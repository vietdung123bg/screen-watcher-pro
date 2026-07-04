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

:: (Re)install deps when the venv is fresh OR requirements.txt changed since the last
:: successful install. The old check only looked at the marker file, so packages added
:: to requirements.txt later (notebook, pywebview, pytest) were never installed. mtimes
:: are compared with PowerShell (reliable across directories).
set "NEED_DEPS=1"
if not exist ".venv\.deps.ok" goto deps_check_done
set "REQ_NEWER=0"
for /f "usebackq delims=" %%x in (`powershell -NoProfile -Command "if((Get-Item 'requirements.txt').LastWriteTime -gt (Get-Item '.venv\.deps.ok').LastWriteTime){'1'}else{'0'}" 2^>nul`) do set "REQ_NEWER=%%x"
set "NEED_DEPS="
if "%REQ_NEWER%"=="1" set "NEED_DEPS=1"
:deps_check_done
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

:: --- Session log: capture everything this run prints (app actions + LLM tool
:: calls: name, params, response, output) to a per-run file while still showing it
:: in the console. The full cross-process log (desktop app + the API server it spawns,
:: both write there) is logs\app_YYYYMMDD.log.
if not exist "logs" md "logs"
set "TS="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul`) do set "TS=%%i"
if "%TS%"=="" set "TS=%RANDOM%"
set "RUNLOG=%CD%\logs\run_%MODE%_%TS%.log"

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
echo [run] Starting Screen Watcher desktop app (auto-starts API server + Jupyter)...
echo [run] Session log : "%RUNLOG%"
echo [run] Unified log : "%CD%\logs\app_<YYYYMMDD>.log"  (app actions + LLM tool calls, desktop + API)
"%VENV_PY%" -u run.py 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%RUNLOG%'"
exit /b %ERRORLEVEL%

:api
echo [run] Starting API server at http://127.0.0.1:8000
echo [run] Session log : "%RUNLOG%"
"%VENV_PY%" -u -m uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%RUNLOG%'"
exit /b %ERRORLEVEL%

:notebook
echo [run] Opening Jupyter notebook chatbox...
echo [run] Session log : "%RUNLOG%"
"%VENV_PY%" -u -m jupyter notebook notebooks\chatbox.ipynb 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%RUNLOG%'"
exit /b %ERRORLEVEL%

:demo
echo [run] Starting API server in a separate window, then opening notebook...
start "Screen Watcher API" "%ComSpec%" /k ""%~f0" api"
timeout /t 3 /nobreak >nul
echo [run] Session log : "%RUNLOG%"
"%VENV_PY%" -u -m jupyter notebook notebooks\chatbox.ipynb 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%RUNLOG%'"
exit /b %ERRORLEVEL%

:test
echo [run] Running tests...
"%VENV_PY%" -m pytest
exit /b %ERRORLEVEL%

