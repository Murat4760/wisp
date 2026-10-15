@echo off
cd /d "%~dp0"
echo Installing build tools...
pip install -r requirements.txt pyinstaller || goto :fail
echo Building Wisp.exe...
pyinstaller --noconfirm --onefile --windowed --name Wisp ^
  --hidden-import pystray._win32 --collect-submodules send2trash ^
  wisp.py || goto :fail
copy /y .env.example dist\.env.example >nul
if exist .env copy /y .env dist\.env >nul
echo.
echo Done: dist\Wisp.exe  (keep .env next to it)
pause
exit /b 0
:fail
echo Build failed - copy the error above and send it to Claude.
pause
exit /b 1
