@echo off
REM Convenience wrapper around build-windows.ps1 for users who prefer cmd.exe.
REM Forwards all arguments to the PowerShell script.

setlocal
set "HERE=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%build-windows.ps1" %*
exit /b %ERRORLEVEL%
