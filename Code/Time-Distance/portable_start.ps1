# Purpose
# -------
# Start the portable tools on Windows without administrator privileges.
#
# Inputs
# ------
# Remaining script arguments are forwarded to portable_launcher.py.
#
# Outputs
# -------
# Return the launcher exit code; offer local uv/Python downloads only when
# no compatible interpreter exists, and report setup failures in red.

# Invoked by Start Tools.bat; does not require Python or administrator privileges.
# Resolve the bundle root and define the isolated interpreter compatibility check
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$launcher = Join-Path $root 'Code\Time-Distance\portable_launcher.py'
$check = 'import sys, venv, ensurepip; assert sys.version_info[:2] in {(3,10),(3,11)}'
Set-Location -LiteralPath $root

# Purpose
# -------
# Locate a usable Python 3.10/3.11 without downloading it.
#
# Inputs
# ------
# Read bundle root and isolated interpreter-check code from the enclosing script.
#
# Outputs
# -------
# Return an executable path from the private venv, py launcher, or PATH;
# ignore incompatible candidates and WindowsApps aliases.
function Find-Python {
    $ErrorActionPreference = 'Continue' # Missing/incompatible interpreters are expected during discovery.
    # Prefer the private environment before searching py and PATH candidates
    $private = Join-Path $root '.local\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $private) {
        & $private -I -c $check 2>$null
        if ($LASTEXITCODE -eq 0) { return $private }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.11', '-3.10')) {
            $found = & py $version -I -c ($check + '; print(sys.executable)') 2>$null
            if ($LASTEXITCODE -eq 0) { return $found }
        }
    }
    foreach ($name in @('python3.11', 'python3.10', 'python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notlike '*\WindowsApps\*') {
            $found = & $command.Source -I -c ($check + '; print(sys.executable)') 2>$null
            if ($LASTEXITCODE -eq 0) { return $found }
        }
    }
}

# Purpose
# -------
# Locate Python 3.11 already installed by this bundle private uv.
#
# Inputs
# ------
# Read the enclosing uv executable path.
#
# Outputs
# -------
# Return the managed interpreter path on success or no value when unavailable.
# The uv query explicitly disables Python downloads.
function Find-ManagedPython {
    $ErrorActionPreference = 'Continue'
    $found = & $uv python find --no-config --managed-python --no-python-downloads --no-project 3.11 2>$null
    if ($LASTEXITCODE -eq 0) { return $found }
}

# Reuse an existing compatible interpreter before asking to install a runtime
try {
    $python = Find-Python
    if ($python) {
        & $python $launcher @args
        exit $LASTEXITCODE
    }
# Keep uv, managed Python, and download caches inside the portable bundle
    $env:UV_UNMANAGED_INSTALL = Join-Path $root '.local\uv'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $root '.local\python'
    $env:UV_CACHE_DIR = Join-Path $root '.local\uv-cache'
    $env:UV_PYTHON_INSTALL_BIN = '0'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    $uv = Join-Path $env:UV_UNMANAGED_INSTALL 'uv.exe'
    if (Test-Path -LiteralPath $uv) {
        $python = Find-ManagedPython
        if ($python) {
            & $python $launcher @args
            exit $LASTEXITCODE
        }
    }
# Explain runtime downloads before accepting an explicit affirmative response
    Write-Host "No usable Python 3.10/3.11 was found."
    Write-Host "Setup will download Python 3.11 and uv from Astral, then the required"
    Write-Host "scientific libraries from PyPI into this tools folder (.local)."
    Write-Host "Your other Python environments and system settings will stay unchanged."
    Write-Host "Internet access is required for downloads."
    $answer = Read-Host 'Allow environment setup and downloads? [y/N]'
    if ($answer -notmatch '^(y|yes)$') { Write-Host 'Setup cancelled. Nothing was installed.'; exit 1 }
    # Download the pinned uv installer only when the private executable is absent
    if (-not (Test-Path -LiteralPath $uv)) {
        New-Item -ItemType Directory -Force -Path $env:UV_UNMANAGED_INSTALL | Out-Null
        $installer = Join-Path $env:UV_UNMANAGED_INSTALL 'installer.ps1'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://releases.astral.sh/github/uv/releases/download/0.13.3/uv-installer.ps1' -OutFile $installer
        & $installer
        if (-not (Test-Path -LiteralPath $uv)) { throw 'The private uv installation failed.' }
    }
    # Install/find managed Python and forward the accepted setup state
    & $uv python install --no-config --no-bin 3.11
    if ($LASTEXITCODE -ne 0) { throw 'Python download failed. Check your connection and run Start Tools again.' }
    $python = & $uv python find --no-config --managed-python --no-python-downloads --no-project 3.11
    if ($LASTEXITCODE -ne 0) { throw 'The downloaded Python could not be found.' }
    & $python $launcher --setup-approved @args
    exit $LASTEXITCODE
# Convert setup exceptions to a visible error and nonzero launcher status
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
