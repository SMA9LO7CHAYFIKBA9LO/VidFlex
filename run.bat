@echo off
echo =======================================================
echo  MediaFlow - Setup & Run
echo =======================================================

echo [1/3] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed. Make sure Python is installed.
  pause
  exit /b 1
)

echo.
echo [2/3] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
  echo WARNING: FFmpeg not found in PATH.
  echo          The Media Converter feature requires FFmpeg.
  echo          Download it from https://ffmpeg.org/download.html
  echo          and add it to your system PATH.
  echo.
)

echo [3/3] Starting Flask server...
echo  Open your browser at: http://127.0.0.1:5000
echo  Press CTRL+C to stop.
echo.
python app.py
pause
