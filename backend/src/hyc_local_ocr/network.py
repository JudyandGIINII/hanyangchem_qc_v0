from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Never
from unittest.mock import patch

from hyc_local_ocr.errors import LocalOcrError


@dataclass
class NetworkDenyAudit:
    attempt_count: int = 0


@contextmanager
def deny_outbound_network() -> Iterator[NetworkDenyAudit]:
    """Deny DNS and socket connection primitives while counting attempts."""

    audit = NetworkDenyAudit()

    def denied(*_: object, **__: object) -> Never:
        audit.attempt_count += 1
        raise LocalOcrError("LOCAL_OCR_NETWORK_ACCESS_DENIED")

    with (
        patch.object(socket, "getaddrinfo", denied),
        patch.object(socket, "create_connection", denied),
        patch.object(socket.socket, "connect", denied),
        patch.object(socket.socket, "connect_ex", denied),
    ):
        yield audit
