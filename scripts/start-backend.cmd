@echo off
rem Starts PostgreSQL + FreelanceHub API with Docker Compose and waits until the API is healthy.
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
set "LOG=logs\backend-start.log"
echo [%date% %time%] Starting FreelanceHub backend > "%LOG%"

docker version >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: Docker is not running. Start Docker Desktop and try again. >> "%LOG%"
  goto done
)
if not exist .env (
  echo ERROR: .env not found. Copy .env.example to .env and fill in the secrets. >> "%LOG%"
  goto done
)

echo --- docker compose up --build --- >> "%LOG%"
docker compose up -d --build >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: docker compose up failed. >> "%LOG%"
  goto diagnostics
)

echo --- waiting for http://localhost:8000/api/v1/health/ready --- >> "%LOG%"
for /l %%i in (1,1,60) do (
  curl.exe -fsS http://localhost:8000/api/v1/health/ready >> "%LOG%" 2>nul && goto ready
  timeout /t 2 /nobreak >nul
)
echo ERROR: API did not become healthy within 2 minutes. >> "%LOG%"
goto diagnostics

:ready
echo. >> "%LOG%"
echo API READY: http://localhost:8000/docs >> "%LOG%"
docker compose ps >> "%LOG%" 2>&1
goto done

:diagnostics
docker compose ps >> "%LOG%" 2>&1
docker compose logs --tail 100 >> "%LOG%" 2>&1

:done
echo [%date% %time%] Finished >> "%LOG%"
type "%LOG%"
echo.
echo Full log: %CD%\%LOG%
pause
