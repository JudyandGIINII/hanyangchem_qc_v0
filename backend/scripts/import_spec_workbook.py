#!/usr/bin/env python3
"""Read-only structural XLSX dry-run parser for two approved profiles.

``masked-marker-v1`` recognizes only the synthetic ``HYC_SPEC_IMPORT_V1`` /
``ITEM_ROW`` fixture layout.  ``qm301-legacy-structural-v1`` recognizes the
approved legacy 38-sheet structural layout without exposing any cell value.
Both profiles are dry-run only: they produce deterministic masked JSON, make
no database writes, and never fetch external resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn
from xml.etree import ElementTree as ET
from xml.parsers import expat


SCHEMA_VERSION = "hyc.spec-workbook-dry-run.v1"
TEMPLATE_MARKER = "HYC_SPEC_IMPORT_V1"
ITEM_MARKER = "ITEM_ROW"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 256
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
MAX_ROWS_PER_SHEET = 20_000
MAX_CELLS_PER_SHEET = 100_000
HASH_CHUNK_BYTES = 1024 * 1024
MAX_EXCEL_ROW = 1_048_576
MAX_EXCEL_COLUMN = 16_384
LEGACY_QM301_WORKSHEET_COUNT = 38
MARKER_PROFILE = "masked-marker-v1"
LEGACY_QM301_PROFILE = "qm301-legacy-structural-v1"
ALLOWED_COMPRESS_TYPES = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
ROW_REFERENCE = re.compile(r"[1-9][0-9]*\Z")
CELL_REFERENCE = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]*)\Z")
CANONICAL_NONNEGATIVE_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
CANONICAL_POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*\Z")
WORKSHEET_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet",
}
OFFICE_DOCUMENT_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
}
XLSX_WORKBOOK_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
WORKSHEET_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
    # ISO/IEC 29500 Strict uses this registered Microsoft media type.
    "application/vnd.ms-excel.worksheet+xml",
}
SHARED_STRINGS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
RELATIONSHIPS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
EXPECTATION_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures/spec-import/qm301-7-expected.json"
EXPECTATION_SCHEMA_VERSION = "hyc.spec-import-expectations.v1"
QM301_SOURCE_ALIAS = "qm301-7-rb-import-inspection"
QM301_SOURCE_SHA256 = "b8ebb179b0dece9a6aa06229fe28feb1890082bd32a46e3ccc314febec138c9f"
SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
MEDIA_TYPE = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+/[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
URI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# RFC 3986 URI lexical characters. Percent is checked separately so a raw
# percent cannot bypass the required two hexadecimal digits.
RFC3986_URI_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "-._~:/?#[]@!$&'()*+,;="
)
# A path segment is deliberately narrower than a URI: it has no slash,
# query, or fragment. OPC package paths also reject every percent encoding,
# even a valid one, to avoid equivalent-but-differently-spelled member names.
RFC3986_PATH_SEGMENT_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "-._~!$&'()*+,;=:@"
)
HEX_DIGITS = frozenset("0123456789ABCDEFabcdef")
# Deliberately conservative ASCII NCName subset. It accepts standard rId1 IDs
# while avoiding XML-name Unicode normalization ambiguity in a security gate.
RELATIONSHIP_ID = re.compile(r"[A-Za-z_][A-Za-z0-9._-]*\Z")


class DryRunFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class StableArgumentParser(argparse.ArgumentParser):
    """Keep malformed invocation output inside the deterministic JSON contract."""

    def error(self, message: str) -> NoReturn:
        del message
        _error("E_ARGUMENTS_INVALID")


@dataclass(frozen=True)
class SheetResult:
    index: int
    item_row_count: int


@dataclass(frozen=True)
class WorksheetRow:
    number: int
    element: ET.Element


@dataclass(frozen=True)
class Baseline:
    template_count: int
    item_row_count: int
    source_sha256: str


def _error(code: str) -> NoReturn:
    raise DryRunFailure(code)


def _q(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def _normalized_identity(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _safe_xml(data: bytes) -> ET.Element:
    """Parse one bounded XML part, rejecting DTD/entity declarations by parser event."""
    parser = expat.ParserCreate()

    def reject_declaration(*_arguments: object) -> None:
        _error("E_XLSX_MALFORMED")

    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    try:
        parser.Parse(data, True)
        return ET.fromstring(data)
    except DryRunFailure:
        raise
    except (expat.ExpatError, ET.ParseError, UnicodeError, ValueError):
        _error("E_XLSX_MALFORMED")


def _is_whitespace(value: str | None) -> bool:
    return value is None or value.isspace() or value == ""


def _is_rfc3986_absolute_uri(value: str) -> bool:
    """Return whether *value* is a complete ASCII RFC 3986 URI spelling."""
    scheme = URI_SCHEME.match(value)
    if scheme is None or scheme.end() == len(value):
        return False
    index = 0
    while index < len(value):
        character = value[index]
        if character == "%":
            if (
                index + 2 >= len(value)
                or value[index + 1] not in HEX_DIGITS
                or value[index + 2] not in HEX_DIGITS
            ):
                return False
            index += 3
            continue
        if character not in RFC3986_URI_CHARACTERS:
            return False
        index += 1
    return True


def _validate_uri_path_segment(segment: str, *, allow_dot_segment: bool) -> None:
    """Validate one conservative, ASCII-only OPC URI path segment."""
    if not segment or (segment in {".", ".."} and not allow_dot_segment):
        _error("E_XLSX_MALFORMED")
    if segment in {".", ".."}:
        return
    # Percent-encoded package paths are intentionally rejected rather than
    # decoded: the importer accepts exactly one lexical package spelling.
    if any(character not in RFC3986_PATH_SEGMENT_CHARACTERS for character in segment):
        _error("E_XLSX_MALFORMED")


def _validate_uri_path(path: str, *, allow_dot_segments: bool) -> None:
    """Validate a relative OPC URI path without normalizing its spelling."""
    if not path or path.startswith("/"):
        _error("E_XLSX_MALFORMED")
    segments = path.split("/")
    # A leading scheme is an absolute URI; a drive-shaped segment is rejected
    # wherever it occurs so platform-specific path semantics cannot leak in.
    if URI_SCHEME.match(path) is not None or any(re.match(r"[A-Za-z]:", segment) for segment in segments):
        _error("E_XLSX_MALFORMED")
    for segment in segments:
        _validate_uri_path_segment(segment, allow_dot_segment=allow_dot_segments)


def _canonical_member_name(name: str, *, allow_directory: bool) -> str:
    """Validate the ZIP spelling used as an OPC part name without normalizing it."""
    if not name:
        _error("E_XLSX_MALFORMED")
    # This required OPC control member has its standardized bracket spelling;
    # it is the sole exception to ordinary RFC 3986 path-segment characters.
    if name == "[Content_Types].xml":
        return name
    is_directory = name.endswith("/")
    if is_directory and not allow_directory:
        _error("E_XLSX_MALFORMED")
    _validate_uri_path(name[:-1] if is_directory else name, allow_dot_segments=False)
    return name


def _extension(member: str) -> str | None:
    basename = member.rsplit("/", 1)[-1]
    if "." not in basename:
        return None
    extension = basename.rsplit(".", 1)[1]
    return extension.casefold() if extension else None


def _is_xml_content_type(content_type: str) -> bool:
    normalized = content_type.casefold()
    return normalized in {"application/xml", "text/xml"} or normalized.endswith("+xml")


def _validate_content_types(root: ET.Element, names: set[str]) -> dict[str, str]:
    if root.tag != _q(CONTENT_TYPES_NS, "Types") or root.attrib:
        _error("E_XLSX_MALFORMED")
    if not _is_whitespace(root.text):
        _error("E_XLSX_MALFORMED")
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for child in root:
        if not _is_whitespace(child.tail):
            _error("E_XLSX_MALFORMED")
        if child.tag == _q(CONTENT_TYPES_NS, "Default"):
            extension = child.attrib.get("Extension")
            content_type = child.attrib.get("ContentType")
            canonical_extension = extension.casefold() if extension else ""
            if (
                set(child.attrib) != {"Extension", "ContentType"}
                or list(child)
                or not _is_whitespace(child.text)
                or not extension
                or not content_type
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", extension)
                or MEDIA_TYPE.fullmatch(content_type) is None
                or canonical_extension in defaults
            ):
                _error("E_XLSX_MALFORMED")
            defaults[canonical_extension] = content_type
        elif child.tag == _q(CONTENT_TYPES_NS, "Override"):
            part_name = child.attrib.get("PartName")
            content_type = child.attrib.get("ContentType")
            member = part_name[1:] if part_name and part_name.startswith("/") else ""
            if (
                set(child.attrib) != {"PartName", "ContentType"}
                or list(child)
                or not _is_whitespace(child.text)
                or not part_name
                or not content_type
                or not part_name.startswith("/")
                or MEDIA_TYPE.fullmatch(content_type) is None
                or member == "[Content_Types].xml"
            ):
                _error("E_XLSX_MALFORMED")
            _canonical_member_name(member, allow_directory=False)
            if member not in names or member in overrides:
                _error("E_XLSX_MALFORMED")
            overrides[member] = content_type
        else:
            _error("E_XLSX_MALFORMED")
    if overrides.get("xl/workbook.xml") != XLSX_WORKBOOK_CONTENT_TYPE:
        _error("E_XLSX_MALFORMED")
    resolved: dict[str, str] = {}
    for name in names:
        if name == "[Content_Types].xml":
            continue
        content_type = overrides.get(name)
        if content_type is None:
            extension = _extension(name)
            content_type = defaults.get(extension) if extension is not None else None
        if content_type is None:
            _error("E_XLSX_MALFORMED")
        resolved[name] = content_type
    if "xl/sharedStrings.xml" in names and resolved["xl/sharedStrings.xml"] != SHARED_STRINGS_CONTENT_TYPE:
        _error("E_XLSX_MALFORMED")
    return resolved


def _relationship_source_part(relationship_part: str) -> str | None:
    if relationship_part == "_rels/.rels":
        return None
    if relationship_part.startswith("_rels/"):
        filename = relationship_part.removeprefix("_rels/")
        if "/" in filename or not filename.casefold().endswith(".rels"):
            _error("E_XLSX_MALFORMED")
        source_name = filename[:-5]
        if not source_name:
            _error("E_XLSX_MALFORMED")
        return source_name
    directory, separator, filename = relationship_part.rpartition("/_rels/")
    if not separator or not directory or not filename.casefold().endswith(".rels"):
        _error("E_XLSX_MALFORMED")
    source_name = filename[:-5]
    if not source_name:
        _error("E_XLSX_MALFORMED")
    return f"{directory}/{source_name}"


def _resolve_relationship_target(source_part: str | None, target: str) -> str:
    _validate_uri_path(target, allow_dot_segments=True)
    source_directory = "" if source_part is None else posixpath.dirname(source_part)
    resolved = posixpath.normpath(posixpath.join(source_directory, target))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        _error("E_XLSX_MALFORMED")
    _validate_uri_path(resolved, allow_dot_segments=False)
    return resolved


def _validate_relationship_parts(
    parsed_parts: dict[str, ET.Element], names: set[str], content_types: dict[str, str]
) -> None:
    package_relationships = parsed_parts.get("_rels/.rels")
    if package_relationships is None:
        _error("E_XLSX_MALFORMED")
    for relationship_part in sorted(name for name in parsed_parts if name.casefold().endswith(".rels")):
        if content_types.get(relationship_part) != RELATIONSHIPS_CONTENT_TYPE:
            _error("E_XLSX_MALFORMED")
        root = parsed_parts[relationship_part]
        if root.tag != _q(PACKAGE_REL_NS, "Relationships") or root.attrib or not _is_whitespace(root.text):
            _error("E_XLSX_MALFORMED")
        source_part = _relationship_source_part(relationship_part)
        if source_part is not None and source_part not in names:
            _error("E_XLSX_MALFORMED")
        relationship_ids: set[str] = set()
        office_document_relationships: list[tuple[str, str]] = []
        for relationship in root:
            if relationship.tag != _q(PACKAGE_REL_NS, "Relationship"):
                _error("E_XLSX_MALFORMED")
            if (
                set(relationship.attrib) - {"Id", "Type", "Target", "TargetMode"}
                or list(relationship)
                or not _is_whitespace(relationship.text)
                or not _is_whitespace(relationship.tail)
            ):
                _error("E_XLSX_MALFORMED")
            relation_id = relationship.attrib.get("Id")
            relation_type = relationship.attrib.get("Type")
            target = relationship.attrib.get("Target")
            target_mode = relationship.attrib.get("TargetMode")
            if (
                RELATIONSHIP_ID.fullmatch(relation_id or "") is None
                or relation_id in relationship_ids
                or not relation_type
                or not _is_rfc3986_absolute_uri(relation_type)
                or not target
                or target_mode not in {None, "Internal"}
            ):
                _error("E_XLSX_MALFORMED")
            relationship_ids.add(relation_id)
            resolved = _resolve_relationship_target(source_part, target)
            # OPC relationship uniqueness is by Id, not resolved Target:
            # distinct typed relationships may legitimately share one part.
            if resolved not in names:
                _error("E_XLSX_MALFORMED")
            if relation_type in WORKSHEET_RELATIONSHIP_TYPES and content_types.get(resolved) not in WORKSHEET_CONTENT_TYPES:
                _error("E_XLSX_MALFORMED")
            if relationship_part == "_rels/.rels" and relation_type in OFFICE_DOCUMENT_RELATIONSHIP_TYPES:
                office_document_relationships.append((relation_type, resolved))
        if relationship_part == "_rels/.rels" and (
            len(office_document_relationships) != 1
            or office_document_relationships[0][1] != "xl/workbook.xml"
        ):
            _error("E_XLSX_MALFORMED")


def _validate_archive(archive: zipfile.ZipFile) -> None:
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        _error("E_XLSX_MALFORMED")
    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)):
        _error("E_XLSX_MALFORMED")
    if any(entry.flag_bits & 0x1 for entry in entries):
        _error("E_XLSX_MALFORMED")
    if any(entry.compress_type not in ALLOWED_COMPRESS_TYPES for entry in entries):
        _error("E_XLSX_MALFORMED")
    if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
        _error("E_XLSX_MALFORMED")
    if any(entry.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES for entry in entries):
        _error("E_XLSX_MALFORMED")
    for name in names:
        _canonical_member_name(name, allow_directory=True)
    member_names = {name for name in names if not name.endswith("/")}
    required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    if not required.issubset(member_names):
        _error("E_XLSX_MALFORMED")
    # Read every bounded member before semantic parsing so CRC/decompression
    # corruption in arbitrary media or binary package members fails closed.
    member_data: dict[str, bytes] = {}
    for name in names:
        data = _read_member(archive, name)
        if name in member_names:
            member_data[name] = data
    # Parse every XML and relationship part even if it is not referenced by the
    # selected workbook structure: OOXML packages must not carry a malformed or
    # entity-bearing side channel.
    content_types_root = _safe_xml(member_data["[Content_Types].xml"])
    content_types = _validate_content_types(content_types_root, member_names)
    parsed_parts: dict[str, ET.Element] = {"[Content_Types].xml": content_types_root}
    for name, content_type in content_types.items():
        if _is_xml_content_type(content_type) or name.casefold().endswith(".rels"):
            parsed_parts[name] = _safe_xml(member_data[name])
    _validate_relationship_parts(parsed_parts, member_names, content_types)


def _read_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except (EOFError, KeyError, NotImplementedError, OSError, RuntimeError, ValueError, zlib.error, zipfile.BadZipFile):
        _error("E_XLSX_MALFORMED")


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _safe_xml(_read_member(archive, "xl/sharedStrings.xml"))
    if root.tag != _q(MAIN_NS, "sst"):
        _error("E_XLSX_MALFORMED")
    return ["".join(text.text or "" for text in item.iter(_q(MAIN_NS, "t"))) for item in root.findall(_q(MAIN_NS, "si"))]


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter(_q(MAIN_NS, "t")))
    value = cell.findtext(_q(MAIN_NS, "v"), default="")
    if cell_type == "s":
        if not CANONICAL_NONNEGATIVE_DECIMAL.fullmatch(value):
            _error("E_XLSX_MALFORMED")
        index = int(value)
        if index >= len(shared_strings):
            _error("E_XLSX_MALFORMED")
        return shared_strings[index]
    return value


def _workbook_sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = _safe_xml(_read_member(archive, "xl/workbook.xml"))
    relationships = _safe_xml(_read_member(archive, "xl/_rels/workbook.xml.rels"))
    if workbook.tag != _q(MAIN_NS, "workbook") or relationships.tag != _q(PACKAGE_REL_NS, "Relationships"):
        _error("E_XLSX_MALFORMED")

    targets: dict[str, str] = {}
    all_relation_ids: set[str] = set()
    for relationship in relationships.findall(_q(PACKAGE_REL_NS, "Relationship")):
        relation_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if not relation_id or not target or relation_id in all_relation_ids:
            _error("E_XLSX_MALFORMED")
        all_relation_ids.add(relation_id)
        if relationship.attrib.get("TargetMode") not in {None, "Internal"}:
            _error("E_XLSX_MALFORMED")
        resolved = _resolve_relationship_target("xl/workbook.xml", target)
        if relationship.attrib.get("Type") in WORKSHEET_RELATIONSHIP_TYPES:
            targets[relation_id] = resolved

    result: list[tuple[str, str]] = []
    identities: set[str] = set()
    sheet_ids: set[str] = set()
    sheet_relation_ids: set[str] = set()
    resolved_targets: set[str] = set()
    for sheet in workbook.findall(f"{_q(MAIN_NS, 'sheets')}/{_q(MAIN_NS, 'sheet')}"):
        name = sheet.attrib.get("name")
        sheet_id = sheet.attrib.get("sheetId")
        relation_id = sheet.attrib.get(_q(REL_NS, "id"))
        if (
            not name
            or not sheet_id
            or not CANONICAL_POSITIVE_DECIMAL.fullmatch(sheet_id)
            or not relation_id
            or relation_id not in targets
        ):
            _error("E_XLSX_MALFORMED")
        if sheet_id in sheet_ids or relation_id in sheet_relation_ids or targets[relation_id] in resolved_targets:
            _error("E_XLSX_MALFORMED")
        sheet_ids.add(sheet_id)
        sheet_relation_ids.add(relation_id)
        resolved_targets.add(targets[relation_id])
        identity = _normalized_identity(name)
        if not identity or identity in identities:
            _error("E_SHEET_IDENTITY_DUPLICATE")
        identities.add(identity)
        result.append((name, targets[relation_id]))
    if not result:
        _error("E_WORKBOOK_STRUCTURE_MISSING")
    return result


def _parse_row_reference(row: ET.Element) -> int:
    reference = row.attrib.get("r", "")
    if not ROW_REFERENCE.fullmatch(reference):
        _error("E_XLSX_MALFORMED")
    number = int(reference)
    if number > MAX_EXCEL_ROW:
        _error("E_XLSX_MALFORMED")
    return number


def _column_number(column: str) -> int:
    number = 0
    for character in column.upper():
        number = (number * 26) + (ord(character) - ord("A") + 1)
    return number


def _cell_reference(cell: ET.Element, row_number: int) -> tuple[str, int]:
    reference = cell.attrib.get("r", "")
    match = CELL_REFERENCE.fullmatch(reference)
    if match is None:
        _error("E_XLSX_MALFORMED")
    column, cell_row = match.groups()
    parsed_row = int(cell_row)
    if parsed_row != row_number or _column_number(column) > MAX_EXCEL_COLUMN:
        _error("E_XLSX_MALFORMED")
    return column.upper(), parsed_row


def _worksheet_rows(root: ET.Element) -> list[WorksheetRow]:
    if root.tag != _q(MAIN_NS, "worksheet"):
        _error("E_XLSX_MALFORMED")
    rows = root.findall(f"{_q(MAIN_NS, 'sheetData')}/{_q(MAIN_NS, 'row')}")
    if len(rows) > MAX_ROWS_PER_SHEET:
        _error("E_XLSX_MALFORMED")
    if sum(len(row.findall(_q(MAIN_NS, "c"))) for row in rows) > MAX_CELLS_PER_SHEET:
        _error("E_XLSX_MALFORMED")
    result: list[WorksheetRow] = []
    prior_number = 0
    for row in rows:
        number = _parse_row_reference(row)
        if number <= prior_number:
            _error("E_XLSX_MALFORMED")
        prior_number = number
        seen_cells: set[str] = set()
        for cell in row.findall(_q(MAIN_NS, "c")):
            column, _ = _cell_reference(cell, number)
            if column in seen_cells:
                _error("E_XLSX_MALFORMED")
            seen_cells.add(column)
        result.append(WorksheetRow(number, row))
    return result


def _marker_header(rows: list[WorksheetRow], shared_strings: list[str]) -> bool:
    if len(rows) < 2 or rows[0].number != 1 or rows[1].number != 2:
        return False
    first_cells = rows[0].element.findall(_q(MAIN_NS, "c"))
    second_cells = rows[1].element.findall(_q(MAIN_NS, "c"))
    return (
        len(first_cells) == len(second_cells) == 1
        and _cell_reference(first_cells[0], 1)[0] == "A"
        and _cell_reference(second_cells[0], 2)[0] == "A"
        and _cell_text(first_cells[0], shared_strings) == TEMPLATE_MARKER
        and _cell_text(second_cells[0], shared_strings) == ITEM_MARKER
    )


def _parse_marker_sheet(archive: zipfile.ZipFile, target: str, index: int, shared_strings: list[str]) -> SheetResult:
    rows = _worksheet_rows(_safe_xml(_read_member(archive, target)))
    if not _marker_header(rows, shared_strings):
        _error("E_WORKBOOK_STRUCTURE_MISSING")

    item_rows = 0
    items_ended = False
    for worksheet_row in rows[2:]:
        values: list[tuple[str, str]] = []
        for cell in worksheet_row.element.findall(_q(MAIN_NS, "c")):
            column, _ = _cell_reference(cell, worksheet_row.number)
            values.append((column, _cell_text(cell, shared_strings)))
        markers = [column for column, value in values if value == ITEM_MARKER]
        if markers:
            if len(markers) != 1 or markers[0] != "A":
                _error("E_ITEM_ROWS_AMBIGUOUS")
            if items_ended or worksheet_row.number != item_rows + 3:
                _error("E_ITEM_ROWS_AMBIGUOUS")
            item_rows += 1
        elif item_rows:
            items_ended = True
    if item_rows == 0:
        _error("E_WORKBOOK_STRUCTURE_MISSING")
    return SheetResult(index=index, item_row_count=item_rows)


def _is_marker_sheet(archive: zipfile.ZipFile, target: str, shared_strings: list[str]) -> bool:
    return _marker_header(_worksheet_rows(_safe_xml(_read_member(archive, target))), shared_strings)


def _cell_is_non_empty(cell: ET.Element) -> bool:
    if cell.attrib.get("t") == "inlineStr":
        return any((text.text or "") != "" for text in cell.iter(_q(MAIN_NS, "t")))
    return (cell.findtext(_q(MAIN_NS, "v"), default="") != "") or cell.find(_q(MAIN_NS, "f")) is not None


def _legacy_row_status(row: WorksheetRow) -> str:
    required_columns = {"A", "C", "Y"}
    values: dict[str, bool] = {}
    for cell in row.element.findall(_q(MAIN_NS, "c")):
        column, _ = _cell_reference(cell, row.number)
        if column in required_columns:
            values[column] = _cell_is_non_empty(cell)
    if not values:
        return "absent"
    if set(values) == required_columns and all(values.values()):
        return "complete"
    return "partial"


def _parse_legacy_qm301_sheet(archive: zipfile.ZipFile, target: str, index: int) -> SheetResult:
    rows = _worksheet_rows(_safe_xml(_read_member(archive, target)))
    header = next((row for row in rows if row.number == 10), None)
    if header is None or _legacy_row_status(header) != "complete":
        _error("E_WORKBOOK_STRUCTURE_MISSING")

    post_header_rows = [row for row in rows if row.number > 10]
    if not post_header_rows or post_header_rows[0].number != 11:
        _error("E_WORKBOOK_STRUCTURE_MISSING")
    first_status = _legacy_row_status(post_header_rows[0])
    if first_status != "complete":
        _error("E_ITEM_ROWS_AMBIGUOUS" if first_status == "partial" else "E_WORKBOOK_STRUCTURE_MISSING")

    item_rows = 1
    items_ended = False
    expected_number = 12
    for row in post_header_rows[1:]:
        status = _legacy_row_status(row)
        if status == "complete":
            if items_ended or row.number != expected_number:
                _error("E_ITEM_ROWS_AMBIGUOUS")
            item_rows += 1
            expected_number += 1
        else:
            items_ended = True
    return SheetResult(index=index, item_row_count=item_rows)


def _baseline() -> Baseline:
    try:
        expected = json.loads(EXPECTATION_FIXTURE_PATH.read_text(encoding="utf-8"))
        if not isinstance(expected, dict) or set(expected) != {
            "schema_version",
            "source_reference",
            "approved_structural_expectations",
            "discrepancy_policy",
        }:
            _error("E_EXPECTATION_FIXTURE_INVALID")
        if expected["schema_version"] != EXPECTATION_SCHEMA_VERSION:
            _error("E_EXPECTATION_FIXTURE_INVALID")

        source_reference = expected["source_reference"]
        if not isinstance(source_reference, dict) or set(source_reference) != {
            "classification",
            "source_body_included",
            "source_alias",
            "source_sha256",
            "p0a_evidence_path",
            "p0a_evidence_manifest_path",
            "p0a_evidence_schema_version",
            "p0a_observation_path",
        }:
            _error("E_EXPECTATION_FIXTURE_INVALID")
        if (
            source_reference["classification"] != "sensitive-source-evidence"
            or source_reference["source_body_included"] is not False
            or source_reference["source_alias"] != QM301_SOURCE_ALIAS
            or not isinstance(source_reference["source_sha256"], str)
            or SHA256_HEX.fullmatch(source_reference["source_sha256"]) is None
            or source_reference["source_sha256"] != QM301_SOURCE_SHA256
            or source_reference["p0a_evidence_path"] != "docs/evidence/2026-07-30-p0a-evidence-freeze.md"
            or source_reference["p0a_evidence_manifest_path"] != "docs/evidence/2026-07-30-p0a-source-manifest.json"
            or isinstance(source_reference["p0a_evidence_schema_version"], bool)
            or not isinstance(source_reference["p0a_evidence_schema_version"], int)
            or source_reference["p0a_evidence_schema_version"] != 1
            or source_reference["p0a_observation_path"] != "read_only_observation.workbook_metadata[0]"
        ):
            _error("E_EXPECTATION_FIXTURE_INVALID")

        expectations = expected["approved_structural_expectations"]
        if not isinstance(expectations, dict) or set(expectations) != {"template_count", "item_row_count"}:
            _error("E_EXPECTATION_FIXTURE_INVALID")
        template_count = expectations["template_count"]
        item_row_count = expectations["item_row_count"]
        if (
            isinstance(template_count, bool)
            or not isinstance(template_count, int)
            or template_count <= 0
            or isinstance(item_row_count, bool)
            or not isinstance(item_row_count, int)
            or item_row_count <= 0
        ):
            _error("E_EXPECTATION_FIXTURE_INVALID")

        discrepancy_policy = expected["discrepancy_policy"]
        if not isinstance(discrepancy_policy, dict) or set(discrepancy_policy) != {
            "when_actual_differs",
            "auto_correct",
            "apply_performed",
        }:
            _error("E_EXPECTATION_FIXTURE_INVALID")
        if (
            discrepancy_policy["when_actual_differs"] != "QUALITY_REVIEW_REQUIRED"
            or discrepancy_policy["auto_correct"] is not False
            or discrepancy_policy["apply_performed"] is not False
        ):
            _error("E_EXPECTATION_FIXTURE_INVALID")
        return Baseline(
            template_count=template_count,
            item_row_count=item_row_count,
            source_sha256=source_reference["source_sha256"],
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        _error("E_EXPECTATION_FIXTURE_INVALID")


def _hash_open_file(source: object) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(HASH_CHUNK_BYTES):  # type: ignore[attr-defined]
        digest.update(chunk)
    return digest.hexdigest()


def _review_discrepancies(
    baseline: Baseline, source_sha256: str, template_count: int, item_row_count: int
) -> list[dict[str, object]]:
    """Return ordered, masked review evidence; never correct or apply input."""
    discrepancies: list[dict[str, object]] = []
    if source_sha256 != baseline.source_sha256:
        discrepancies.append(
            {
                "code": "QUALITY_REVIEW_REQUIRED",
                "kind": "SOURCE_DIGEST_MISMATCH",
                "expected": {"source_sha256": baseline.source_sha256},
                "observed": {"source_sha256": source_sha256},
            }
        )
    if (template_count, item_row_count) != (baseline.template_count, baseline.item_row_count):
        discrepancies.append(
            {
                "code": "QUALITY_REVIEW_REQUIRED",
                "kind": "STRUCTURAL_COUNT_MISMATCH",
                "expected": {
                    "template_count": baseline.template_count,
                    "item_row_count": baseline.item_row_count,
                },
                "observed": {"template_count": template_count, "item_row_count": item_row_count},
            }
        )
    return discrepancies


def parse_dry_run(input_path: Path) -> dict[str, object]:
    if not input_path.is_file():
        _error("E_INPUT_NOT_FOUND")
    if input_path.suffix.casefold() != ".xlsx":
        _error("E_INPUT_NOT_XLSX")
    try:
        with input_path.open("rb") as source:
            before_stat = os.fstat(source.fileno())
            if before_stat.st_size > MAX_INPUT_BYTES:
                _error("E_XLSX_MALFORMED")
            source_hash = _hash_open_file(source)
            source.seek(0)
            with zipfile.ZipFile(source, "r") as archive:
                _validate_archive(archive)
                sheets = _workbook_sheets(archive)
                shared_strings = _shared_strings(archive)
                if all(_is_marker_sheet(archive, target, shared_strings) for _, target in sheets):
                    structural_profile = MARKER_PROFILE
                    parsed_sheets = [
                        _parse_marker_sheet(archive, target, index, shared_strings)
                        for index, (_, target) in enumerate(sheets, start=1)
                    ]
                else:
                    if len(sheets) != LEGACY_QM301_WORKSHEET_COUNT:
                        _error("E_WORKBOOK_STRUCTURE_MISSING")
                    structural_profile = LEGACY_QM301_PROFILE
                    parsed_sheets = [
                        _parse_legacy_qm301_sheet(archive, target, index)
                        for index, (_, target) in enumerate(sheets, start=1)
                    ]
            source.seek(0)
            parsed_hash = _hash_open_file(source)
            after_stat = os.fstat(source.fileno())
            if (
                before_stat.st_size != after_stat.st_size
                or before_stat.st_mtime_ns != after_stat.st_mtime_ns
                or source_hash != parsed_hash
            ):
                _error("E_INPUT_CHANGED")
    except DryRunFailure:
        raise
    except (EOFError, NotImplementedError, OSError, RuntimeError, ValueError, zlib.error, zipfile.BadZipFile):
        _error("E_XLSX_MALFORMED")

    baseline = _baseline()
    template_count = len(parsed_sheets)
    item_row_count = sum(sheet.item_row_count for sheet in parsed_sheets)
    discrepancies = _review_discrepancies(baseline, source_hash, template_count, item_row_count)
    return {
        "apply_performed": False,
        "database_writes": 0,
        "discrepancies": discrepancies,
        "item_row_count": item_row_count,
        "schema_version": SCHEMA_VERSION,
        "sheets": [
            {
                "item_row_count": sheet.item_row_count,
                "sheet_identifier": f"sheet-{sheet.index:03d}",
                "structural_profile": structural_profile,
            }
            for sheet in parsed_sheets
        ],
        "source_sha256": source_hash,
        "structural_profile": structural_profile,
        "template_count": template_count,
        "warnings": [],
        "worksheet_count": template_count,
    }


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = StableArgumentParser(add_help=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    try:
        arguments = parser.parse_args(argv)
        if not arguments.dry_run:
            _emit({"error_code": "E_DRY_RUN_REQUIRED", "schema_version": SCHEMA_VERSION})
            return 2
        if not arguments.json:
            _emit({"error_code": "E_JSON_REQUIRED", "schema_version": SCHEMA_VERSION})
            return 2
        _emit(parse_dry_run(Path(arguments.input)))
        return 0
    except DryRunFailure as failure:
        _emit({"error_code": failure.code, "schema_version": SCHEMA_VERSION})
        return 2
    except Exception:
        _emit({"error_code": "E_UNEXPECTED", "schema_version": SCHEMA_VERSION})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
