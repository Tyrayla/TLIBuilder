@echo off
echo Installing PyInstaller...
pip install pyinstaller --quiet

echo.
echo Building TLI Planner...
python -m PyInstaller ^
  --onedir ^
  --noconsole ^
  --collect-all dearpygui ^
  --name "TLI Planner" ^
  main.py

echo.
echo Done! Executable is at: dist\TLI Planner\TLI Planner.exe
pause
