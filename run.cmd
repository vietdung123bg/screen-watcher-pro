@echo off
setlocal

cd /d "%~dp0"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=desktop"

set "PYTHON=python"
where python >nul 2>nul
if errorlevel 1 set "PYTHON=py -3"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment...
  %PYTHON% -m venv .venv
  if errorlevel 1 exit /b %ERRORLEVEL%
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

:: (Re)install deps when the venv is fresh OR requirements.txt changed since the
:: last successful install. The old check only looked at the marker file, so newly
:: added dependencies (e.g. notebook, pywebview, pytest) were never installed.
set "NEED_DEPS=1"
if exist ".venv\.deps.ok" (
  set "NEED_DEPS="
  for /f "delims=" %%F in ('dir /b /o-d "requirements.txt" ".venv\.deps.ok" 2^>nul') do (
    if not defined _NEWEST_SEEN (
      set "_NEWEST_SEEN=1"
      if /I "%%F"=="requirements.txt" set "NEED_DEPS=1"
    )
  )
  set "_NEWEST_SEEN="
)
if defined NEED_DEPS (
  echo [setup] Installing/updating dependencies...
  "%VENV_PY%" -m pip install --upgrade pip
  if errorlevel 1 exit /b %ERRORLEVEL%
  "%VENV_PY%" -m pip install -r requirements.txt
  if errorlevel 1 exit /b %ERRORLEVEL%
  echo ok > ".venv\.deps.ok"
)

if not exist "config\rules.yaml" (
  echo [setup] Creating config\rules.yaml from example...
  copy "config\rules.example.yaml" "config\rules.yaml" >nul
)

if not exist ".ocr.env" (
  echo [setup] Creating .ocr.env from example...
  copy ".ocr.env.example" ".ocr.env" >nul
)

if not exist ".smtp.env" (
  echo [setup] Creating .smtp.env from example...
  copy ".smtp.env.example" ".smtp.env" >nul
)

if not exist ".chatbot.env" (
  echo [setup] Creating .chatbot.env from example...
  copy ".chatbot.env.example" ".chatbot.env" >nul
)

if /I "%MODE%"=="desktop" goto desktop
if /I "%MODE%"=="app" goto desktop
if /I "%MODE%"=="api" goto api
if /I "%MODE%"=="server" goto api
if /I "%MODE%"=="notebook" goto notebook
if /I "%MODE%"=="jupyter" goto notebook
if /I "%MODE%"=="demo" goto demo
if /I "%MODE%"=="test" goto test
if /I "%MODE%"=="tests" goto test

echo Usage:
echo   run.cmd [desktop^|api^|notebook^|demo^|test]
exit /b 2

:desktop
echo [run] Starting Screen Watcher desktop app...
"%VENV_PY%" run.py
exit /b %ERRORLEVEL%

:api
echo [run] Starting API server at http://127.0.0.1:8000
"%VENV_PY%" -m uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1
exit /b %ERRORLEVEL%

:notebook
echo [run] Opening Jupyter notebook chatbox...
"%VENV_PY%" -m jupyter notebook notebooks\chatbox.ipynb
exit /b %ERRORLEVEL%

:demo
echo [run] Starting API server in a separate window, then opening notebook...
start "Screen Watcher API" "%ComSpec%" /k ""%~f0" api"
timeout /t 3 /nobreak >nul
"%VENV_PY%" -m jupyter notebook notebooks\chatbox.ipynb
exit /b %ERRORLEVEL%

:test
echo [run] Running tests...
"%VENV_PY%" -m pytest
exit /b %ERRORLEVEL%

