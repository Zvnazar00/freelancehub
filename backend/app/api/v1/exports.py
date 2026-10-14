import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import Auth, DbSession
from app.core.clock import Clock, get_clock
from app.services import exports as service

router = APIRouter(prefix="/exports", tags=["exports"])
Now = Annotated[Clock, Depends(get_clock)]
From = Annotated[date | None, Query(alias="from", description="Local date, inclusive. Default: 1st of the month")]
To = Annotated[date | None, Query(alias="to", description="Local date, inclusive. Default: today")]
_csv_doc: dict[int | str, dict[str, Any]] = {200: {"content": {"text/csv": {}}, "description": "UTF-8 CSV with BOM"}}


def _csv(body: bytes, filename: str) -> Response:
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get("/time-entries.csv", response_class=Response, responses=_csv_doc)
def time_entries_csv(
    auth: Auth,
    db: DbSession,
    clock: Now,
    day_from: From = None,
    day_to: To = None,
    project_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
) -> Response:
    return _csv(
        *service.time_entries_csv(
            db, auth.user, day_from=day_from, day_to=day_to, project_id=project_id, client_id=client_id, now=clock()
        )
    )


@router.get("/invoices.csv", response_class=Response, responses=_csv_doc)
def invoices_csv(auth: Auth, db: DbSession, clock: Now, day_from: From = None, day_to: To = None) -> Response:
    return _csv(*service.invoices_csv(db, auth.user, day_from=day_from, day_to=day_to, now=clock()))
