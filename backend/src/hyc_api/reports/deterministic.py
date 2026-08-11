from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from openpyxl import Workbook  # type: ignore[import-untyped]

_PINNED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_PINNED_DATETIME = datetime(1980, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SheetSpec:
    """One worksheet rendered as pre-stringified cells.

    Values are strings by contract: Decimal formatting and locale decisions
    belong to the caller, so this module never rounds or reformats a number.
    """

    title: str
    rows: list[list[str]]


def _pin_archive(payload: bytes) -> bytes:
    """Rewrite the xlsx zip so every member carries a fixed timestamp.

    openpyxl stamps the current clock into each member and into docProps.
    Without this the same inspection renders a different digest every second,
    which would make the reproducibility contract untestable.
    """

    source = io.BytesIO(payload)
    target = io.BytesIO()
    with zipfile.ZipFile(source) as original:
        names = sorted(original.namelist())
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as pinned:
            for name in names:
                info = zipfile.ZipInfo(filename=name, date_time=_PINNED_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                pinned.writestr(info, original.read(name))
    return target.getvalue()


def render_workbook(sheets: Sequence[SheetSpec]) -> bytes:
    if not sheets:
        raise ValueError("a report workbook requires at least one sheet")
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet in sheets:
        worksheet = workbook.create_sheet(title=sheet.title)
        for row in sheet.rows:
            worksheet.append(list(row))
    workbook.properties.created = _PINNED_DATETIME
    workbook.properties.modified = _PINNED_DATETIME
    workbook.properties.creator = ""
    workbook.properties.lastModifiedBy = ""
    buffer = io.BytesIO()
    workbook.save(buffer)
    return _pin_archive(buffer.getvalue())


def workbook_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
