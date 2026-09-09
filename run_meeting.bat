@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo       Meeting Minutes (MoM) Automatic Generator
echo ========================================================
echo.

REM 1. Check for Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on your computer!
    echo.
    echo How to fix:
    echo 1. Download Python from: https://www.python.org/downloads/
    echo 2. During installation, CHECK the box: "Add python.exe to PATH"
    echo 3. Restart your computer or terminal and try again.
    echo.
    echo See README.md for full step-by-step help.
    echo.
    pause
    exit /b 1
)

REM 2. Check for FFmpeg
ffmpeg -version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] FFmpeg was not found on your computer!
    echo.
    echo How to fix:
    echo Open PowerShell and run: winget install Gyan.FFmpeg
    echo Then restart your terminal or this script.
    echo.
    echo See README.md for full step-by-step help.
    echo.
    pause
    exit /b 1
)

REM 3. Check for Antigravity CLI
agy --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Antigravity CLI 'agy' was not found in PATH!
    echo The AI summary step requires Antigravity to be installed.
    echo Please check README.md for installation details.
    echo.
)

REM 4. Run the pipeline
if "%~1"=="" (
    echo [INFO] Searching for latest recording in D:\OBS Captures...
    echo Tip: You can also drag and drop any video file onto this batch file.
    echo.
    python process_meeting.py
) else (
    echo [INFO] Processing provided video file or options...
    echo.
    python process_meeting.py %*
)

echo.
echo ========================================================
if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] Meeting processing complete!
    echo Your generated Minutes of Meeting is in: docs\mom\
) else (
    echo [NOTICE] Process finished with exit code %ERRORLEVEL%.
    echo Check any messages above.
)
echo ========================================================
echo.
pause
