"""Stable, digest-scoped ownership serialization for document uploads.

Filesystem leases protect object identity, but their lock namespace is mutable.
This guard deliberately derives its authority only from the immutable digest.
"""

from __future__ import annotations

import re
import threading

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool


class DigestOwnershipGuard:
    """Serialize a digest's DB ownership lifecycle independently of storage paths.

    Every process uses a bounded in-memory stripe.  PostgreSQL additionally
    holds a session-level advisory lock on a dedicated checked-out connection,
    so workers in different processes cannot interleave ownership and cleanup.
    """

    _STRIPE_COUNT = 256
    _process_locks = tuple(threading.RLock() for _ in range(_STRIPE_COUNT))

    def __init__(self, session: Session, digest: str, lock_engine: Engine | None = None) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("digest ownership lock requires a SHA-256 digest")
        self._digest = digest
        self._session = session
        self._lock_engine = lock_engine
        self._process_lock = self._process_locks[self._stripe_index(digest)]
        self._connection: Connection | None = None
        self._acquired = False

    @classmethod
    def _stripe_index(cls, digest: str) -> int:
        return int(digest[:8], 16) % cls._STRIPE_COUNT

    @staticmethod
    def advisory_keys(digest: str) -> tuple[int, int]:
        """Return PostgreSQL's signed two-int key pair from a SHA-256 digest."""

        raw = bytes.fromhex(digest)
        return (
            int.from_bytes(raw[:4], byteorder="big", signed=True),
            int.from_bytes(raw[4:8], byteorder="big", signed=True),
        )

    def acquire(self) -> None:
        """Acquire process and, for PostgreSQL, cross-process serialization."""

        if self._acquired:
            raise RuntimeError("digest ownership guard was acquired twice")
        self._process_lock.acquire()
        try:
            application_engine = self._application_engine()
            if application_engine.dialect.name != "postgresql":
                self._acquired = True
                return
            lock_engine = self._postgresql_lock_engine(application_engine)
            connection = lock_engine.connect()
            self._connection = connection
            key_one, key_two = self.advisory_keys(self._digest)
            try:
                connection.execute(
                    text("SELECT pg_advisory_lock(:key_one, :key_two)"),
                    {"key_one": key_one, "key_two": key_two},
                )
            except Exception:
                self._invalidate_and_close(connection)
                self._connection = None
                raise
            self._acquired = True
        except Exception:
            self._process_lock.release()
            raise

    def _application_engine(self) -> Engine:
        """Return the session bind solely to identify the application dialect."""

        bind = self._session.get_bind()
        engine = bind.engine if isinstance(bind, Connection) else bind
        if not isinstance(engine, Engine):
            raise RuntimeError("digest ownership guard requires an Engine session bind")
        return engine

    def _postgresql_lock_engine(self, application_engine: Engine) -> Engine:
        """Fail closed unless advisory locks have a dedicated NullPool engine."""

        lock_engine = self._lock_engine
        if (
            not isinstance(lock_engine, Engine)
            or lock_engine.dialect.name != "postgresql"
            or not isinstance(lock_engine.pool, NullPool)
            or lock_engine.pool is application_engine.pool
        ):
            raise RuntimeError("PostgreSQL digest ownership guard requires an independent NullPool")
        return lock_engine

    def release(self) -> None:
        """Release both guards, never returning an unknown advisory lock to a pool."""

        if not self._acquired:
            return
        self._acquired = False
        connection = self._connection
        self._connection = None
        try:
            if connection is not None:
                key_one, key_two = self.advisory_keys(self._digest)
                try:
                    unlocked = connection.execute(
                        text("SELECT pg_advisory_unlock(:key_one, :key_two)"),
                        {"key_one": key_one, "key_two": key_two},
                    ).scalar_one()
                    if unlocked is not True:
                        raise RuntimeError("PostgreSQL advisory lock ownership was lost")
                except Exception:
                    # If the unlock result is unknown, discard the physical
                    # connection before it can be returned to SQLAlchemy's pool.
                    self._invalidate_and_close(connection)
                    connection = None
                finally:
                    if connection is not None:
                        self._close_quietly(connection)
        finally:
            self._process_lock.release()

    @staticmethod
    def _close_quietly(connection: Connection) -> None:
        try:
            connection.close()
        except Exception:
            pass

    @classmethod
    def _invalidate_and_close(cls, connection: Connection) -> None:
        try:
            connection.invalidate()
        except Exception:
            pass
        finally:
            cls._close_quietly(connection)
