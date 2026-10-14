import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import Auth, DbSession
from app.core.clock import Clock, get_clock
from app.schemas.analytics import Breakdown, DashboardSummary, GroupBy, Interval, Period, ProjectSummary, Timeseries
from app.services import analytics as service

router = APIRouter(tags=["dashboard & analytics"])
Now = Annotated[Clock, Depends(get_clock)]
From = Annotated[date | None, Query(alias="from", description="Local date (user time zone), inclusive")]
To = Annotated[date | None, Query(alias="to", description="Local date (user time zone), inclusive")]
PeriodQuery = Annotated[Period | None, Query(description="Calendar period containing today; ignored with from/to")]


@router.get("/dashboard/summary")
def dashboard_summary(
    auth: Auth, db: DbSession, clock: Now, period: PeriodQuery = None, day_from: From = None, day_to: To = None
) -> DashboardSummary:
    return service.dashboard(db, auth.user, period=period, day_from=day_from, day_to=day_to, now=clock())


@router.get("/analytics/timeseries")
def analytics_timeseries(
    auth: Auth,
    db: DbSession,
    clock: Now,
    period: PeriodQuery = None,
    day_from: From = None,
    day_to: To = None,
    interval: Interval | None = None,
) -> Timeseries:
    return service.timeseries(
        db, auth.user, period=period, day_from=day_from, day_to=day_to, interval=interval, now=clock()
    )


@router.get("/analytics/breakdown")
def analytics_breakdown(
    auth: Auth,
    db: DbSession,
    clock: Now,
    period: PeriodQuery = None,
    day_from: From = None,
    day_to: To = None,
    group_by: GroupBy = "project",
) -> Breakdown:
    return service.breakdown(
        db, auth.user, period=period, day_from=day_from, day_to=day_to, group_by=group_by, now=clock()
    )


@router.get("/projects/{project_id}/summary")
def project_summary(project_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now) -> ProjectSummary:
    return service.project_summary(db, auth.user, project_id, clock())
