#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import tempfile

import netCDF4  # noqa: F401
import numpy as np
import xarray as xr

try:
    import dask  # noqa: F401

    HAS_DASK = True
except ImportError:
    HAS_DASK = False

TS_PATTERN = re.compile(r't(-?\d+)s')

def read_args() -> argparse.Namespace:
    
    '''
    Purpose
    --------
    Parse the command-line arguments for the NetCDF concatenation workflow.

    Inputs
    ------
    None.

    Outputs
    --------
    args : argparse.Namespace | Parsed command-line arguments.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    parser = argparse.ArgumentParser(
        description=(
            'Concatenate NetCDF files in a directory after sorting them by the '
            'integer embedded between t and s in the filename.'
        )
    )
    parser.add_argument(
        'directory',
        type=Path,
        help='Directory containing the NetCDF (.nc) files to combine.',
    )
    parser.add_argument(
        '--output',
        default=None,
        help=(
            'Name of the output NetCDF file written inside the input directory. '
            'If omitted, the script uses '
            'simulation_<parent_dir>_<dir>_<start>s_<end>s.nc.'
        ),
    )
    parser.add_argument(
        '--time-dim',
        default='time',
        help=(
            'Time dimension name. If the input files already contain this '
            'dimension, the script concatenates along it. Otherwise, a new time '
            'dimension with this name is created from the filename tokens '
            '(default: %(default)s).'
        ),
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite the output file if it already exists.',
    )
    
    return parser.parse_args()


def get_t_value(nc_path: Path) -> int:
    
    '''
    Purpose
    --------
    Extract the integer between the characters 't' and 's' from a NetCDF filename.

    Inputs
    ------
    nc_path : Path | Path to a NetCDF file.

    Outputs
    --------
    t_val : int | Integer time token extracted from the filename.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    match = TS_PATTERN.search(nc_path.name)
    if match is None:
        raise ValueError(
            f"Filename does not contain a 't<number>s' token: {nc_path.name}"
        )
    
    return int(match.group(1))


def find_nc_files(
    nc_dir: Path,
    out_name: str | None = None,
    ignore_bad_name: bool = False,
) -> tuple[list[Path], list[int]]:
    
    '''
    Purpose
    --------
    Find all NetCDF files in a directory, exclude the requested output file,
    and sort the files using the integer embedded between 't' and 's'.

    Inputs
    ------
    nc_dir : Path | Directory containing the NetCDF files.
    out_name : str | None | Name of the output file to exclude from the search.
    ignore_bad_name : bool | If True, skip .nc files that do not match the
        expected t...s filename pattern.

    Outputs
    --------
    nc_files : list[Path] | Sorted list of NetCDF file paths.
    t_vals : list[int] | Sorted list of integer time tokens associated with nc_files.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    if not nc_dir.exists():
        raise FileNotFoundError(f'Directory does not exist: {nc_dir}')
    
    if not nc_dir.is_dir():
        raise NotADirectoryError(f'Input path is not a directory: {nc_dir}')
    
    # Collect the candidate NetCDF files
    nc_list = sorted(
        path
        for path in nc_dir.iterdir()
        if path.is_file() and path.suffix.lower() == '.nc' and path.name != out_name
    )
    
    if not nc_list:
        raise FileNotFoundError(f'No .nc files were found in {nc_dir}')
    
    pairs = []
    for nc_file in nc_list:
        try:
            pairs.append((get_t_value(nc_file), nc_file))
        except ValueError:
            if ignore_bad_name:
                continue
            raise
    
    if not pairs:
        raise FileNotFoundError(
            f"No .nc files containing a 't<number>s' token were found in {nc_dir}"
        )
    
    pairs.sort(key=lambda pair: pair[0])
    
    t_vals = [pair[0] for pair in pairs]
    nc_files = [pair[1] for pair in pairs]
    
    return nc_files, t_vals


def get_output_name(nc_dir: Path, t_vals: list[int]) -> str:
    
    '''
    Purpose
    --------
    Build the default output filename from the input directory structure and
    the sorted time range.

    Inputs
    ------
    nc_dir : Path | Directory containing the NetCDF files.
    t_vals : list[int] | Sorted list of integer time tokens.

    Outputs
    --------
    out_name : str | Default output filename.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    if not t_vals:
        raise ValueError('t_vals must contain at least one time value.')
    
    parent_name = nc_dir.parent.name if nc_dir.parent != nc_dir else 'root'
    dir_name = nc_dir.name if nc_dir.name else 'root'
    
    out_name = (
        f'simulation_{parent_name}_{dir_name}_{t_vals[0]}s_{t_vals[-1]}s.nc'
    )
    
    return out_name


def open_nc_file(nc_path: Path, chunks: str | None = None) -> xr.Dataset:
    
    '''
    Purpose
    --------
    Open a NetCDF file with xarray using the netCDF4 backend.

    Inputs
    ------
    nc_path : Path | Path to the NetCDF file.
    chunks : str | None | Chunking directive passed to xarray.

    Outputs
    --------
    ds : xarray.Dataset | Opened NetCDF dataset.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    return xr.open_dataset(nc_path, engine='netcdf4', cache=False, chunks=chunks)


def get_time_dim_name(ds: xr.Dataset, time_dim: str) -> tuple[str, bool]:
    
    '''
    Purpose
    --------
    Determine whether the requested time dimension already exists in the dataset.

    Inputs
    ------
    ds : xarray.Dataset | Dataset used to determine the concatenation dimension.
    time_dim : str | Requested time dimension name.

    Outputs
    --------
    dim_name : str | Time dimension name that should be used for concatenation.
    has_time_dim : bool | True if the input dataset already contains dim_name.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    if time_dim in ds.sizes:
        return time_dim, True
    
    if time_dim == 'time':
        lower_time = [name for name in ds.sizes if name.lower() == 'time']
        if len(lower_time) == 1:
            return lower_time[0], True
    
    return time_dim, False


def get_dataset_schema(ds: xr.Dataset) -> dict[str, object]:
    
    '''
    Purpose
    --------
    Build a lightweight schema summary of a dataset for compatibility checks.

    Inputs
    ------
    ds : xarray.Dataset | Dataset whose structure will be summarized.

    Outputs
    --------
    schema : dict | Dictionary containing dimensions, coordinates, variables,
        and dtypes needed to compare datasets before concatenation.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    var_info: dict[str, dict[str, object]] = {}
    for name, var in ds.variables.items():
        var_info[name] = {
            'dims': tuple(var.dims),
            'dtype': np.dtype(var.dtype).str,
        }
    
    schema = {
        'sizes': {name: int(size) for name, size in ds.sizes.items()},
        'data_vars': tuple(sorted(ds.data_vars)),
        'coords': tuple(sorted(ds.coords)),
        'var_info': var_info,
    }
    
    return schema


def check_dataset_match(
    ds: xr.Dataset,
    nc_path: Path,
    ref_schema: dict[str, object],
    ref_path: Path,
    time_dim: str,
    has_time_dim: bool,
) -> None:
    
    '''
    Purpose
    --------
    Verify that a dataset matches the reference schema before concatenation.

    Inputs
    ------
    ds : xarray.Dataset | Dataset being checked.
    nc_path : Path | Path to ds.
    ref_schema : dict | Reference dataset schema.
    ref_path : Path | Path to the reference dataset.
    time_dim : str | Concatenation dimension name.
    has_time_dim : bool | True if the input files already contain time_dim.

    Outputs
    --------
    None.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    ds_dims = set(ds.sizes)
    ref_dims = set(ref_schema['sizes'])
    
    if ds_dims != ref_dims:
        missing = sorted(ref_dims - ds_dims)
        extra = sorted(ds_dims - ref_dims)
        raise ValueError(
            f'Dimension names do not match for {nc_path.name} relative to '
            f"{ref_path.name}. Missing: {missing or 'none'}, extra: {extra or 'none'}."
        )
    
    # Skip the concatenation axis when checking sizes
    for dim_name, ref_size in ref_schema['sizes'].items():
        if has_time_dim and dim_name == time_dim:
            continue
        
        ds_size = int(ds.sizes[dim_name])
        if ds_size != ref_size:
            raise ValueError(
                f"Dimension '{dim_name}' differs in {nc_path.name}: "
                f'expected {ref_size}, found {ds_size}.'
            )
    
    if tuple(sorted(ds.data_vars)) != ref_schema['data_vars']:
        raise ValueError(
            f'Data variables do not match for {nc_path.name} relative to '
            f'{ref_path.name}.'
        )
    
    if tuple(sorted(ds.coords)) != ref_schema['coords']:
        raise ValueError(
            f'Coordinate variables do not match for {nc_path.name} relative to '
            f'{ref_path.name}.'
        )
    
    for name, ref_var in ref_schema['var_info'].items():
        if name not in ds.variables:
            raise ValueError(f"Variable '{name}' is missing from {nc_path.name}.")
        
        ds_var = ds.variables[name]
        ds_dims_var = tuple(ds_var.dims)
        ds_dtype = np.dtype(ds_var.dtype).str
        
        if ds_dims_var != ref_var['dims']:
            raise ValueError(
                f"Variable '{name}' has incompatible dimensions in {nc_path.name}: "
                f"expected {ref_var['dims']}, found {ds_dims_var}."
            )
        
        if ds_dtype != ref_var['dtype']:
            raise ValueError(
                f"Variable '{name}' has incompatible dtype in {nc_path.name}: "
                f"expected {ref_var['dtype']}, found {ds_dtype}."
            )


def check_input_files(nc_files: list[Path], time_dim: str) -> tuple[str, bool]:
    
    '''
    Purpose
    --------
    Validate that all input NetCDF files are structurally compatible for
    concatenation.

    Inputs
    ------
    nc_files : list[Path] | Sorted list of NetCDF file paths.
    time_dim : str | Requested time dimension name.

    Outputs
    --------
    dim_name : str | Concatenation dimension name that will be used.
    has_time_dim : bool | True if the input files already contain dim_name.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    ref_path = nc_files[0]
    
    with open_nc_file(ref_path) as ds0:
        dim_name, has_time_dim = get_time_dim_name(ds0, time_dim)
        if not has_time_dim and dim_name in ds0.variables:
            raise ValueError(
                f"The requested time dimension '{dim_name}' is not an input "
                f'dimension, but a variable with that name already exists in '
                f'{ref_path.name}. Choose a different --time-dim value.'
            )
        ref_schema = get_dataset_schema(ds0)
    
    for nc_path in nc_files[1:]:
        with open_nc_file(nc_path) as ds:
            has_time_dim_i = dim_name in ds.sizes
            if has_time_dim_i != has_time_dim:
                raise ValueError(
                    f'Time dimension presence is inconsistent in {nc_path.name}. '
                    f'Expected existing time dimension: {has_time_dim}.'
                )
            
            if not has_time_dim and dim_name in ds.variables:
                raise ValueError(
                    f"The requested time dimension '{dim_name}' conflicts with "
                    f'an existing variable in {nc_path.name}. Choose a different '
                    f'--time-dim value.'
                )
            
            check_dataset_match(
                ds=ds,
                nc_path=nc_path,
                ref_schema=ref_schema,
                ref_path=ref_path,
                time_dim=dim_name,
                has_time_dim=has_time_dim,
            )
    
    return dim_name, has_time_dim


def update_history(ds: xr.Dataset, nc_files: list[Path]) -> xr.Dataset:
    
    '''
    Purpose
    --------
    Append a history entry describing the concatenation that produced the
    output dataset.

    Inputs
    ------
    ds : xarray.Dataset | Concatenated dataset.
    nc_files : list[Path] | Input NetCDF files used to build ds.

    Outputs
    --------
    ds : xarray.Dataset | Dataset with an updated history attribute.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    new_line = (
        f'{now_utc}: concatenated {len(nc_files)} files sorted by the '
        "integer between 't' and 's' in each filename"
    )
    
    attrs = dict(ds.attrs)
    if attrs.get('history'):
        attrs['history'] = f"{attrs['history']}\n{new_line}"
    else:
        attrs['history'] = new_line
    
    ds.attrs = attrs
    
    return ds


def concat_nc_files(
    nc_files: list[Path],
    t_vals: list[int],
    time_dim: str,
    has_time_dim: bool,
) -> tuple[xr.Dataset, list[xr.Dataset]]:
    
    '''
    Purpose
    --------
    Concatenate a sorted list of NetCDF files into one continuous dataset.

    Inputs
    ------
    nc_files : list[Path] | Sorted list of NetCDF file paths.
    t_vals : list[int] | Integer time tokens extracted from the filenames.
    time_dim : str | Concatenation dimension name.
    has_time_dim : bool | True if the input files already contain time_dim.

    Outputs
    --------
    ds_cat : xarray.Dataset | Concatenated dataset.
    open_list : list[xarray.Dataset] | List of datasets that must be closed by
        the caller when xr.concat is used.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    if has_time_dim:
        concat_axis: str | xr.IndexVariable = time_dim
    else:
        # Build the new time coordinate from the filename values
        concat_axis = xr.IndexVariable(time_dim, np.asarray(t_vals, dtype=np.int64))
    
    concat_kwargs = {
        'data_vars': 'all',
        'coords': 'different',
        'compat': 'equals',
        'join': 'exact',
        'combine_attrs': 'override',
    }
    
    if HAS_DASK and has_time_dim:
        ds_cat = xr.open_mfdataset(
            [str(path) for path in nc_files],
            engine='netcdf4',
            combine='nested',
            concat_dim=concat_axis,
            chunks='auto',
            **concat_kwargs,
        )
        return ds_cat, []
    
    chunk_mode = 'auto' if HAS_DASK else None
    open_list = [open_nc_file(path, chunks=chunk_mode) for path in nc_files]
    
    with xr.set_options(keep_attrs=True):
        ds_cat = xr.concat(open_list, dim=concat_axis, **concat_kwargs)
    
    return ds_cat, open_list


def write_output_nc(
    ds: xr.Dataset,
    out_path: Path,
    time_dim: str,
    overwrite: bool,
) -> None:
    
    '''
    Purpose
    --------
    Write the concatenated dataset to disk as a new NetCDF file.

    Inputs
    ------
    ds : xarray.Dataset | Dataset to write.
    out_path : Path | Output NetCDF file path.
    time_dim : str | Time dimension name.
    overwrite : bool | If True, allow an existing output file to be replaced.

    Outputs
    --------
    None.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    if out_path.exists() and not overwrite:
        raise FileExistsError(
            f'Output file already exists: {out_path}. '
            'Re-run with --overwrite to replace it.'
        )
    
    # Write to a temporary file first to avoid partial outputs
    with tempfile.NamedTemporaryFile(
        dir=out_path.parent,
        prefix=f'{out_path.stem}.',
        suffix='.tmp.nc',
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
    
    unlimited_dims = [time_dim] if time_dim in ds.dims else None
    
    try:
        ds.to_netcdf(
            tmp_path,
            engine='netcdf4',
            format='NETCDF4',
            unlimited_dims=unlimited_dims,
        )
        tmp_path.replace(out_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def main() -> int:
    
    '''
    Purpose
    --------
    Execute the full NetCDF discovery, sorting, validation, concatenation, and
    output-writing workflow.

    Inputs
    ------
    None.

    Outputs
    --------
    rc : int | Return code for shell execution. Zero indicates success.

    Author(s)
    ---------
    OpenAI Codex, Mar. 13th, 2026.
    '''
    
    args = read_args()
    
    nc_dir = args.directory.expanduser().resolve()
    
    try:
        if args.output is None:
            _, t_vals0 = find_nc_files(nc_dir, ignore_bad_name=True)
            out_name = get_output_name(nc_dir, t_vals0)
        else:
            out_name = args.output
        
        out_path = nc_dir / out_name
        nc_files, t_vals = find_nc_files(
            nc_dir,
            out_path.name,
            ignore_bad_name=True,
        )
        time_dim, has_time_dim = check_input_files(nc_files, args.time_dim)
    except Exception as err:  # noqa: BLE001
        print(f'Error: {err}', file=sys.stderr)
        return 1
    
    print(f'Found {len(nc_files)} NetCDF files in {nc_dir}')
    print(f'Sorted by filename token t...s from {t_vals[0]} to {t_vals[-1]}')
    
    if has_time_dim:
        print(f"Using existing time dimension '{time_dim}'")
    else:
        print(f"Creating new time dimension '{time_dim}' from filename values")
    
    ds_cat: xr.Dataset | None = None
    open_list: list[xr.Dataset] = []
    
    try:
        ds_cat, open_list = concat_nc_files(
            nc_files=nc_files,
            t_vals=t_vals,
            time_dim=time_dim,
            has_time_dim=has_time_dim,
        )
        ds_cat = update_history(ds_cat, nc_files)
        
        if not has_time_dim and time_dim in ds_cat.coords:
            ds_cat[time_dim].attrs.setdefault(
                'description',
                "Integer extracted from the filename token between 't' and 's'.",
            )
        
        write_output_nc(
            ds=ds_cat,
            out_path=out_path,
            time_dim=time_dim,
            overwrite=args.overwrite,
        )
    except Exception as err:  # noqa: BLE001
        print(f'Error: {err}', file=sys.stderr)
        return 1
    finally:
        if ds_cat is not None:
            ds_cat.close()
        
        for ds in open_list:
            ds.close()
    
    print(f'Wrote concatenated dataset to {out_path}')
    
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
