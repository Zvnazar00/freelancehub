@echo off
rem Stops the backend containers. Database data is kept in the "pgdata" Docker volume.
cd /d "%~dp0.."
docker compose down
pause
