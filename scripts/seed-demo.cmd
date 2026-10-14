@echo off
rem Creates (or recreates) the demo account with realistic data for screenshots and screencasts.
rem Requires the backend to be running (scripts\start-backend.cmd). Only the demo user is replaced.
cd /d "%~dp0.."
if not exist logs mkdir logs
docker compose exec -T api python -m app.cli.seed_demo > logs\seed-demo.log 2>&1
type logs\seed-demo.log
pause
