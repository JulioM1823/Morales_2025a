'''
Purpose
-------
Stage pressure and plasma-beta snapshots on native atmospheric heights.

Inputs
------
None

Outputs
-------
Command-line program
    Write validated standalone profiles and a manifest; copy staged outputs
    into the profile directory only with --publish.

Notes
-----
Fields are never estimated from internal energy or averaged magnetic
components. Missing publisher/server fields are recorded without placeholders.
'''
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import netCDF4
import numpy as np

from download_density_profiles import BASE, DEFAULT_PROFILES, file_hash, make_profile
# Make the shared native-field selection and unit conversion helpers importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Time-Distance'))
from simulation_observables import FIELD_NAMES, profile_units, select_field


def import_shared(reference, source_path, stage, source_url, pressure_unit):
    '''
    Purpose
    -------
    Copy publisher-provided one-dimensional values without averaging them again.

    Inputs
    ------
    reference: Path
        Atmospheric profile whose filename, heights, and density snapshot identify the model/time.

    source_path: Path
        Publisher 1D atmospheric file with exactly the reference filename.

    stage: Path
        Existing staging directory for standalone pressure/beta profiles.

    source_url: str
        Publisher provenance URL recorded in the output metadata.

    pressure_unit: str or None
        Explicit legacy pressure-unit contract when its attribute is missing.

    Outputs
    -------
    record: dict
        Copied profile provenance and missing fields. Output z uses cm, native
        time uses seconds, pressure is converted by profile_units, and beta is
        dimensionless. Height/density mismatches, invalid fields, or unsupported
        units raise; complete profiles are read back after writing.
    '''
    model, token = re.fullmatch(r'(.+)_t(\d+)s_atmos_param\.h5', reference.name).groups()
    # Require the same model/snapshot name before comparing native profiles
    if source_path.name != reference.name:
        raise ValueError('Shared and reference snapshot names must match exactly.')
    stem = f'{model}_t{token}s'
    density_path = reference.with_name(stem+'_density_profile.h5')
    record = dict(model=model, snapshot_label_time_s=int(token), source_url=source_url,
                  source_file=source_path.name, source_sha256=file_hash(source_path),
                  profiles=[], missing_fields=[])
    with netCDF4.Dataset(source_path) as source, netCDF4.Dataset(reference) as thermal, netCDF4.Dataset(density_path) as density:
        z = np.asarray(source['z'][:], float)
        np.testing.assert_array_equal(z, thermal['z'][:])
        np.testing.assert_array_equal(z, density['z'][:])
        if not np.all(np.diff(z) > 0):
            raise ValueError('Shared heights must be strictly increasing.')
        # Independently confirm that the new publisher profile belongs to the
        # previously retrieved density snapshot, allowing float32 mean error.
        np.testing.assert_allclose(source['rho'][:], density['rho'][:], rtol=2e-7, atol=0)
        record['density_max_relative_difference'] = float(np.max(
            np.abs(source['rho'][:]-density['rho'][:])/density['rho'][:]))
        ratio = np.asarray(source['rho'][:])*np.asarray(source['sound_speed'][:])**2/np.asarray(source['pressure'][:])
        record['rho_cs_squared_over_pressure_median'] = float(np.median(ratio))
        native_time = float(density['time'][:])
        # Copy each available canonical field after validating units and support
        for field in FIELD_NAMES:
            if field not in source.variables:
                record['missing_fields'].append(field)
                continue
            variable = source[field]
            if variable.dimensions != ('z',):
                raise ValueError(f'{field} must be a native 1D profile.')
            units = getattr(variable, 'units', '') or (pressure_unit if field == 'pressure' else '1')
            output_units, factor = profile_units(field, units)
            values = np.ma.filled(variable[:], np.nan).astype(float)*factor
            if values.shape != z.shape or not np.isfinite(values).all() or np.any(values <= 0):
                raise ValueError(f'Invalid shared {field} profile.')
            path = stage/(stem+'_'+field+'_profile.h5')
            # Retain the publisher values and record their explicit source provenance
            with netCDF4.Dataset(path, 'w') as output:
                output.Model = model
                output.source_url = source_url
                output.source_filename = source_path.name
                output.source_file_sha256 = file_hash(source_path)
                output.reference_atmospheric_profile_sha256 = file_hash(reference)
                output.snapshot_label_time_s = int(token)
                output.native_time_db_s = native_time
                output.time_alignment = 'Exact filename model/snapshot match; precise time from independently matched density snapshot. Publisher supplied no time attributes.'
                output.vertical_binning = 'none'
                output.horizontal_reduction = 'Copied publisher-provided 1D profile; averaging definition was not supplied.'
                output.unit_basis = ('Source variable attribute' if getattr(variable, 'units', '') else
                    'Explicit CO5BOLD cgs convention for pressure, checked against rho*cs^2/P; plasma beta is dimensionless. Source attributes absent.')
                output.createDimension('z', len(z))
                coord = output.createVariable('z', 'f8', ('z',)); coord[:] = z; coord.units = 'cm'; coord.positive = 'up'
                value = output.createVariable(field, 'f8', ('z',)); value[:] = values; value.units = output_units
                value.long_name = 'Publisher-provided '+field+' snapshot profile'
                time = output.createVariable('time', 'f8', ()); time.assignValue(native_time); time.units = 's'
            # Read the completed profile back independently of the writer
            with netCDF4.Dataset(path) as output:
                np.testing.assert_array_equal(output['z'][:], z)
                np.testing.assert_array_equal(output[field][:], values)
            record['profiles'].append(dict(field=field, profile_file=path.name,
                profile_sha256=file_hash(path), units=output_units, vertical_levels=len(z),
                value_range=[float(values.min()), float(values.max())]))
    return record


def retrieve(reference, stage, ncks):
    '''
    Purpose
    -------
    Inspect the current remote field inventory and reduce available native 3D fields.

    Inputs
    ------
    reference: Path
        Atmospheric snapshot selecting the remote model and filename time token.

    stage: Path
        Existing directory for DDS inventory, raw cube, and standalone profiles.

    ncks: str
        NCO executable used for the native-variable OPeNDAP request.

    Outputs
    -------
    record: dict
        Available/missing server fields and validated profile records. No raw
        download occurs when none of the requested fields exists. curl and NCO
        failures propagate; the data download has a 900-second timeout.
    '''

    model, token = re.fullmatch(r'(.+)_t(\d+)s_atmos_param\.h5', reference.name).groups()
    stem = f'{model}_t{token}s'
    url = f'{BASE}/{model}/rhd_t{token}s.h5'
    # Use a fresh server inventory, not an old downloaded density cube.
    dds = subprocess.check_output(['curl', '--fail', '--silent', '--show-error',
                                  '--max-time', '90', url+'.dds'], text=True)
    (stage/(stem+'.dds')).write_text(dds)
    available = set(re.findall(r'Float(?:32|64)\s+(\w+)\[xc3\s*=', dds))
    # Resolve recognized server aliases while retaining unavailable canonical fields
    selected = {key: next((name for name in names if name in available), None)
                for key, names in FIELD_NAMES.items()}
    missing = [key for key, name in selected.items() if name is None]
    record = dict(model=model, snapshot_url=url, snapshot_label_time_s=int(token),
                  available_fields=sorted(available), missing_fields=missing, profiles=[])
    names = [name for name in selected.values() if name]
    if not names:
        return record
    raw = stage/(stem+'_raw_thermodynamic.nc')
    if not raw.is_file():
        subprocess.run([ncks, '-O', '-4', '-v',
                        ','.join(names+['xc1', 'xc2', 'xc3', 'xb1', 'xb2', 'xb3']),
                        url, str(raw)], check=True, timeout=900)
    # Use the common full-plane reducer for each available source field
    for field, name in selected.items():
        if name is None:
            continue
        with netCDF4.Dataset(raw) as source:
            actual, variable = select_field(source.variables, field, ndim=3)
            units = variable.units
            out_units, factor = profile_units(field, units)
        output = stage/(stem+'_'+field+'_profile.h5')
        record['profiles'].append(make_profile(reference, raw, output, field=field,
            variable_name=actual, expected_units=units, output_units=out_units, factor=factor))
    return record


def main():
    '''
    Purpose
    -------
    Retrieve or import thermodynamic profiles and optionally publish validated files.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Read command-line settings, write a complete staging manifest, and
        optionally copy profiles into the reference directory. Missing NCO,
        absent references, and conflicting publication destinations raise.
    '''

    # Parse source, staging, unit-contract, and publication settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path, default=DEFAULT_PROFILES)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--source-profiles', type=Path,
                        help='Directory of downloaded publisher 1D atmospheric files.')
    parser.add_argument('--source-url', default=BASE)
    parser.add_argument('--pressure-unit', help='Explicit legacy pressure unit when publisher omitted attributes.')
    args = parser.parse_args()
    args.stage.mkdir(parents=True, exist_ok=True)
    ncks = shutil.which('ncks')
    if not ncks:
        raise RuntimeError('The existing NCO ncks executable is required.')
    references = sorted(args.profiles.glob('*_atmos_param.h5'))
    if not references:
        raise ValueError('No atmospheric reference profiles found.')
    records = []
    for reference in references:
        record = (import_shared(reference, args.source_profiles/reference.name,
                                args.stage, args.source_url, args.pressure_unit)
                  if args.source_profiles else retrieve(reference, args.stage, ncks))
        records.append(record)
        print(f"{record['model']}: {len(record['profiles'])} profiles; missing {record['missing_fields']}", flush=True)
    manifest = dict(checked_utc=datetime.now(timezone.utc).isoformat(),
                    source=args.source_url, simulations=records,
                    profile_count=sum(len(r['profiles']) for r in records))
    manifest_path = args.stage/'thermodynamic_profiles_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    # Publish only on the explicit flag after all staging records are complete
    if args.publish:
        for record in records:
            for profile in record['profiles']:
                target = args.profiles/profile['profile_file']
                if target.exists():
                    raise FileExistsError(f'Refusing to overwrite existing profile: {target}')
        for record in records:
            for profile in record['profiles']:
                target = args.profiles/profile['profile_file']
                temporary = target.with_suffix('.h5.staging')
                shutil.copy2(args.stage/profile['profile_file'], temporary)
                temporary.replace(target)
        shutil.copy2(manifest_path, args.profiles/manifest_path.name)


if __name__ == '__main__':
    main()
