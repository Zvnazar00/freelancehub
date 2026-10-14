import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from app.api.deps import Auth, DbSession
from app.api.idempotency import run_idempotent
from app.core.clock import Clock, get_clock
from app.schemas.time_entries import ActiveEntryUpdate, TimerCommand, TimerStart, TimerState, TimerStop
from app.services import time_entries as service

router = APIRouter(prefix="/timer", tags=["timer"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", description="Required. Unique per command.")]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/current")
def current(auth: Auth, db: DbSession, clock: Now) -> TimerState:
    now = clock()
    entry = service.current(db, auth.user)
    return TimerState(entry=service.serialize(db, auth.user, [entry], now)[0] if entry else None, server_time=now)


@router.post("/start", status_code=201, response_model=TimerState, responses={200: {"model": TimerState}})
def start(body: TimerStart, auth: Auth, db: DbSession, clock: Now, idempotency_key: IdemKey = None) -> Response:
    now = clock()

    def mutation() -> tuple[int, TimerState]:
        entry, created = service.start(db, auth.user, body, clock)
        moment = clock()
        return (201 if created else 200), TimerState(
            entry=service.one(db, auth.user, entry, moment), server_time=moment
        )

    return run_idempotent(
        db, auth.user, idempotency_key, "POST /timer/start", body.model_dump(mode="json"), now, mutation
    )


def _command(name: str):  # type: ignore[no-untyped-def]
    def handler(
        entry_id: uuid.UUID, body: TimerCommand, auth: Auth, db: DbSession, clock: Now, idempotency_key: IdemKey = None
    ) -> Response:
        now = clock()
        action = {"pause": service.pause, "resume": service.resume}[name]

        def mutation() -> tuple[int, TimerState]:
            entry = action(db, auth.user, entry_id, body, clock)
            moment = clock()
            return 200, TimerState(entry=service.one(db, auth.user, entry, moment), server_time=moment)

        return run_idempotent(
            db,
            auth.user,
            idempotency_key,
            f"POST /timer/{entry_id}/{name}",
            body.model_dump(mode="json"),
            now,
            mutation,
        )

    return handler


router.add_api_route("/{entry_id}/pause", _command("pause"), methods=["POST"], response_model=TimerState)
router.add_api_route("/{entry_id}/resume", _command("resume"), methods=["POST"], response_model=TimerState)


@router.post("/{entry_id}/stop", response_model=TimerState)
def stop(
    entry_id: uuid.UUID, body: TimerStop, auth: Auth, db: DbSession, clock: Now, idempotency_key: IdemKey = None
) -> Response:
    now = clock()

    def mutation() -> tuple[int, TimerState]:
        entry = service.stop(db, auth.user, entry_id, body, clock)
        moment = clock()
        return 200, TimerState(entry=service.one(db, auth.user, entry, moment), server_time=moment)

    return run_idempotent(
        db, auth.user, idempotency_key, f"POST /timer/{entry_id}/stop", body.model_dump(mode="json"), now, mutation
    )


@router.post("/{entry_id}/discard", response_model=TimerState)
def discard(entry_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now, idempotency_key: IdemKey = None) -> Response:
    now = clock()

    def mutation() -> tuple[int, TimerState]:
        service.discard(db, auth.user, entry_id, clock)
        return 200, TimerState(entry=None, server_time=clock())

    return run_idempotent(db, auth.user, idempotency_key, f"POST /timer/{entry_id}/discard", {}, now, mutation)


@router.patch("/{entry_id}")
def update_active(entry_id: uuid.UUID, body: ActiveEntryUpdate, auth: Auth, db: DbSession, clock: Now) -> TimerState:
    entry = service.update_active(db, auth.user, entry_id, body, clock)
    db.commit()
    now = clock()
    return TimerState(entry=service.one(db, auth.user, entry, now), server_time=now)
