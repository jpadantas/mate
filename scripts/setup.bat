@echo off
setlocal enableextensions
title Setup RAG Offline

REM === Project root (batch file folder) ===
REM Resolve absolute ROOT path without relying on relative slashes
pushd "%~dp0"
set "ROOT=%CD%\.."
popd

set "VENV=%ROOT%\venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"
set "REQ=%ROOT%\requirements.txt"

REM Set wheels flag only if the folder exists
set "WHEELS_FLAG="
if exist "%ROOT%\wheels\" (
    set "WHEELS_FLAG=--no-index --find-links \"%ROOT%\wheels\""
)

echo [1/4] Checking virtual environment...
if exist "%VENV%\Scripts\activate.bat" (
    echo Venv already exists.
) else (
    echo Creating venv at "%VENV%" ...
    python -m venv "%VENV%"
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: failed to create venv.
        exit /b 1
    )
)

echo [2/4] Updating pip/setuptools...
"%PYTHON%" -m pip install --upgrade pip setuptools wheel %WHEELS_FLAG%
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: update via local wheels failed or no wheels found. Trying online...
    "%PYTHON%" -m pip install --upgrade pip setuptools wheel
)

echo [3/4] Installing project dependencies...
if exist "%REQ%" (
    if defined WHEELS_FLAG (
        "%PIP%" install -r "%REQ%" %WHEELS_FLAG%
        if %ERRORLEVEL% NEQ 0 (
            echo WARNING: offline installation failed. Trying online...
            "%PIP%" install -r "%REQ%"
            if %ERRORLEVEL% NEQ 0 (
                echo ERROR: failed to install dependencies.
                exit /b 1
            )
        )
    ) else (
        echo No local wheels folder found. Installing online...
        "%PIP%" install -r "%REQ%"
        if %ERRORLEVEL% NEQ 0 (
            echo ERROR: failed to install dependencies.
            exit /b 1
        )
    )
) else (
    echo No requirements.txt found; skipping.
)

echo [4/4] Setting up offline cache for SentenceTransformers (optional)...
REM If you have locally downloaded models, uncomment and adjust:
REM set "SENTENCE_TRANSFORMERS_HOME=%ROOT%\models"

echo Setup completed.
exit /b 0
