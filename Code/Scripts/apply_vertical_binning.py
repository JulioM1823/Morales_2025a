#!/usr/bin/env python3
'''
Purpose
-------
Vertically bin CO5BOLD NetCDF files using cell-center averages and
subsampled cell boundaries, with progress reporting.

Inputs
------
None

Outputs
-------
Command-line program
    Write one binned NetCDF per input; --overwrite permits replacement.
    The selected xc3 range is inclusive, and xb3 includes its upper boundary.
'''

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
    '''
    Purpose
    -------
    Format elapsed whole seconds as hours, minutes, and seconds.

    Inputs
    ------
    seconds: float
        Elapsed time in seconds; the fractional part is discarded.

    Outputs
    -------
    text: str
        Compact elapsed-time label with only the required leading units.
    '''

    # Convert the elapsed duration to whole hours, minutes, and seconds
    seconds_i = int(seconds)
    minutes, seconds_i = divmod(seconds_i, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours:d}h{minutes:02d}m{seconds_i:02d}s"
    if minutes:
        return f"{minutes:d}m{seconds_i:02d}s"
    return f"{seconds_i:d}s"


def format_bytes(num_bytes: int) -> str:
    '''
    Purpose
    -------
    Format a byte count with binary size prefixes.

    Inputs
    ------
    num_bytes: int
        Number of bytes to report.

    Outputs
    -------
    text: str
        Size rounded to one decimal place in B, KiB, MiB, GiB, or TiB.
    '''

    # Scale by powers of 1024 until the value fits a binary display unit
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024.0

    return f"{value:.1f} TiB"


class ProgressLog:
    '''
    Purpose
    -------
    Write optional elapsed-time progress messages to standard error.

    Inputs
    ------
    enabled: bool, optional
        Enable progress output when True.

    Outputs
    -------
    logger: ProgressLog
        Logger retaining its monotonic start time and enabled state.
    '''

    def __init__(self, enabled: bool = True) -> None:
        '''
        Purpose
        -------
        Store whether progress output is enabled and start the elapsed timer.

        Inputs
        ------
        enabled: bool, optional
            Enable progress messages when True.

        Outputs
        -------
        None
            Initialize the instance enabled flag and monotonic start time.
        '''

        self.enabled = enabled
        self.start_time = time.monotonic()

    def emit(self, message: str) -> None:
        '''
        Purpose
        -------
        Print a timestamped progress message when logging is enabled.

        Inputs
        ------
        message: str
            Progress text to write.

        Outputs
        -------
        None
            Flush the formatted message to standard error; disabled loggers are silent.
        '''

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
    '''
    Purpose
    -------
    Start a daemon thread that periodically reports the size of an output file.

    Inputs
    ------
    path: Path
        Output file being written; absent files are reported as zero bytes.

    label: str
        Progress label preceding the size report.

    progress: ProgressLog
        Logger controlling whether monitoring is enabled.

    interval: float
        Seconds between file-size polls.

    Outputs
    -------
    stop_event, thread: tuple
        Thread cancellation event and daemon thread, or (None, None) when
        progress output is disabled.
    '''

    if not progress.enabled:
        return None, None

    stop_event = threading.Event()

    def monitor() -> None:
        '''
        Purpose
        -------
        Poll the enclosing output path until its stop event is signaled.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Emit file sizes through the enclosing logger and identify unchanged sizes.
        '''

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
    '''
    Purpose
    -------
    Signal a file-size monitor to stop and wait briefly for its thread.

    Inputs
    ------
    stop_event: threading.Event or None
        Cancellation event returned by start_file_size_monitor.

    thread: threading.Thread or None
        Corresponding daemon thread.

    Outputs
    -------
    None
        Return immediately for absent handles; otherwise join for at most two seconds.
    '''

    if stop_event is None or thread is None:
        return

    stop_event.set()
    thread.join(timeout=2.0)


def parse_args() -> argparse.Namespace:
    '''
    Purpose
    -------
    Parse input files, vertical sampling, output paths, and progress settings.

    Inputs
    ------
    None

    Outputs
    -------
    args: argparse.Namespace
        Parsed command-line settings. Invalid arguments terminate through argparse.
    '''

    # Declare file selection, sampling, overwrite, and progress options
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
    '''
    Purpose
    -------
    Construct a binned-output path while retaining the input file extension.

    Inputs
    ------
    input_path: Path
        Source NetCDF path.

    output_dir: Path or None
        Destination directory; None uses the input parent directory.

    suffix: str
        Text appended to the input stem before its extension.

    Outputs
    -------
    path: Path
        Destination path; this helper creates no directory or file.
    '''

    target_dir = output_dir if output_dir is not None else input_path.parent
    stem = input_path.stem
    return target_dir / f"{stem}{suffix}{input_path.suffix}"


def append_history(attrs: dict, entry: str) -> None:
    '''
    Purpose
    -------
    Prepend a processing record to a dataset attribute mapping.

    Inputs
    ------
    attrs: dict
        Mutable dataset attributes updated in place.

    entry: str
        New history line to prepend.

    Outputs
    -------
    None
        Update attrs["history"], retaining any previous text below the new entry.
    '''

    history = attrs.get("history", "")
    if history:
        attrs["history"] = f"{entry}\n{history}"
    else:
        attrs["history"] = entry


def validate_ranges(ds: xr.Dataset, z_start: int, z_end: int, z_bin: int) -> None:
    '''
    Purpose
    -------
    Check that the selected center/boundary indices support the requested binning.

    Inputs
    ------
    ds: xarray.Dataset
        Input with xc3 cell centers and xb3 cell boundaries.

    z_start, z_end: int
        Inclusive lower and upper xc3 indices.

    z_bin: int
        Positive center-cell averaging factor; checked by main before this call.

    Outputs
    -------
    None
        Raise ValueError for absent dimensions, invalid index bounds, or a
        selected center count not divisible by z_bin.
    '''

    # Validate required dimensions before indexing cell centers and boundaries
    if "xc3" not in ds.dims or "xb3" not in ds.dims:
        raise ValueError("Dataset must contain xc3 and xb3 dimensions.")

    if z_start < 0 or z_end < 0:
        raise ValueError("z-start and z-end must be non-negative.")

    if z_end < z_start:
        raise ValueError("z-end must be >= z-start.")

    # Check the inclusive center range and its extra upper cell boundary
    xc3_len = ds.sizes["xc3"]
    xb3_len = ds.sizes["xb3"]

    if z_end >= xc3_len:
        raise ValueError(f"z-end={z_end} exceeds xc3 length={xc3_len}.")

    if z_end + 1 >= xb3_len:
        raise ValueError(f"xb3 length={xb3_len} inconsistent with z-end={z_end}.")

    # Require complete center-cell groups for the requested averaging factor
    sliced_len = z_end - z_start + 1
    if sliced_len % z_bin != 0:
        raise ValueError(
            f"Selected xc3 range length {sliced_len} is not divisible by z-bin={z_bin}."
        )


def bin_dataset(ds: xr.Dataset, z_start: int, z_end: int, z_bin: int) -> xr.Dataset:
    '''
    Purpose
    -------
    Select the inclusive center range, average vertical centers, and retain bin edges.

    Inputs
    ------
    ds: xarray.Dataset
        Input with xc3 and xb3 dimensions.

    z_start, z_end: int
        Inclusive xc3 range, already validated.

    z_bin: int
        Positive number of center cells per vertical average.

    Outputs
    -------
    binned: xarray.Dataset
        Dataset coarsened along xc3; xb3 is sampled at every z_bin-th boundary.
        Variable attributes are retained through the averaging operation.
    '''

    # Select matching center and boundary intervals before coarsening centers
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
    '''
    Purpose
    -------
    Validate, vertically bin, and write one input dataset with history metadata.

    Inputs
    ------
    path: Path
        Existing input NetCDF file.

    args: argparse.Namespace
        Vertical ranges, bin factor, output location, suffix, and overwrite policy.

    progress: ProgressLog
        Progress logger for the processing stages.

    progress_interval: float
        Seconds between file-size progress updates.

    Outputs
    -------
    output_path: Path
        Written NetCDF path. Existing outputs are rejected unless overwrite is
        enabled; same-path writes use a temporary file followed by replacement.
        Input datasets and monitor handles are closed on exit.
    '''

    # Reject missing input and pre-existing outputs before opening the dataset
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")

    progress.emit(f"[1/5] Preparing output path for {path}")
    output_path = build_output_path(path, args.output_dir, args.suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Avoid truncating an input file when the requested destination is identical
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
        # Build the binned view only after validating the complete vertical range
        validate_ranges(ds, args.z_start, args.z_end, args.z_bin)
        progress.emit("[4/5] Building vertically binned dataset")
        ds_bin = bin_dataset(ds, args.z_start, args.z_end, args.z_bin)
        ds_bin.attrs = dict(ds.attrs)
        # Record the applied native-index range and averaging factor in UTC
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
        # Write the output while the daemon monitor reports its growing size
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
    '''
    Purpose
    -------
    Run vertical binning for each command-line input and print output paths.

    Inputs
    ------
    None

    Outputs
    -------
    status: int
        Zero after all files are written. Invalid bin factors or file failures
        propagate as exceptions and stop subsequent processing.
    '''

    # Parse settings and clamp reporting intervals to at least one second
    args = parse_args()
    progress = ProgressLog(enabled=not args.no_progress)
    progress_interval = max(1.0, args.progress_interval)

    if args.z_bin < 1:
        raise ValueError("z-bin must be >= 1")

    # Process inputs sequentially and retain the paths of completed outputs
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
