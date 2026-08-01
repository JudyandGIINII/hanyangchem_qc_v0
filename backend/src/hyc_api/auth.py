from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException, Request

from hyc_api.contracts import Role

_FIXTURE_PRINCIPALS: dict[str, tuple[UUID, Role]] = {
    "p3-inspector": (UUID("11111111-1111-4111-8111-111111111111"), "INSPECTOR"),
    "p3-lead": (UUID("22222222-2222-4222-8222-222222222222"), "LEAD"),
    "p3-admin": (UUID("33333333-3333-4333-8333-333333333333"), "ADMIN"),
}


@dataclass(frozen=True, slots=True)
class Principal:
    actor_id: UUID
    role: Role
    fixture_name: str


def create_fixture_session(request: Request, fixture_name: str) -> tuple[str, Principal]:
    if not request.app.state.settings.p3_fixture_mode:
        raise HTTPException(status_code=404, detail="P3 fixture mode is disabled")
    identity = _FIXTURE_PRINCIPALS.get(fixture_name)
    if identity is None:
        raise HTTPException(status_code=401, detail="Unknown fixture principal")
    session_handle = uuid4().hex
    principal = Principal(identity[0], identity[1], fixture_name)
    request.app.state.p3_sessions[session_handle] = principal
    return session_handle, principal


def require_principal(request: Request) -> Principal:
    if not request.app.state.settings.p3_fixture_mode:
        raise HTTPException(status_code=404, detail="P3 fixture mode is disabled")
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Fixture bearer session required")
    principal = request.app.state.p3_sessions.get(header[7:])
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid fixture session")
    return cast(Principal, principal)


def require_role(principal: Principal, *roles: Role) -> None:
    if principal.role not in roles:
        raise HTTPException(status_code=403, detail="Role is not permitted")
