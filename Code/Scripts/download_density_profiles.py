'''
Purpose
-------
Retrieve native-height CO5BOLD density snapshots matching atmospheric profiles.

Inputs
------
None

Outputs
-------
Command-line program
    Stage independently validated density profiles and a progress manifest.
    Existing atmospheric files are read only; staged products are not published.

Notes
-----
Download only rho and its native coordinates. Means include every native
horizontal cell; no horizontal subsampling or vertical interpolation is used.
The existing NCO and netCDF4 runtimes are required.
'''
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess

import netCDF4
import numpy as np

# Define the remote model archive and default local reference-profile directory
BASE = 'https://simulations.sdc.leibniz-kis.de/opendap/co5bold'
DEFAULT_PROFILES = Path(__file__).resolve().parents[2]/'Data/co5bold/co5bold_1d_profiles'


def file_hash(path):
    '''
    Purpose
    -------
    Hash a file with SHA-256 using one-megabyte streaming reads.

    Inputs
    ------
    path: str or Path
        Source file whose complete bytes are read.

    Outputs
    -------
    digest: str
        Hexadecimal SHA-256 checksum.
    '''

    result = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def make_profile(reference, raw_path, output_path, *, field='rho', variable_name=None,
                 expected_units='gm/cm^3', output_units=None, factor=1.):
    '''
    Purpose
    -------
    Validate an exact native grid and independently verify its horizontal reduction.

    Inputs
    ------
    reference: Path
        Existing MODEL_tTOKENs_atmos_param.h5 file defining model and native z.

    raw_path: Path
        Downloaded native 3D field and coordinates in NetCDF format.

    output_path: Path
        Standalone profile destination, created or replaced by the NetCDF writer.

    field: str, optional
        Canonical output field name; defaults to rho.

    variable_name: str or None, optional
        Actual source variable name; None uses field.

    expected_units: str, optional
        Exact required source unit attribute.

    output_units: str or None, optional
        Output unit attribute; None retains expected_units.

    factor: float, optional
        Multiplicative conversion applied after the horizontal mean.

    Outputs
    -------
    record: dict
        Provenance, checksums, grid/time checks, and reduction diagnostics for
        the written profile. Coordinates are in cm and native time in seconds.
        Reject nonuniform horizontal cells, missing/nonpositive values, mismatched
        heights/model/time, or incompatible dimensions/units before publication.
    '''
    # Derive the exact model and snapshot token from the atmospheric reference
    match = re.fullmatch(r'(.+)_t(\d+)s_atmos_param\.h5', reference.name)
    if not match:
        raise ValueError(f'Unrecognized atmospheric snapshot name: {reference}')
    model, token = match.groups()
    label_time = int(token)
    source_url = f'{BASE}/{model}/rhd_t{token}s.h5'
    with netCDF4.Dataset(raw_path) as source, netCDF4.Dataset(reference) as existing:
        if source.Model != model:
            raise ValueError(f'Model mismatch for {reference.name}')
        # Require the expected native field dimensions and exact source units
        variable = source[variable_name or field]
        if variable.dimensions != ('xc3', 'xc2', 'xc1') or variable.units != expected_units:
            raise ValueError(f'Unexpected {field} dimensions or units: {variable.dimensions}, {variable.units}')
        # Match every native height to the existing atmospheric profile
        z = np.asarray(source['xc3'][:], dtype=np.float64)
        reference_z = np.asarray(existing['z'][:], dtype=np.float64)
        if not np.array_equal(z, reference_z):
            raise ValueError(f'Native heights differ from atmospheric profile: {reference.name}')
        if not np.all(np.isfinite(z)) or not np.all(np.diff(z) > 0):
            raise ValueError('Invalid native height coordinate.')
        for name in ('xc1', 'xc2', 'xc3', 'xb1', 'xb2', 'xb3'):
            if source[name].units != 'cm':
                raise ValueError(f'Unexpected coordinate units: {name}')
        # Arithmetic averaging is the existing full-plane profile convention.
        # Require uniform horizontal cells rather than silently changing area
        # weights on an unfamiliar mesh.
        for axis in ('xb1', 'xb2'):
            widths = np.diff(np.asarray(source[axis][:], dtype=np.float64))
            if not np.allclose(widths, widths[0], rtol=1e-5, atol=0):
                raise ValueError(f'Nonuniform horizontal cells on {axis}.')
        # Reject missing support before reducing all horizontal cells in float64
        density = np.ma.filled(variable[:], np.nan)
        if not np.all(np.isfinite(density)) or np.any(density <= 0):
            raise ValueError(f'{field} contains missing, nonfinite or nonpositive cells; cannot change the averaging support.')
        averaged = np.mean(density, axis=(1, 2), dtype=np.float64)*factor
        independent = np.mean(np.mean(density, axis=2, dtype=np.float64), axis=1, dtype=np.float64)*factor
        np.testing.assert_allclose(averaged, independent, rtol=5e-15, atol=0)
        # Retain precise native time and compare it with the filename snapshot label
        native_time = float(source.time_db)
        if abs(native_time-label_time) >= 1:
            raise ValueError(f'Native time does not match snapshot label: {native_time}, {label_time}')
        metadata = {name: source.getncattr(name) for name in source.ncattrs()
                    if name not in {'history', 'NCO', '_NCProperties'}}
        # Write the standalone native-height profile and complete source provenance
        with netCDF4.Dataset(output_path, 'w', format='NETCDF4') as output:
            output.setncatts(metadata)
            output.source_url = source_url
            output.source_variable = variable_name or field
            output.source_file_sha256 = file_hash(raw_path)
            output.reference_atmospheric_profile = str(reference.resolve())
            output.reference_atmospheric_profile_sha256 = file_hash(reference)
            output.snapshot_label_time_s = label_time
            output.native_time_db_s = native_time
            output.time_alignment = 'Exact model and snapshot filename token match; native time_db retained. Legacy atmospheric file has no independent time attribute.'
            output.vertical_binning = 'none'
            output.vertical_sampling = 'All native xc3 cell centres, unchanged; no subset, binning or interpolation.'
            output.horizontal_reduction = 'Unweighted arithmetic mean of all native xc1 and xc2 cells, accumulated in float64.'
            output.horizontal_shape = np.array(density.shape[1:], dtype=np.int32)
            output.created_utc = datetime.now(timezone.utc).isoformat()
            output.createDimension('z', len(z))
            height = output.createVariable('z', 'f8', ('z',))
            height[:] = z
            height.units = 'cm'
            height.positive = 'up'
            height.source_variable = 'xc3'
            height.long_name = 'Native vertical cell centres, matching reference atmospheric z exactly'
            rho = output.createVariable(field, 'f8', ('z',), zlib=True, complevel=4)
            rho[:] = averaged
            rho.units = output_units or expected_units
            rho.long_name = f'Horizontally averaged {field} at each native vertical cell centre'
            rho.cell_methods = 'xc1: mean xc2: mean'
            rho.coordinates = 'z time'
            time = output.createVariable('time', 'f8', ())
            time.assignValue(native_time)
            time.units = 's'
            time.long_name = 'Simulation time from source time_db'
            # Keep the native grid, including vertical boundaries, for auditing.
            for name in ('xc1', 'xc2', 'xc3', 'xb1', 'xb2', 'xb3'):
                original = source[name]
                output.createDimension(name, len(original))
                coordinate = output.createVariable(name, original.dtype, (name,))
                coordinate.setncatts({a: original.getncattr(a) for a in original.ncattrs() if a != '_FillValue'})
                coordinate[:] = original[:]
        record = dict(model=model, model_reference=str(source.ModelRefName),
            description=str(source.Description), snapshot_label_time_s=label_time,
            native_time_db_s=native_time, source_url=source_url,
            reference_profile=str(reference.resolve()), reference_sha256=file_hash(reference),
            density_file=output_path.name, density_sha256=file_hash(output_path),
            native_shape=list(density.shape), vertical_levels=len(z),
            heights_exactly_equal=True, vertical_binning=False,
            height_range_cm=[float(z[0]), float(z[-1])],
            density_range_g_cm3=[float(averaged.min()),float(averaged.max())],
            independent_mean_max_relative_error=float(np.max(np.abs(averaged-independent)/averaged)))
    # Rename density-specific manifest keys when reducing another physical field
    if field != 'rho':
        record['profile_file'] = record.pop('density_file')
        record['profile_sha256'] = record.pop('density_sha256')
        record['value_range'] = record.pop('density_range_g_cm3')
        record.update(field=field, source_variable=variable_name or field, units=output_units or expected_units)
    # Read back the completed standalone profile, independently of the writer.
    with netCDF4.Dataset(output_path) as output:
        np.testing.assert_array_equal(output['z'][:], reference_z)
        np.testing.assert_array_equal(output[field][:], averaged)
        assert output[field].dimensions == ('z',)
        assert output[field].units == (output_units or expected_units)
        assert float(output['time'][:]) == native_time
        assert output.vertical_binning == 'none'
    return record


def download(reference, stage, ncks):
    '''
    Purpose
    -------
    Download one native density cube if absent and write its validated profile.

    Inputs
    ------
    reference: Path
        Existing atmospheric snapshot whose filename selects the remote model/time.

    stage: Path
        Existing staging directory for raw data, logs, and output profile.

    ncks: str
        NCO executable used to retrieve rho and native coordinates.

    Outputs
    -------
    record: dict
        make_profile provenance record. Download failures propagate; remote
        execution has a 900-second timeout and writes a per-snapshot log.
    '''

    # Resolve the staged raw cube, profile path, and matching OPeNDAP URL
    stem = reference.name.removesuffix('_atmos_param.h5')
    model, token = re.fullmatch(r'(.+)_t(\d+)s', stem).groups()
    raw_path = stage/(stem+'_raw_density.nc')
    output_path = stage/(stem+'_density_profile.h5')
    url = f'{BASE}/{model}/rhd_t{token}s.h5'
    if not raw_path.is_file():
        command = [ncks, '-O', '-4', '-v', 'rho,xc1,xc2,xc3,xb1,xb2,xb3', url, str(raw_path)]
        with (stage/(stem+'.download.log')).open('w') as log:
            subprocess.run(command, check=True, timeout=900, stdout=log, stderr=subprocess.STDOUT)
    return make_profile(reference, raw_path, output_path)


def main():
    '''
    Purpose
    -------
    Stage all density snapshots matching the command-line reference directory.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Download and validate snapshots sequentially, rewriting the cumulative
        density_profiles_manifest.json after each success. Missing NCO or
        reference profiles raise before download.
    '''

    # Parse the reference directory and required staging directory
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path, default=DEFAULT_PROFILES)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    ncks = shutil.which('ncks')
    if not ncks:
        raise RuntimeError('The existing NCO ncks executable is required.')
    args.stage.mkdir(parents=True, exist_ok=True)
    references = sorted(args.profiles.glob('*_atmos_param.h5'))
    if not references:
        raise ValueError('No existing atmospheric reference profiles found.')
    records = []
    # Download sequentially: NCO/netCDF4 are not assumed thread-safe, and the
    # public server need not serve multiple full-density cubes concurrently.
    for reference in references:
        print('Retrieving '+reference.name, flush=True)
        record = download(reference, args.stage, ncks)
        records.append(record)
        print('Validated '+record['density_file'], flush=True)
        (args.stage/'density_profiles_manifest.json').write_text(json.dumps(
            dict(profile_count=len(records), profiles=records), indent=2)+'\n')


if __name__ == '__main__':
    main()
