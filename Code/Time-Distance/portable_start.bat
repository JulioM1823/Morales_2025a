@echo off
REM Purpose
REM -------
REM Forward portable Windows launch requests to the bundled PowerShell entry point.
REM
REM Inputs
REM ------
REM All command-line arguments are passed unchanged to portable_start.ps1.
REM
REM Outputs
REM -------
REM Return the PowerShell exit code; pause the console only after a failure.

REM Run the package-relative launcher without loading a user PowerShell profile
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Code\Time-Distance\portable_start.ps1" %*
REM Capture the exit status before an optional interactive pause
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
