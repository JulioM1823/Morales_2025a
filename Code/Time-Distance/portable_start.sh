#!/bin/sh
# Purpose
# -------
# Start the portable tools with a compatible existing or package-local Python.
#
# Inputs
# ------
# Launcher arguments are forwarded unchanged; run this copied file from the bundle root.
#
# Outputs
# -------
# Run portable_launcher.py and return its exit status. When Python is absent,
# ask before downloading uv/Python into .local; cancellation returns status 1.

# Copied to the bundle root as Start Tools.command and Start Tools.sh.
# Resolve the bundle root before locating its launcher and runtime checks
cd -- "$(dirname -- "$0")" || exit 1
root=$(pwd -P)
launcher="$root/Code/Time-Distance/portable_launcher.py"
check='import sys, venv, ensurepip; sys.exit(sys.version_info[:2] not in {(3,10),(3,11)})'

# Purpose
# -------
# Find Python 3.10/3.11 or perform the explicitly accepted local runtime setup.
#
# Inputs
# ------
# All arguments: portable-launcher command-line arguments.
#
# Outputs
# -------
# Run the launcher with the selected interpreter and return its exit status.
# Downloads are confined to this bundle and occur only after the prompt is accepted.
main() {
    # Prefer the bundled environment, then compatible interpreters already on PATH
    for candidate in "$root/.local/venv/bin/python" python3.11 python3.10 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -I -c "$check" 2>/dev/null; then
            "$candidate" "$launcher" "$@"
            return $?
        fi
    done
    # uv and all downloaded runtimes remain inside this bundle; no shell/profile edits.
    UV_UNMANAGED_INSTALL="$root/.local/uv"
    UV_PYTHON_INSTALL_DIR="$root/.local/python"
    UV_CACHE_DIR="$root/.local/uv-cache"
    UV_PYTHON_INSTALL_BIN=0
    UV_PYTHON_INSTALL_REGISTRY=0
    export UV_UNMANAGED_INSTALL UV_PYTHON_INSTALL_DIR UV_CACHE_DIR
    export UV_PYTHON_INSTALL_BIN UV_PYTHON_INSTALL_REGISTRY
    uv="$UV_UNMANAGED_INSTALL/uv"
    # Reuse an existing managed runtime without initiating a download
    if [ -x "$uv" ]; then
        python=$("$uv" python find --no-config --managed-python --no-python-downloads --no-project 3.11 2>/dev/null) && {
            "$python" "$launcher" "$@"
            return $?
        }
    fi
    # Explain the local installation and require an affirmative setup response
    printf '%s\n' 'No usable Python 3.10/3.11 was found.' \
        'Setup will download Python 3.11 and the uv installer from Astral, then the' \
        'required scientific libraries from PyPI into this tools folder (.local).' \
        'Your other Python environments and system settings will stay unchanged.' \
        'Internet access is required for downloads.'
    printf 'Allow environment setup and downloads? [y/N] '
    IFS= read -r answer || answer=n
    case "$answer" in y|Y|yes|YES|Yes) ;; *) printf '%s\n' 'Setup cancelled. Nothing was installed.'; return 1 ;; esac
    # Retrieve the pinned uv installer only when the private uv executable is absent
    if [ ! -x "$uv" ]; then
        mkdir -p "$UV_UNMANAGED_INSTALL" || return 1
        installer="$UV_UNMANAGED_INSTALL/installer.sh"
        url='https://releases.astral.sh/github/uv/releases/download/0.13.3/uv-installer.sh'
        if command -v curl >/dev/null 2>&1; then
            curl --proto '=https' --tlsv1.2 -fLsS "$url" -o "$installer" || return 1
        elif command -v wget >/dev/null 2>&1; then
            wget -q "$url" -O "$installer" || return 1
        else
            printf '%s\n' 'Setup requires curl or wget to download Python.'; return 1
        fi
        sh "$installer" || return 1
    fi
    # Install/find managed Python, then pass the accepted setup state to the launcher
    "$uv" python install --no-config --no-bin 3.11 || return 1
    python=$("$uv" python find --no-config --managed-python --no-python-downloads --no-project 3.11) || return 1
    "$python" "$launcher" --setup-approved "$@"
}

# Preserve the launcher status and hold an interactive error window open
main "$@"
result=$?
if [ "$result" -ne 0 ] && [ -t 0 ]; then
    printf '\nPress Enter to close.'
    IFS= read -r answer
fi
exit "$result"
