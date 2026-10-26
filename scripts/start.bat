@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Start MATE - backend + GUI

rem --- PATHS ---
set "ROOT=%~dp0.."
set "SRC=%ROOT%\src"
set "DIST=%ROOT%\dist"
set "VENV=%ROOT%\venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "PYTHONW=%VENV%\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
  echo ERROR: venv not found in "%VENV%".
  echo Run setup.bat first.
  exit /b 1
)

rem --- START BACKEND ---
echo Starting backend...
start "MATE Backend" "%PYTHON%" -m uvicorn app:app --app-dir "%SRC%" --host 127.0.0.1 --port 8000 --log-level debug

rem --- WAIT FOR /health (optional with curl) ---
where curl >NUL 2>&1
if errorlevel 1 (
  echo Warning: curl not found. Waiting 5 seconds before opening the GUI...
  timeout /t 5 >NUL
) else (
  echo Waiting for backend to respond at /health, timeout about 30s...
  set "OK=0"
  for /L %%I in (1,1,30) do (
    curl -s -f http://127.0.0.1:8000/health >NUL 2>&1
    if !errorlevel! EQU 0 (
      set "OK=1"
      goto READY
    )
    timeout /t 1 >NUL
  )
  :READY
  if "!OK!" NEQ "1" (
    echo Warning: could not confirm backend status. Opening GUI anyway...
  )
)

rem --- START GUI (prefer EXE for correct icon) ---
if exist "%DIST%\mate.exe" (
  echo Opening GUI: "%DIST%\mate.exe"
  start "MATE GUI" "%DIST%\mate.exe"
) else (
  echo Warning: mate.exe not found in "%DIST%".
  echo Opening in dev mode with pythonw or python.
  if exist "%PYTHONW%" (
    start "MATE GUI dev" "%PYTHONW%" "%SRC%\gui.py"
  ) else (
    start "MATE GUI dev" "%PYTHON%" "%SRC%\gui.py"
  )
)

exit /b 0
