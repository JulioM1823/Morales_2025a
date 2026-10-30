# Distributing the HTML and Bokeh tools

The distribution is built by `package_komega_tools.py`. It packages the existing
figure HTML, image assets, saved plot exports, Python tools, and dispersion-model
source. The full project `Data` directory is transferred separately; it is too
large to duplicate inside the tools ZIP.

```sh
python Code/Time-Distance/package_komega_tools.py --output Deliverables/Morales-Tools
```

The output directory and ZIP must not already exist. Existing research HTML and
scientific products are not overwritten. The distribution's index links to the
current galleries and saved exports. Every distributed HTML page checks the
shared local setup, and its Bokeh bridge uses the port selected by the launcher.

Recipients extract the whole ZIP, run their platform's `Start Tools` launcher,
and enter the full path to their local **Data** directory. The first launch asks
permission to create a private environment and install the pinned libraries in
`.local/venv`. A usable existing Python 3.10 or 3.11 is reused; otherwise the native
shell/PowerShell bootstrap downloads uv 0.13.3 and Python 3.11 from Astral, after
asking permission. Downloads require internet. The uv installer uses
`UV_UNMANAGED_INSTALL`; managed Python uses `UV_PYTHON_INSTALL_DIR`, with executable
and Windows registry installation disabled. Everything is kept inside `.local`.
No administrator account, global package install, or shell-profile change is
required. Dependencies come from PyPI as binary wheels. The pinned uv release and
installer behavior follow the [official release](https://github.com/astral-sh/uv/releases/tag/0.13.3)
and [installer documentation](https://docs.astral.sh/uv/reference/installer/).
Declining setup creates no environment. An interrupted install is retried on the
next run, and changes to the library requirements ask permission again.
The launcher stays open while Python callbacks are used. After that,
the saved directory and environment are reused. HTML alone cannot execute the
existing Python callbacks or start a local Python process.

`portable_paths.py` enables translations only when the launcher sets
`MORALES_PORTABLE_ROOT`. Saved launch contexts, numerical settings, dataset IDs,
and provenance remain intact. The manifest maps their original I/O paths to the
recipient's Data tree. Existing research checkouts use their ordinary resolvers.
The solver is included under `vendor/Vesa_2026`, with no separate checkout needed.

The loopback-only server provides `/setup`, `/portable/status`, and `/files/`.
Setup writes its selection atomically into `.local/settings.json`, checks the
presence and byte sizes of the recorded source files, and reports missing files.
That check is not a checksum validation. Configuration writes require the local
page's token and matching origin. Settings and generated caches are not shipped.

## Consolidated source locations

The canonical source is this project's `Data` directory. The following previous
locations are now forwarding links to one physical copy under that directory:

- `~/Research/Projects/Morales_2025a/Data/co5bold` → `Data/co5bold`
- The neighboring `Vesa_2026/Data` → `Data/observations_raw` (71 files)
- `~/Research/Projects/Morales_2025a/Data/phase_coherence` → `Data/phase_coherence` (4 files)

The two new moves are recorded in `Data/json_files/observations_raw_relocation.json`
and `Data/json_files/phase_coherence_relocation.json`. The observing directory was
atomically renamed on the same filesystem and verified by unchanged inodes,
sizes, and modification times; its full checksum read stalled on a cloud-backed
file. That file was subsequently downloaded explicitly in Finder and its full
content read and SHA-256 calculation succeeded; the evidence is in
`Code/Tests/validation/portable_observing_cube_read.json`.
The four phase/coherence files were also SHA-256 verified. Identity mapping
preserves existing IDs and historical references across both relocations.

When transferring Data, transfer actual file contents rather than unresolved
symbolic links. Source Data includes older aliases to absent intermediate
products; saved contexts with exact original input references can rebuild their
native baseline. No unrelated dataset is substituted. The bundle records dangling
historical figure aliases separately; they are not treated as active HTML resources.

## Validation

`Code/Tests/test_portable_tools.py` covers a differently located Data directory,
spaces and Unicode paths, unchanged IDs, invalid directory handling, persistent
setup, request-origin checks, shared HTML setup, and the portable launch bridge.
It also covers setup refusal before installation, failed-install retry markers,
and reuse without a second prompt. The native macOS bootstrap was tested with
Python absent from PATH: it downloaded Python 3.11, installed all pinned libraries,
and passed scientific imports and a subsequent launch with stdin closed.
The relocation tests include cloud-file moves without content reads.

```sh
python Code/Tests/audit_portable_tools.py --bundle Deliverables/Morales-Tools \
  --data Data --report Code/Tests/validation/portable_context_audit.json
```

The audit checks HTML resources, saved dataset IDs, and the presence of recorded
inputs without repeating scientific calculations. The live acceptance check
uses the gallery, height-pair view, individual figure, and Bokeh bridge, and
changes a Gaussian parameter through the existing Python callback. Runtime and
browser validation were performed on macOS; Windows and Linux launchers are
included but were not exercised on those operating systems.
