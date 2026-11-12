@echo off
rem mf launcher for Windows. Same usage as macOS: mf new NAME -b PS --platform dy
rem Python lookup order: .venv next to this file -> %USERPROFILE%\mediaflow\.venv -> py -3 -> python
setlocal
set "HERE=%~dp0"
set "SCRIPT=%HERE%mf.py"

if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)
if exist "%USERPROFILE%\mediaflow\.venv\Scripts\python.exe" (
  "%USERPROFILE%\mediaflow\.venv\Scripts\python.exe" "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)
python "%SCRIPT%" %*
exit /b %ERRORLEVEL%
