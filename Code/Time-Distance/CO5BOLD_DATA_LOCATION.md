# CO5BOLD source data

The original collection now lives inside this project:

```text
Data/co5bold/
  hx/{10G,50G,100G}/simulation_*.nc
  vx/{10G,50G,100G}/simulation_*.nc
  z0/0G/simulation_*.nc
  co5bold_1d_profiles/
    *_atmos_param.h5
    *_density_profile.h5
    *_pressure_profile.h5
    *_plasma_beta_profile.h5
    thermodynamic_profile_sources/
  hx/file_names_hx_*.txt
  vx/file_names_vx_*.txt
  z0/file_names_z0_*.txt
```

These are source cubes, native profiles, download lists, and their original
provenance manifests. Calculated products remain under `Data/simulations/`,
`Data/observations/`, and the existing cache directories. Scientific source files
were moved intact; their internal provenance attributes were not rewritten.

`config.py` derives `co5bold_batch_root`, the default cube, all batch cube paths,
and the profile directory from its project directory. `data_locations.py` owns
the current locations and verified relocation lookup. The HTML recovery CLI,
download scripts, and executable notebook cells use the project copy. The batch
downloader also accepts `CO5BOLD_DATA_ROOT` as an explicit override.

## Relocation and compatibility

`move_co5bold_data.py` records every source file's SHA-256, size, inode, and
modification time before moving the directory. It requires the same filesystem
and an absent destination; it does not fall back to copying large files. After
the move it verifies every checksum and records the result in
`Data/json_files/co5bold_relocation.json`.

The former directory at `~/Research/Projects/Morales_2025a/Data/co5bold` is now
a forwarding symlink to the project copy. It holds no second set of data.
This preserves historical HTML launch contexts, optimized-filter records,
NetCDF/HDF5 provenance attributes, saved input references, and external notebooks.
Their historical source strings remain truthful and usable.

Only files listed in the verified relocation manifest keep their original
logical dataset and cache identities. Physical reads use the current location.
`output_paths.py` and `observation_datasets.py` preserve these identities;
new output metadata records `source_locations` separately from stable identity
labels. Atmospheric source-version labels also remain stable. Existing cache
validation continues to check file versions and checksums; changed input data
invalidate reuse. New files under `Data/co5bold/` receive their own identities.

The forwarding link and relocation manifest are compatibility resources. Removing
either can break historical references or prevent reuse of earlier caches.
