# Persistent Filter Cache

## Scope

The pipeline now persists generated filters in `Data/Filters/` and reuses them when the same filter is requested again.

Cached artifacts currently cover:

- Gaussian Fourier-space filters built by `AGWFilter.build_gaussian_filter`.
- Magnetogram boolean masks built by `AGWFilter.load_magnetogram_filter_masks`.

The cache is transparent to downstream cross-correlations, phase differences, FITS outputs, plots, names, and metadata. The filtering APIs still return the same arrays as before; cache state is exposed only through diagnostic keys on `AGWFilter.data`.

## Cache Keys

Each cache filename has a readable slug plus the full SHA-256 digest over a canonical JSON metadata payload.

Gaussian cache metadata includes:

- cache schema version and filter algorithm id,
- filter type,
- Fourier filter shape in `[x, y, t]`,
- cadence `dt`,
- pixel scale `dx_Mm`,
- `central_f`, `width_f`, `central_k`, and `width_k`,
- Fourier grid mode.

Magnetogram mask cache metadata includes:

- cache schema version and mask algorithm id,
- filter type,
- `selection` and `threshold_G`,
- mask source shapes,
- SHA-256 hashes of the absolute magnetic-field arrays used to build the masks.

The human-readable filename fragments intentionally reuse the existing output slug conventions:

- Gaussian parameters use `gauss_ck_<central_k>_wk_<width_k>_cf_<central_f>_wf_<width_f>`.
- Magnetogram selections use `b_le_<threshold>g` for nonmagnetic outputs and `b_gt_<threshold>g` for magnetic outputs.

Example filenames:

- `Data/Filters/gaussian_filter_gauss_ck_2_wk_2_cf_1_5_wf_1_5_shape_6x4x5_dt_1_dx_0_5_b6860da3532b6501535c06eb8915871103dc9ce43aa68c72743e69e74b101482.npy`
- `Data/Filters/magnetogram_filter_b_le_0_75g_v1_shape_2x2x2_v2_shape_2x2x2_4a2c775d1b5e5e68fa4bfe83869d7fd32adf053e3f6707f83b8358a246e498c6.npz`

## I/O Safety

Gaussian filters are stored as `.npy` for fast reads. Magnetogram mask pairs are stored as compressed `.npz` files because boolean masks compress well.

Writes are atomic:

1. The array is written to a unique temporary file in `Data/Filters/`.
2. The temporary file is atomically moved into place with `os.replace`.
3. If another worker already wrote the same cache artifact, the temporary file is discarded.

This avoids partially-written cache files for future threaded or process-based runs.

## Validation

Implemented runtime tests cover:

- Gaussian cache reuse with no second call to `spectral_analysis.create_filter`.
- Shape-specific Gaussian cache keys.
- Magnetogram cache reuse with no second call to the mask-threshold builder.
- Existing single-cube magnetogram modes and zero-field behavior.

Validation command:

```bash
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3 -m pytest Code/Tests/test_time_distance_runtime.py -q
```

Result:

```text
25 passed, 2 warnings
```
