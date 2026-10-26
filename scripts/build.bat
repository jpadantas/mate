@echo off
setlocal enableextensions
title Build RAG Offline (onefile)

REM === paths (adjust if needed) ===
set "ROOT=%~dp0.."
set "SRC=%ROOT%\src"
set "DIST=%ROOT%\dist"
set "BUILD=%ROOT%\build"
set "EMB=%ROOT%\embeddings"
set "DOCS=%ROOT%\docs"
set "ASSETS=%ROOT%\assets"
set "VENV=%ROOT%\venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "PYI=%VENV%\Scripts\pyinstaller.exe"

echo [1/6] Activating virtual environment...
if not exist "%PYTHON%" (
    echo ERROR: venv not found. Run setup.bat first.
    exit /b 1
)

echo [2/6] Checking dependencies...
if not exist "%PYI%" (
    echo ERROR: PyInstaller not found in venv.
    echo Tip: "%PYTHON%" -m pip install pyinstaller
    exit /b 1
)

if not exist "%ASSETS%\mate_icon.ico" (
    echo ERROR: Icon not found at "%ASSETS%\mate_icon.ico".
    exit /b 1
)

echo [3/6] Cleaning old build artifacts...
if exist "%DIST%" rd /s /q "%DIST%"
if exist "%BUILD%" rd /s /q "%BUILD%"

echo [4/6] Building FAISS index...
if not exist "%EMB%" mkdir "%EMB%"
"%PYTHON%" "%SRC%\index_documents.py"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: indexing failed.
    exit /b 1
)

echo [5/6] Packaging with PyInstaller (onefile + icon + noconsole)...
REM Notes:
REM  - --icon EMBEDS the icon into the executable (taskbar uses this icon)
REM  - --add-data copies the assets folder into the bundle (used by Tk at runtime)
REM  - the --add-data separator on Windows is ';' (source;destination)
"%PYTHON%" -m PyInstaller "%SRC%\gui.py" ^
  --onefile ^
  --noconsole ^
  --name mate ^
  --distpath "%DIST%" ^
  --workpath "%BUILD%" ^
  --clean ^
  --icon "%ASSETS%\mate_icon.ico" ^
  --add-data "%ASSETS%;assets"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: build failed.
    exit /b 1
)

echo [6/6] Testing binary...
if exist "%DIST%\mate.exe" (
    echo Success: "%DIST%\mate.exe" generated.
) else (
    echo ERROR: mate.exe not found in "%DIST%".
    exit /b 1
)
echo Tip: If the taskbar still shows the Python icon:
echo   - make sure gui.py sets the AppUserModelID (ctypes) before creating windows;
echo   - run the .exe (not the .py) and close any old Python windows.

echo Build completed.
exit /b 0
