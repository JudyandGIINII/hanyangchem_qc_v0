from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

#: PostgreSQL assigns SQLSTATE P0001 to a bare ``RAISE EXCEPTION``. Every domain
#: invariant this repository enforces in a trigger raises that way, so P0001 marks
#: an intentional rule violation. Any other SQLSTATE is an infrastructure fault and
#: must keep propagating rather than being reported as a business conflict.
_DOMAIN_INVARIANT_SQLSTATE = "P0001"


def _is_domain_invariant_violation(error: DBAPIError) -> bool:
    original = getattr(error, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return sqlstate == _DOMAIN_INVARIANT_SQLSTATE


def _commit(session: Session, *, stale_detail: str, conflict_detail: str) -> None:
    try:
        session.commit()
    except StaleDataError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=stale_detail) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail) from error
    except DBAPIError as error:
        session.rollback()
        if not _is_domain_invariant_violation(error):
            raise
        raise HTTPException(status_code=409, detail=conflict_detail) from error
