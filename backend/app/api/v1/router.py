from fastapi import APIRouter

from app.api.v1 import analytics, auth, clients, exports, health, invoices, me, projects, tasks, time_entries, timer
from app.schemas.common import ProblemDetail

_problem = {"model": ProblemDetail, "content": {"application/problem+json": {}}}

api_router = APIRouter(
    responses={401: _problem, 404: _problem, 409: _problem, 422: _problem, 500: _problem},
)
for module in (health, auth, me, clients, projects, tasks, timer, time_entries, invoices, analytics, exports):
    api_router.include_router(module.router)
