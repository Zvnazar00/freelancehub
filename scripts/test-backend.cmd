@echo off
rem Runs the backend test suite inside the API container (uses a separate *_test database).
cd /d "%~dp0.."
if not exist logs mkdir logs
echo --- dev database migration version --- > logs\backend-tests.log
docker compose exec -T api alembic current >> logs\backend-tests.log 2>&1
echo --- pytest --- >> logs\backend-tests.log
docker compose exec -T api pytest --cov -q -p no:logging >> logs\backend-tests.log 2>&1
type logs\backend-tests.log
pause
