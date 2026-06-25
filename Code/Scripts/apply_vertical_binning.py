#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

import xarray as xr


def format_duration(seconds: float) -> str:
    seconds_i = int(seconds)
    minutes, seconds_i = divmod(seconds_i, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours:d}h{minutes:02d}m{seconds_i:02d}s"
    if minutes:
        return f"{minutes:d}m{seconds_i:02d}s"
    return f"{seconds_i:d}s"


def format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024.0

    return f"{value:.1f} TiB"


class ProgressLog:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.start_time = time.monotonic()

    def emit(self, message: str) -> None:
        if not self.enabled:
            return

        elapsed = format_duration(time.monotonic() - self.start_time)
        print(f"[progress +{elapsed}] {message}", file=sys.stderr, flush=True)


def start_file_size_monitor(
    path: Path,
    label: str,
    progress: ProgressLog,
    interval: float,
) -> tuple[threading.Event | None, threading.Thread | None]:
    if not progress.enabled:
        return None, None

    stop_event = threading.Event()

    def monitor() -> None:
        last_size: int | None = None
        while not stop_event.wait(interval):
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                size = 0

            suffix = "" if size != last_size else " (unchanged)"
            progress.emit(
                f"{label}: {format_bytes(size)} written to {path.name}{suffix}"
            )
            last_size = size

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()

    return stop_event, thread


def stop_file_size_monitor(
    stop_event: threading.Event | None,
    thread: threading.Thread | None,
) -> None:
    if stop_event is None or thread is None:
        return

    stop_event.set()
    thread.join(timeout=2.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply vertical binning to NetCDF files using the same xc3/xb3 "
            "logic as the CO5BOLD download pipeline."
        )
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Input NetCDF files to vertically bin.",
    )
    parser.add_argument(
        "--z-start",
        type=int,
        default=54,
        help="First xc3 index to include before binning (default: %(default)s).",
    )
    parser.add_argument(
        "--z-end",
        type=int,
        default=119,
        help="Last xc3 index to include before binning (default: %(default)s).",
    )
    parser.add_argument(
        "--z-bin",
        type=int,
        default=11,
        help="Vertical bin factor (default: %(default)s).",
    )
    parser.add_argument(
        "--suffix",
        default="_vbin",
        help="Suffix to append before .nc (default: %(default)s).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory (default: same as input file).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite outputs if they already exist.",
    )
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=10.0,
        help=(
            "Seconds between long-running progress updates "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress messages.",
    )
    return parser.parse_args()


def build_output_path(input_path: Path, output_dir: Path | None, suffix: str) -> Path:
    target_dir = output_dir if output_dir is not None else input_path.parent
    stem = input_path.stem
    return target_dir / f"{stem}{suffix}{input_path.suffix}"


def append_history(attrs: dict, entry: str) -> None:
    history = attrs.get("history", "")
    if history:
        attrs["history"] = f"{entry}\n{history}"
    else:
        attrs["history"] = entry


def validate_ranges(ds: xr.Dataset, z_start: int, z_end: int, z_bin: int) -> None:
    if "xc3" not in ds.dims or "xb3" not in ds.dims:
        raise ValueError("Dataset must contain xc3 and xb3 dimensions.")

    if z_start < 0 or z_end < 0:
        raise ValueError("z-start and z-end must be non-negative.")

    if z_end < z_start:
        raise ValueError("z-end must be >= z-start.")

    xc3_len = ds.sizes["xc3"]
    xb3_len = ds.sizes["xb3"]

    if z_end >= xc3_len:
        raise ValueError(f"z-end={z_end} exceeds xc3 length={xc3_len}.")

    if z_end + 1 >= xb3_len:
        raise ValueError(f"xb3 length={xb3_len} inconsistent with z-end={z_end}.")

    sliced_len = z_end - z_start + 1
    if sliced_len % z_bin != 0:
        raise ValueError(
            f"Selected xc3 range length {sliced_len} is not divisible by z-bin={z_bin}."
        )


def bin_dataset(ds: xr.Dataset, z_start: int, z_end: int, z_bin: int) -> xr.Dataset:
    ds_slice = ds.isel(xc3=slice(z_start, z_end + 1), xb3=slice(z_start, z_end + 2))
    ds_slice = ds_slice.isel(xb3=slice(0, None, z_bin))

    with xr.set_options(keep_attrs=True):
        ds_bin = ds_slice.coarsen(xc3=z_bin, boundary="trim").mean()

    return ds_bin


def process_file(
    path: Path,
    args: argparse.Namespace,
    progress: ProgressLog,
    progress_interval: float,
) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")

    progress.emit(f"[1/5] Preparing output path for {path}")
    output_path = build_output_path(path, args.output_dir, args.suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    same_path = output_path.resolve() == path.resolve()
    temp_path: Path | None = None
    if same_path:
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{path.stem}_vbin_",
            suffix=path.suffix,
            dir=str(path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)

    progress.emit(f"[2/5] Opening input dataset: {path.name}")
    ds = xr.open_dataset(path, engine="netcdf4", cache=False, chunks="auto")
    try:
        progress.emit(
            "[3/5] Validating vertical range "
            f"xc3[{args.z_start}:{args.z_end}] with z_bin={args.z_bin}; "
            f"input sizes: time={ds.sizes.get('time', 'n/a')}, "
            f"xc3={ds.sizes.get('xc3', 'n/a')}, xb3={ds.sizes.get('xb3', 'n/a')}"
        )
        validate_ranges(ds, args.z_start, args.z_end, args.z_bin)
        progress.emit("[4/5] Building vertically binned dataset")
        ds_bin = bin_dataset(ds, args.z_start, args.z_end, args.z_bin)
        ds_bin.attrs = dict(ds.attrs)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        history_entry = (
            f"{timestamp}: apply_vertical_binning.py "
            f"xc3[{args.z_start}:{args.z_end}] z_bin={args.z_bin}"
        )
        append_history(ds_bin.attrs, history_entry)
        write_path = temp_path if temp_path is not None else output_path
        progress.emit(f"[5/5] Writing NetCDF output: {write_path.name}")
        stop_event, thread = start_file_size_monitor(
            write_path,
            "Writing binned output",
            progress,
            progress_interval,
        )
        ds_bin.to_netcdf(write_path)
        stop_file_size_monitor(stop_event, thread)
        stop_event = None
        thread = None
        progress.emit(
            f"Finished writing {format_bytes(write_path.stat().st_size)} "
            f"to {write_path.name}"
        )
        if temp_path is not None:
            progress.emit(f"Replacing original file with binned output: {output_path}")
            temp_path.replace(output_path)
    finally:
        if "stop_event" in locals() and "thread" in locals():
            stop_file_size_monitor(stop_event, thread)
        ds.close()

    return output_path


def main() -> int:
    args = parse_args()
    progress = ProgressLog(enabled=not args.no_progress)
    progress_interval = max(1.0, args.progress_interval)

    if args.z_bin < 1:
        raise ValueError("z-bin must be >= 1")

    outputs: list[Path] = []
    total_files = len(args.files)
    for idx, path in enumerate(args.files, start=1):
        progress.emit(f"Processing file {idx}/{total_files}")
        outputs.append(process_file(path, args, progress, progress_interval))

    for output in outputs:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
