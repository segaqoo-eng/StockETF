@echo off
setlocal
cd /d "%~dp0"

REM Force Python stdout/stderr to UTF-8 so Chinese characters survive
REM cmd.exe's default cp950 codec on Traditional Chinese Windows.
set PYTHONIOENCODING=utf-8

REM === StockETF daily update (one-click) ===
REM   1) Scrape ETF holdings -> data/latest.json
REM   2) Generate post summary -> status_today.md + my_status.md
REM   3) Start local web server + open browser
REM Headless mode: set SKIP_PAUSE=1 to skip server, browser, and pause
REM Full output is appended to logs/update_YYYY-MM-DD.log

REM --- Get today's date (yyyy-MM-dd) ---
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
if not exist logs mkdir logs
set LOG=logs\update_%TODAY%.log

echo === StockETF daily update [%TODAY%] ===
echo Log: %LOG%
echo.

REM --- Activate venv ---
if not exist .venv\Scripts\activate.bat (
  echo [ERROR] .venv not found. Run init.bat first.
  if not "%SKIP_PAUSE%"=="1" pause
  exit /b 1
)
call .venv\Scripts\activate.bat

REM --- 1/3 Update ETF holdings ---
echo [1/3] Updating ETF holdings (main.py)...
echo. >> "%LOG%"
echo ====== %DATE% %TIME% main.py ====== >> "%LOG%"
python scripts\tee.py main.py "%LOG%"
if errorlevel 1 (echo   [FAIL] see %LOG%) else (echo   [OK])

REM --- 2/3 Generate status reports ---
echo [2/3] Generating status reports...
echo. >> "%LOG%"
echo ====== %DATE% %TIME% generate_status.py ====== >> "%LOG%"
python scripts\generate_status.py >> "%LOG%" 2>&1
if errorlevel 1 (echo   [FAIL] status_today see %LOG%) else (echo   [OK] status_today.md)

echo. >> "%LOG%"
echo ====== %DATE% %TIME% my_status.py ====== >> "%LOG%"
python scripts\my_status.py >> "%LOG%" 2>&1
if errorlevel 1 (echo   [FAIL] my_status see %LOG%) else (echo   [OK] my_status.md)

REM --- 3/3 Start web server + open browser (skipped in headless mode) ---
if "%SKIP_PAUSE%"=="1" (
  echo [3/3] Headless mode - skipping web server
  goto :SUMMARY
)

echo [3/3] Starting local web server and opening browser...
start "StockETF Server" /B python scripts\web_server.py 8000 >> "%LOG%" 2>&1
timeout /t 2 /nobreak > nul
start http://localhost:8000

:SUMMARY
echo.
echo === Done ===
echo Summary: status_today.md  (copy to FB)
if not "%SKIP_PAUSE%"=="1" echo Site:    http://localhost:8000
echo Log:     %LOG%

if not "%SKIP_PAUSE%"=="1" (
  echo.
  echo Press any key to close window (server will stop)...
  pause > nul
)
