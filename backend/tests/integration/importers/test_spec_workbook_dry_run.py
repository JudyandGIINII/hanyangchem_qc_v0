from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import warnings
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "backend/scripts/import_spec_workbook.py"

# All sentinels in this module are synthetic test fixtures, not credentials.


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets></workbook>"
    )


def _content_types_xml(worksheet_count: int = 1) -> str:
    worksheet_overrides = "".join(
        '<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(index=index)
        for index in range(1, worksheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{worksheet_overrides}</Types>"
    )


def _content_types_with(*declarations: str) -> str:
    return _content_types_xml().replace("</Types>", f"{''.join(declarations)}</Types>")


def _override_content_type(part_name: str, content_type: str) -> str:
    return f'<Override PartName="/{part_name}" ContentType="{content_type}"/>'


def _package_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _sheet_xml(item_rows: int, *, secret: str = "MASKED_VALUE", ambiguous: bool = False) -> str:
    rows = [
        '<row r="1"><c r="A1" t="inlineStr"><is><t>HYC_SPEC_IMPORT_V1</t></is></c></row>',
        '<row r="2"><c r="A2" t="inlineStr"><is><t>ITEM_ROW</t></is></c></row>',
    ]
    for row in range(3, item_rows + 3):
        extra = (
            '<c r="B{row}" t="inlineStr"><is><t>ITEM_ROW</t></is></c>'.format(row=row)
            if ambiguous and row == 3
            else '<c r="B{row}" t="inlineStr"><is><t>{secret}</t></is></c>'.format(
                row=row, secret=escape(secret)
            )
        )
        rows.append(
            '<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>ITEM_ROW</t></is></c>{extra}</row>'.format(
                row=row, extra=extra
            )
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


def _legacy_sheet_xml(
    item_rows: int,
    *,
    secret: str = "MASKED_VALUE",
    start_row: int = 11,
    gap: bool = False,
    footer_partial: bool = False,
) -> str:
    rows = [
        '<row r="10">'
        '<c r="A10" t="inlineStr"><is><t>MASKED_HEADER_A</t></is></c>'
        '<c r="C10" t="inlineStr"><is><t>MASKED_HEADER_C</t></is></c>'
        '<c r="Y10" t="inlineStr"><is><t>MASKED_HEADER_Y</t></is></c>'
        "</row>"
    ]
    for row in range(start_row, item_rows + start_row):
        middle = (
            '<c r="C{row}" t="inlineStr"><is><t>{secret}</t></is></c>'.format(
                row=row, secret=escape(secret)
            )
            if not (gap and row == 12)
            else ""
        )
        rows.append(
            '<row r="{row}">'
            '<c r="A{row}" t="inlineStr"><is><t>{secret}</t></is></c>'
            "{middle}"
            '<c r="Y{row}" t="inlineStr"><is><t>{secret}</t></is></c>'
            "</row>".format(row=row, secret=escape(secret), middle=middle)
        )
    if footer_partial:
        footer_row = item_rows + start_row
        rows.append(
            '<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>{secret}</t></is></c></row>'.format(
                row=footer_row, secret=escape(secret)
            )
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


def build_masked_workbook(
    path: Path,
    item_counts: list[int],
    *,
    secret: str = "MASKED_VALUE",
    ambiguous: bool = False,
    duplicate_sheet_identity: bool = False,
    missing_structure: bool = False,
    profile: str = "marker",
    legacy_gap: bool = False,
    legacy_footer_partial: bool = False,
    legacy_sparse_complete_row: int | None = None,
    legacy_first_item_row_missing: bool = False,
) -> None:
    names = [f"MASKED_TEMPLATE_{index:03d}" for index in range(1, len(item_counts) + 1)]
    if duplicate_sheet_identity and len(names) > 1:
        names[1] = names[0]
    relationships = "".join(
        '<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet{index}.xml"/>'.format(index=index)
        for index in range(1, len(names) + 1)
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            _content_types_xml(len(names)),
        )
        archive.writestr("_rels/.rels", _package_relationships_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(names))
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{relationships}</Relationships>",
        )
        for index, count in enumerate(item_counts, start=1):
            content = (
                _legacy_sheet_xml(
                    count,
                    secret=secret,
                    start_row=12 if legacy_first_item_row_missing and index == 1 else 11,
                    gap=legacy_gap and index == 1,
                    footer_partial=legacy_footer_partial,
                )
                if profile == "legacy"
                else _sheet_xml(count, secret=secret, ambiguous=ambiguous)
            )
            if missing_structure and index == 1:
                content = content.replace("HYC_SPEC_IMPORT_V1", "NOT_A_TEMPLATE")
            if legacy_sparse_complete_row is not None and index == 1:
                content = content.replace(
                    "</sheetData>",
                    '<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>MASKED</t></is></c>'
                    '<c r="C{row}" t="inlineStr"><is><t>MASKED</t></is></c>'
                    '<c r="Y{row}" t="inlineStr"><is><t>MASKED</t></is></c></row></sheetData>'.format(
                        row=legacy_sparse_complete_row
                    ),
                )
            archive.writestr(f"xl/worksheets/sheet{index}.xml", content)


def _write_archive(path: Path, members: list[tuple[str, str | bytes]], *, compression: int = zipfile.ZIP_DEFLATED) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, content in members:
                archive.writestr(name, content)


def _mark_archive_encrypted(path: Path) -> None:
    """Set ZIP encryption flags without needing a password-capable writer."""
    contents = bytearray(path.read_bytes())
    for offset in range(len(contents) - 3):
        signature = bytes(contents[offset : offset + 4])
        if signature == b"PK\x03\x04":
            flag_offset = offset + 6
        elif signature == b"PK\x01\x02":
            flag_offset = offset + 8
        else:
            continue
        contents[flag_offset] |= 0x01
    path.write_bytes(contents)


def _corrupt_member(path: Path, member: str) -> None:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(member)
    contents = bytearray(path.read_bytes())
    name_size = int.from_bytes(contents[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_size = int.from_bytes(contents[info.header_offset + 28 : info.header_offset + 30], "little")
    payload_offset = info.header_offset + 30 + name_size + extra_size
    contents[payload_offset] ^= 0xFF
    path.write_bytes(contents)


def _standard_members(
    *,
    content_types: str | bytes | None = None,
    relationships: str | None = None,
    workbook: str | None = None,
    sheet: str | None = None,
) -> list[tuple[str, str]]:
    return [
        (
            "[Content_Types].xml",
            content_types or _content_types_xml(),
        ),
        ("_rels/.rels", _package_relationships_xml()),
        ("xl/workbook.xml", workbook or _workbook_xml(["MASKED_TEMPLATE_001"])),
        (
            "xl/_rels/workbook.xml.rels",
            relationships
            or '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        ),
        ("xl/worksheets/sheet1.xml", sheet or _sheet_xml(1)),
    ]


def run_importer(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(path), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_output(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stderr == ""
    return json.loads(result.stdout)


def assert_failure(result: subprocess.CompletedProcess[str], code: str, *forbidden: str) -> None:
    assert result.returncode == 2
    assert result.stderr == ""
    assert parse_output(result) == {"error_code": code, "schema_version": "hyc.spec-workbook-dry-run.v1"}
    for value in forbidden:
        assert value not in result.stdout


def test_dry_run_reports_masked_structural_counts_and_zero_writes(tmp_path: Path) -> None:
    workbook = tmp_path / "masked.xlsx"
    build_masked_workbook(workbook, [2] * 37 + [45], secret="DO_NOT_DISCLOSE_BUSINESS_VALUE")
    before = workbook.read_bytes()

    result = run_importer(workbook, "--dry-run", "--json")

    assert result.returncode == 0
    report = parse_output(result)
    assert report["schema_version"] == "hyc.spec-workbook-dry-run.v1"
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert report["worksheet_count"] == 38
    assert report["template_count"] == 38
    assert report["item_row_count"] == 119
    assert report["discrepancies"] == [
        {
            "code": "QUALITY_REVIEW_REQUIRED",
            "kind": "SOURCE_DIGEST_MISMATCH",
            "expected": {
                "source_sha256": "b8ebb179b0dece9a6aa06229fe28feb1890082bd32a46e3ccc314febec138c9f"
            },
            "observed": {"source_sha256": hashlib.sha256(before).hexdigest()},
        }
    ]
    assert report["apply_performed"] is False
    assert report["database_writes"] == 0
    assert len(report["sheets"]) == 38
    assert "DO_NOT_DISCLOSE_BUSINESS_VALUE" not in result.stdout
    assert "MASKED_TEMPLATE" not in result.stdout
    assert workbook.read_bytes() == before


def test_repeated_dry_runs_are_byte_identical(tmp_path: Path) -> None:
    workbook = tmp_path / "masked.xlsx"
    build_masked_workbook(workbook, [1])

    first = run_importer(workbook, "--dry-run", "--json")
    second = run_importer(workbook, "--dry-run", "--json")

    assert first.returncode == second.returncode == 0
    assert first.stdout.encode() == second.stdout.encode()


def test_legacy_qm301_profile_reports_masked_structural_counts(tmp_path: Path) -> None:
    workbook = tmp_path / "legacy-masked.xlsx"
    build_masked_workbook(
        workbook,
        [2] * 37 + [45],
        profile="legacy",
        secret="LEGACY_RAW_VALUE_MUST_NOT_APPEAR",
    )
    before = workbook.read_bytes()

    result = run_importer(workbook, "--dry-run", "--json")

    assert result.returncode == 0
    report = parse_output(result)
    assert report["structural_profile"] == "qm301-legacy-structural-v1"
    assert report["template_count"] == 38
    assert report["item_row_count"] == 119
    assert "LEGACY_RAW_VALUE_MUST_NOT_APPEAR" not in result.stdout
    assert "MASKED_TEMPLATE" not in result.stdout
    assert workbook.read_bytes() == before


def test_legacy_qm301_profile_fails_closed_for_noncontiguous_item_rows(tmp_path: Path) -> None:
    workbook = tmp_path / "legacy-gap.xlsx"
    build_masked_workbook(workbook, [3] + [1] * 37, profile="legacy", legacy_gap=True)

    result = run_importer(workbook, "--dry-run", "--json")

    assert_failure(result, "E_ITEM_ROWS_AMBIGUOUS", str(workbook))


def test_legacy_qm301_profile_requires_first_complete_item_row_at_row_11(tmp_path: Path) -> None:
    workbook = tmp_path / "legacy-row-11-deleted.xlsx"
    build_masked_workbook(
        workbook,
        [2] + [1] * 37,
        profile="legacy",
        legacy_first_item_row_missing=True,
    )

    assert_failure(run_importer(workbook, "--dry-run", "--json"), "E_WORKBOOK_STRUCTURE_MISSING", str(workbook))


def test_legacy_qm301_profile_ignores_partial_footer_after_item_block(tmp_path: Path) -> None:
    workbook = tmp_path / "legacy-footer.xlsx"
    build_masked_workbook(
        workbook,
        [2] * 37 + [45],
        profile="legacy",
        legacy_footer_partial=True,
        secret="FOOTER_VALUE_MUST_NOT_APPEAR",
    )

    result = run_importer(workbook, "--dry-run", "--json")

    assert result.returncode == 0
    report = parse_output(result)
    assert report["item_row_count"] == 119
    assert "FOOTER_VALUE_MUST_NOT_APPEAR" not in result.stdout


def test_legacy_qm301_profile_requires_exact_worksheet_count(tmp_path: Path) -> None:
    workbook = tmp_path / "legacy-short.xlsx"
    build_masked_workbook(workbook, [1], profile="legacy")

    result = run_importer(workbook, "--dry-run", "--json")

    assert_failure(result, "E_WORKBOOK_STRUCTURE_MISSING", str(workbook))


def test_count_difference_requires_quality_review_without_auto_correction(tmp_path: Path) -> None:
    workbook = tmp_path / "masked.xlsx"
    build_masked_workbook(workbook, [1])

    report = parse_output(run_importer(workbook, "--dry-run", "--json"))

    assert report["template_count"] == 1
    assert report["item_row_count"] == 1
    assert report["discrepancies"] == [
        {
            "code": "QUALITY_REVIEW_REQUIRED",
            "kind": "SOURCE_DIGEST_MISMATCH",
            "expected": {
                "source_sha256": "b8ebb179b0dece9a6aa06229fe28feb1890082bd32a46e3ccc314febec138c9f"
            },
            "observed": {"source_sha256": report["source_sha256"]},
        },
        {
            "code": "QUALITY_REVIEW_REQUIRED",
            "kind": "STRUCTURAL_COUNT_MISMATCH",
            "expected": {"item_row_count": 119, "template_count": 38},
            "observed": {"item_row_count": 1, "template_count": 1},
        }
    ]
    assert report["apply_performed"] is False


def test_approved_source_digest_with_approved_counts_has_no_provenance_discrepancy() -> None:
    spec = importlib.util.spec_from_file_location("import_spec_workbook_provenance_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    baseline = module.Baseline(
        template_count=38,
        item_row_count=119,
        source_sha256=module.QM301_SOURCE_SHA256,
    )

    assert module._review_discrepancies(baseline, module.QM301_SOURCE_SHA256, 38, 119) == []


def test_dry_run_is_mandatory(tmp_path: Path) -> None:
    workbook = tmp_path / "masked.xlsx"
    build_masked_workbook(workbook, [1])

    result = run_importer(workbook, "--json")

    assert_failure(result, "E_DRY_RUN_REQUIRED", str(workbook))


def test_rejects_non_xlsx_and_malformed_archives(tmp_path: Path) -> None:
    text_file = tmp_path / "not-a-workbook.txt"
    text_file.write_text("not a workbook", encoding="utf-8")
    malformed = tmp_path / "malformed.xlsx"
    malformed.write_bytes(b"not a zip archive")

    assert_failure(run_importer(text_file, "--dry-run", "--json"), "E_INPUT_NOT_XLSX", str(text_file))
    assert_failure(run_importer(malformed, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(malformed))


def test_rejects_missing_input_without_exposing_a_path(tmp_path: Path) -> None:
    result = run_importer(tmp_path / "missing.xlsx", "--dry-run", "--json")

    assert_failure(result, "E_INPUT_NOT_FOUND", "missing.xlsx", str(tmp_path))


def test_fails_closed_for_missing_or_ambiguous_structure(tmp_path: Path) -> None:
    missing = tmp_path / "missing.xlsx"
    no_items = tmp_path / "no-items.xlsx"
    ambiguous = tmp_path / "ambiguous.xlsx"
    duplicate = tmp_path / "duplicate.xlsx"
    build_masked_workbook(missing, [1], missing_structure=True)
    build_masked_workbook(no_items, [0])
    build_masked_workbook(ambiguous, [1], ambiguous=True)
    build_masked_workbook(duplicate, [1, 1], duplicate_sheet_identity=True)

    assert_failure(run_importer(missing, "--dry-run", "--json"), "E_WORKBOOK_STRUCTURE_MISSING", str(missing))
    assert_failure(run_importer(no_items, "--dry-run", "--json"), "E_WORKBOOK_STRUCTURE_MISSING", str(no_items))
    assert_failure(run_importer(ambiguous, "--dry-run", "--json"), "E_ITEM_ROWS_AMBIGUOUS", str(ambiguous))
    assert_failure(run_importer(duplicate, "--dry-run", "--json"), "E_SHEET_IDENTITY_DUPLICATE", str(duplicate))


@pytest.mark.parametrize(
    "xml_declaration",
    [
        '<!DOCTYPE workbook [<!ENTITY xxe "TEST_FIXTURE_SENTINEL_NO_CREDENTIAL">]>',
        '<!ENTITY xxe "TEST_FIXTURE_SENTINEL_NO_CREDENTIAL">',
    ],
)
def test_rejects_duplicate_zip_members_and_dtd_entities_without_disclosure(tmp_path: Path, xml_declaration: str) -> None:
    duplicate = tmp_path / "duplicate-member.xlsx"
    members = _standard_members()
    _write_archive(duplicate, members + [("xl/workbook.xml", members[1][1])])
    dtd = tmp_path / "dtd.xlsx"
    _write_archive(
        dtd,
        _standard_members(
            workbook=xml_declaration + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="MASKED_TEMPLATE_001" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
    )

    assert_failure(run_importer(duplicate, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(duplicate))
    assert_failure(run_importer(dtd, "--dry-run", "--json"), "E_XLSX_MALFORMED", "TEST_FIXTURE_SENTINEL_NO_CREDENTIAL")


def test_rejects_utf16_dtd_entity_without_fixture_sentinel_disclosure(tmp_path: Path) -> None:
    utf16_workbook = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE workbook [<!ENTITY xxe "TEST_FIXTURE_UTF16_SENTINEL_NO_CREDENTIAL">]>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        '<sheet name="&xxe;" sheetId="1" r:id="rId1"/></sheets></workbook>'
    ).encode("utf-16")
    path = tmp_path / "utf16-dtd.xlsx"
    _write_archive(path, _standard_members(workbook=utf16_workbook))

    assert_failure(
        run_importer(path, "--dry-run", "--json"),
        "E_XLSX_MALFORMED",
        "TEST_FIXTURE_UTF16_SENTINEL_NO_CREDENTIAL",
    )


@pytest.mark.parametrize(
    ("content_types", "member_to_corrupt"),
    [
        ("<not-xml", None),
        (
            '<!DOCTYPE Types [<!ENTITY xxe "TEST_FIXTURE_CONTENT_TYPES_SENTINEL_NO_CREDENTIAL">]>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">&xxe;</Types>',
            None,
        ),
        ('<?xml version="1.0"?><NotTypes/>', None),
        (None, "[Content_Types].xml"),
    ],
)
def test_rejects_invalid_dtd_or_corrupt_content_types(tmp_path: Path, content_types: str | None, member_to_corrupt: str | None) -> None:
    path = tmp_path / "content-types.xlsx"
    _write_archive(path, _standard_members(content_types=content_types))
    if member_to_corrupt:
        _corrupt_member(path, member_to_corrupt)

    assert_failure(
        run_importer(path, "--dry-run", "--json"),
        "E_XLSX_MALFORMED",
        "TEST_FIXTURE_CONTENT_TYPES_SENTINEL_NO_CREDENTIAL",
    )


@pytest.mark.parametrize(
    "content_types",
    [
        _content_types_xml().replace(
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"',
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"',
        ),
        _content_types_xml().replace(
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"',
            'ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"',
        ),
        _content_types_xml().replace(
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
            "",
        ),
        _content_types_xml().replace(
            '</Types>',
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
        ),
    ],
)
def test_content_types_requires_one_canonical_xlsx_workbook_override(tmp_path: Path, content_types: str) -> None:
    path = tmp_path / "invalid-workbook-content-type.xlsx"
    _write_archive(path, _standard_members(content_types=content_types))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


@pytest.mark.parametrize(
    ("content_type", "payload", "forbidden"),
    [
        (
            "application/xml",
            '<!DOCTYPE payload [<!ENTITY xxe "TEST_FIXTURE_BIN_XML_SENTINEL_NO_CREDENTIAL">]><payload>&xxe;</payload>',
            "TEST_FIXTURE_BIN_XML_SENTINEL_NO_CREDENTIAL",
        ),
        ("application/vnd.masked+xml", "<payload>", "custom/payload.bin"),
    ],
)
def test_content_type_driven_xml_parsing_rejects_non_xml_named_members(
    tmp_path: Path, content_type: str, payload: str, forbidden: str
) -> None:
    path = tmp_path / "content-type-xml-member.xlsx"
    _write_archive(
        path,
        _standard_members(content_types=_content_types_with(_override_content_type("custom/payload.bin", content_type)))
        + [("custom/payload.bin", payload)],
    )

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", forbidden)


@pytest.mark.parametrize(
    "content_types",
    [
        _content_types_xml().replace(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        ),
        _content_types_xml().replace(
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"', 'ContentType="application/xml"'
        ),
        _content_types_xml().replace(
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>', ""
        ),
        _content_types_with('<Default Extension="RELs" ContentType="application/xml"/>'),
    ],
)
def test_content_type_resolution_rejects_wrong_worksheet_relationship_and_ambiguous_defaults(
    tmp_path: Path, content_types: str
) -> None:
    path = tmp_path / "invalid-resolved-content-type.xlsx"
    _write_archive(path, _standard_members(content_types=content_types))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


def test_standard_content_type_workbook_remains_accepted(tmp_path: Path) -> None:
    path = tmp_path / "standard-content-types.xlsx"
    _write_archive(path, _standard_members())

    assert run_importer(path, "--dry-run", "--json").returncode == 0


@pytest.mark.parametrize(
    "member",
    [
        "xl/media/t one.bin",
        " xl/media/leading.bin",
        "xl/media/trailing.bin ",
        "xl/media/t\tone.bin",
        "xl/media/t\x7fone.bin",
        "xl/media/té.bin",
        "xl/media/t|one.bin",
        "xl/media/t{one}.bin",
        "xl/media/t?one.bin",
        "xl/media/t#one.bin",
        "xl/media/t%ZZ.bin",
        "xl/C:/drive.bin",
    ],
)
def test_zip_members_require_canonical_ascii_opc_uri_path_segments(tmp_path: Path, member: str) -> None:
    path = tmp_path / "invalid-opc-member.xlsx"
    _write_archive(
        path,
        _standard_members(
            content_types=_content_types_with('<Default Extension="bin" ContentType="application/octet-stream"/>')
        )
        + [(member, b"synthetic")],
    )

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


@pytest.mark.parametrize("part_name", ["xl/media/t one.bin", "xl/media/t%ZZ.bin", "xl/media/té.bin"])
def test_content_type_override_part_names_require_canonical_ascii_opc_paths(tmp_path: Path, part_name: str) -> None:
    path = tmp_path / "invalid-override-part-name.xlsx"
    content_types = _content_types_with(_override_content_type(part_name, "application/octet-stream"))
    _write_archive(path, _standard_members(content_types=content_types) + [("xl/media/safe.bin", b"synthetic")])

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


@pytest.mark.parametrize(
    "package_relationships",
    [
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/><Relationship Id="rId2" '
        'Type="http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>",
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="https://example.invalid/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>",
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="https://example.invalid/workbook.xml" TargetMode="External"/></Relationships>',
        '<NotRelationships/>',
    ],
)
def test_package_relationships_require_one_internal_office_document_workbook(
    tmp_path: Path, package_relationships: str
) -> None:
    path = tmp_path / "invalid-package-relationships.xlsx"
    _write_archive(path, [
        (name, package_relationships if name == "_rels/.rels" else content)
        for name, content in _standard_members()
    ])

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


def test_package_relationships_member_is_required(tmp_path: Path) -> None:
    path = tmp_path / "missing-package-relationships.xlsx"
    _write_archive(path, [(name, content) for name, content in _standard_members() if name != "_rels/.rels"])

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("docProps/unused.xml", "<not-xml"),
        (
            "xl/_rels/unused.rels",
            '<!DOCTYPE Relationships [<!ENTITY xxe "TEST_FIXTURE_UNUSED_REL_SENTINEL_NO_CREDENTIAL">]>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">&xxe;</Relationships>',
        ),
    ],
)
def test_rejects_malformed_or_dtd_unused_xml_relationship_parts(tmp_path: Path, name: str, content: str) -> None:
    path = tmp_path / "unused-part.xlsx"
    _write_archive(path, _standard_members() + [(name, content)])

    assert_failure(
        run_importer(path, "--dry-run", "--json"),
        "E_XLSX_MALFORMED",
        "TEST_FIXTURE_UNUSED_REL_SENTINEL_NO_CREDENTIAL",
    )


@pytest.mark.parametrize(
    ("nested_relationships", "extra_members"),
    [
        (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="urn:masked:test" Target="https://example.invalid/media.bin" '
            'TargetMode="External"/></Relationships>',
            [],
        ),
        (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="urn:masked:test" Target="../media/image1.bin"/>'
            '<Relationship Id="rId1" Type="urn:masked:test" Target="../media/image2.bin"/>'
            "</Relationships>",
            [("xl/media/image1.bin", b"synthetic")],
        ),
        (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="urn:masked:test" Target="../media/image%31.bin"/>'
            "</Relationships>",
            [],
        ),
        (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="urn:masked:test" Target="../media/missing.bin"/>'
            "</Relationships>",
            [],
        ),
        ("<NotRelationships/>", []),
    ],
)
def test_every_relationship_part_requires_safe_internal_resolvable_relationships(
    tmp_path: Path, nested_relationships: str, extra_members: list[tuple[str, bytes]]
) -> None:
    path = tmp_path / "invalid-nested-relationships.xlsx"
    _write_archive(
        path,
        _standard_members()
        + [("xl/worksheets/_rels/sheet1.xml.rels", nested_relationships)]
        + extra_members,
    )

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


def test_nested_relationship_allows_internal_parent_traversal_that_stays_in_package(tmp_path: Path) -> None:
    path = tmp_path / "nested-internal-parent.xlsx"
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="urn:masked:test" Target="../media/image1.bin"/></Relationships>'
    )
    _write_archive(
        path,
        _standard_members(content_types=_content_types_with('<Default Extension="bin" ContentType="application/octet-stream"/>'))
        + [("xl/worksheets/_rels/sheet1.xml.rels", relationships), ("xl/media/image1.bin", b"synthetic")],
    )

    assert run_importer(path, "--dry-run", "--json").returncode == 0


@pytest.mark.parametrize(
    "target",
    [
        "../media/t one.bin",
        " ../media/image1.bin",
        "../media/image1.bin ",
        "../media/t\tone.bin",
        "../media/t&#x7F;one.bin",
        "../media/té.bin",
        "../media/t|one.bin",
        "../media/t^one.bin",
        "../media/t%ZZ.bin",
        "C:/media/image1.bin",
    ],
)
def test_relationship_targets_require_canonical_ascii_opc_uri_paths(tmp_path: Path, target: str) -> None:
    path = tmp_path / "invalid-relationship-target-lexical.xlsx"
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="urn:masked:test" Target="{target}"/></Relationships>'
    )
    _write_archive(
        path,
        _standard_members(content_types=_content_types_with('<Default Extension="bin" ContentType="application/octet-stream"/>'))
        + [("xl/worksheets/_rels/sheet1.xml.rels", relationships), ("xl/media/image1.bin", b"synthetic")],
    )

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


@pytest.mark.parametrize(
    "relationship",
    [
        '<Relationship Id="1invalid" Type="urn:masked:test" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="not-a-uri" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="urn:masked|invalid" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="urn:%ZZ" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="urn:masked value" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="urn:masked&#x9;value" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="urn:마스크" Target="worksheets/sheet1.xml"/>',
        '<Relationship Id="rId1" Type="urn:masked:test" Target="worksheets/sheet1.xml"><Unexpected/></Relationship>',
        '<Relationship Id="rId1" Type="urn:masked:test" Target="worksheets/sheet1.xml">unexpected</Relationship>',
        '<Relationship Id="rId1" Type="urn:masked:test" Target="worksheets/sheet1.xml" Extra="unexpected"/>',
    ],
)
def test_relationship_elements_require_strict_id_type_and_empty_structure(tmp_path: Path, relationship: str) -> None:
    path = tmp_path / "invalid-relationship-element.xlsx"
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relationship}</Relationships>"
    )
    _write_archive(path, _standard_members(relationships=relationships))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


def test_root_level_relationship_source_and_urn_type_are_accepted_when_internal_target_exists(tmp_path: Path) -> None:
    path = tmp_path / "root-level-relationship-source.xlsx"
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="urn:masked:relationship" Target="target.bin"/></Relationships>'
    )
    _write_archive(
        path,
        _standard_members(content_types=_content_types_with('<Default Extension="bin" ContentType="application/octet-stream"/>'))
        + [("foo.xml", "<payload/>"), ("_rels/foo.xml.rels", relationships), ("target.bin", b"synthetic")],
    )

    assert run_importer(path, "--dry-run", "--json").returncode == 0


def test_relationship_type_accepts_rfc3986_percent_encoding_and_duplicate_targets(tmp_path: Path) -> None:
    path = tmp_path / "valid-relationship-uri-and-shared-target.xlsx"
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="urn:masked:relationship%2Fv1" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    _write_archive(path, _standard_members(relationships=relationships))

    # OPC permits distinct typed relationship IDs to reference one part.
    assert run_importer(path, "--dry-run", "--json").returncode == 0


@pytest.mark.parametrize(
    "relationships",
    [
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" Extra="unexpected">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n  '
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>\n</Relationships>',
    ],
)
def test_relationship_root_rejects_attributes_but_preserves_whitespace_only_content(
    tmp_path: Path, relationships: str
) -> None:
    path = tmp_path / "relationship-root-structure.xlsx"
    _write_archive(path, _standard_members(relationships=relationships))

    result = run_importer(path, "--dry-run", "--json")
    if 'Extra="unexpected"' in relationships:
        assert_failure(result, "E_XLSX_MALFORMED", str(path))
    else:
        assert result.returncode == 0


@pytest.mark.parametrize(
    ("relationships", "workbook", "expected"),
    [
        (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            "</Relationships>",
            None,
            "E_XLSX_MALFORMED",
        ),
        (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="/absolute/sheet.xml"/>'
            "</Relationships>",
            None,
            "E_XLSX_MALFORMED",
        ),
        (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="https://example.invalid/sheet.xml" TargetMode="External"/>'
            "</Relationships>",
            None,
            "E_XLSX_MALFORMED",
        ),
        (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="../outside.xml"/>'
            "</Relationships>",
            None,
            "E_XLSX_MALFORMED",
        ),
        (
            None,
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="ONE" sheetId="1" r:id="rId1"/><sheet name="TWO" sheetId="2" r:id="rId1"/>'
            "</sheets></workbook>",
            "E_XLSX_MALFORMED",
        ),
        (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="ONE" sheetId="1" r:id="rId1"/><sheet name="TWO" sheetId="2" r:id="rId2"/>'
            "</sheets></workbook>",
            "E_XLSX_MALFORMED",
        ),
    ],
)
def test_rejects_ambiguous_or_nonlocal_relationships(
    tmp_path: Path, relationships: str | None, workbook: str | None, expected: str
) -> None:
    path = tmp_path / "relationship-sentinel.xlsx"
    _write_archive(path, _standard_members(relationships=relationships, workbook=workbook))

    assert_failure(run_importer(path, "--dry-run", "--json"), expected, "relationship-sentinel.xlsx")


def test_rejects_unsupported_encrypted_corrupt_and_oversized_inputs_before_hashing(tmp_path: Path) -> None:
    unsupported = tmp_path / "unsupported.xlsx"
    _write_archive(unsupported, _standard_members(), compression=zipfile.ZIP_BZIP2)
    corrupt = tmp_path / "corrupt.xlsx"
    _write_archive(corrupt, _standard_members())
    _corrupt_member(corrupt, "xl/workbook.xml")
    encrypted = tmp_path / "encrypted.xlsx"
    _write_archive(encrypted, _standard_members())
    _mark_archive_encrypted(encrypted)
    oversized = tmp_path / "oversized.xlsx"
    with oversized.open("wb") as stream:
        stream.truncate(33 * 1024 * 1024)

    assert_failure(run_importer(unsupported, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(unsupported))
    assert_failure(run_importer(corrupt, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(corrupt))
    assert_failure(run_importer(encrypted, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(encrypted))
    assert_failure(run_importer(oversized, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(oversized))


def test_rejects_crc_corruption_in_synthetic_non_xml_member(tmp_path: Path) -> None:
    path = tmp_path / "corrupt-media-member.xlsx"
    _write_archive(path, _standard_members() + [("xl/media/image1.bin", b"synthetic-binary-member")])
    _corrupt_member(path, "xl/media/image1.bin")

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


def test_marker_profile_rejects_noncontiguous_invalid_row_references_and_non_a_marker(tmp_path: Path) -> None:
    cases = {
        "resumed": _sheet_xml(1).replace("</sheetData>", '<row r="5"><c r="A5" t="inlineStr"><is><t>ITEM_ROW</t></is></c></row></sheetData>'),
        "gap": _sheet_xml(1).replace('r="A3"', 'r="A4"').replace('r="B3"', 'r="B4"').replace('<row r="3">', '<row r="4">'),
        "out-of-order": _sheet_xml(1).replace('<row r="2">', '<row r="3"><c r="A3" t="inlineStr"><is><t>ITEM_ROW</t></is></c></row><row r="2">'),
        "duplicate-row": _sheet_xml(1).replace("</sheetData>", '<row r="3"><c r="B3" t="inlineStr"><is><t>footer</t></is></c></row></sheetData>'),
        "wrong-cell-row": _sheet_xml(1).replace('r="A3"', 'r="A4"'),
        "aa-marker": _sheet_xml(1).replace('r="A3"', 'r="AA3"'),
    }
    for label, sheet in cases.items():
        path = tmp_path / f"{label}.xlsx"
        _write_archive(path, _standard_members(sheet=sheet))
        assert_failure(
            run_importer(path, "--dry-run", "--json"),
            "E_ITEM_ROWS_AMBIGUOUS" if label in {"resumed", "gap", "aa-marker"} else "E_XLSX_MALFORMED",
            str(path),
        )


def test_shared_strings_are_supported_but_invalid_indexes_fail_closed(tmp_path: Path) -> None:
    shared = (
        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<si><t>HYC_SPEC_IMPORT_V1</t></si><si><t>ITEM_ROW</t></si></sst>"
    )
    sheet = (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="A3" t="s"><v>1</v></c></row></sheetData></worksheet>'
    )
    good = tmp_path / "shared-good.xlsx"
    content_types = _content_types_with(
        _override_content_type(
            "xl/sharedStrings.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
        )
    )
    _write_archive(good, _standard_members(sheet=sheet, content_types=content_types) + [("xl/sharedStrings.xml", shared)])
    bad = tmp_path / "shared-bad.xlsx"
    _write_archive(
        bad,
        _standard_members(
            sheet=sheet.replace("<v>1</v></c></row></sheetData>", "<v>99</v></c></row></sheetData>"),
            content_types=content_types,
        )
        + [("xl/sharedStrings.xml", shared)],
    )

    assert run_importer(good, "--dry-run", "--json").returncode == 0
    assert_failure(run_importer(bad, "--dry-run", "--json"), "E_XLSX_MALFORMED")


@pytest.mark.parametrize(
    "content_types",
    [
        _content_types_with(_override_content_type("xl/sharedStrings.xml", "application/xml")),
        _content_types_xml(),
    ],
)
def test_shared_strings_requires_exact_content_type_when_present(tmp_path: Path, content_types: str) -> None:
    path = tmp_path / "shared-strings-content-type.xlsx"
    _write_archive(
        path,
        _standard_members(content_types=content_types)
        + [("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')],
    )

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED", str(path))


@pytest.mark.parametrize("invalid_index", ["-1", "+1", " 1", "1 "])
def test_shared_string_indices_must_be_canonical_nonnegative_decimals(tmp_path: Path, invalid_index: str) -> None:
    shared = (
        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<si><t>HYC_SPEC_IMPORT_V1</t></si><si><t>ITEM_ROW</t></si></sst>"
    )
    sheet = (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="A3" t="s"><v>1</v></c></row></sheetData></worksheet>'
    )
    path = tmp_path / "invalid-shared-index.xlsx"
    _write_archive(
        path,
        _standard_members(sheet=sheet.replace("<v>1</v>", f"<v>{invalid_index}</v>", 1))
        + [("xl/sharedStrings.xml", shared)],
    )

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED")


@pytest.mark.parametrize(
    "workbook, relationships",
    [
        (
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="ONE" sheetId="1" r:id="rId1"/><sheet name="TWO" sheetId="1" r:id="rId2"/>'
            "</sheets></workbook>",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            "</Relationships>",
        ),
        (_workbook_xml(["ONE"]).replace(' sheetId="1"', ""), None),
        (_workbook_xml(["ONE"]).replace('sheetId="1"', 'sheetId="0"'), None),
        (_workbook_xml(["ONE"]).replace('sheetId="1"', 'sheetId="01"'), None),
    ],
)
def test_sheet_ids_must_be_unique_positive_canonical_decimals(
    tmp_path: Path, workbook: str, relationships: str | None
) -> None:
    path = tmp_path / "invalid-sheet-id.xlsx"
    _write_archive(path, _standard_members(workbook=workbook, relationships=relationships))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED")


def test_rejects_spoofed_worksheet_relationship_type(tmp_path: Path) -> None:
    relationships = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="https://attacker.invalid/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    path = tmp_path / "spoofed-worksheet-type.xlsx"
    _write_archive(path, _standard_members(relationships=relationships))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED")


def test_accepts_official_strict_worksheet_relationship_type(tmp_path: Path) -> None:
    relationships = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet" '
        'Target="worksheets/sheet1.xml" TargetMode="Internal"/></Relationships>'
    )
    path = tmp_path / "strict-worksheet-type.xlsx"
    _write_archive(path, _standard_members(relationships=relationships))

    assert run_importer(path, "--dry-run", "--json").returncode == 0


@pytest.mark.parametrize(
    "replacement",
    [
        ('<row r="3">', '<row r="1048577">'),
        ('r="B3"', 'r="XFE3"'),
    ],
)
def test_rejects_excel_addresses_beyond_supported_maxima(tmp_path: Path, replacement: tuple[str, str]) -> None:
    path = tmp_path / "out-of-range-address.xlsx"
    _write_archive(path, _standard_members(sheet=_sheet_xml(1).replace(*replacement)))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED")


def test_legacy_sparse_huge_row_is_bounded_and_fails_stably(tmp_path: Path) -> None:
    path = tmp_path / "huge-sparse-row.xlsx"
    build_masked_workbook(
        path,
        [1] * 38,
        profile="legacy",
        legacy_sparse_complete_row=1_048_576,
    )

    started = time.monotonic()
    first = run_importer(path, "--dry-run", "--json")
    elapsed = time.monotonic() - started
    second = run_importer(path, "--dry-run", "--json")

    assert elapsed < 2
    assert_failure(first, "E_ITEM_ROWS_AMBIGUOUS")
    assert second.stdout == first.stdout


@pytest.mark.parametrize(
    "target, target_mode",
    [
        ("worksheets/sheet%31.xml", None),
        ("worksheets/sheet1.xml?query", None),
        ("worksheets/sheet1.xml#fragment", None),
        ("worksheets/sheet1.xml", "Unknown"),
    ],
)
def test_rejects_unsafe_relationship_targets_and_modes(
    tmp_path: Path, target: str, target_mode: str | None
) -> None:
    mode = "" if target_mode is None else f' TargetMode="{target_mode}"'
    relationships = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="{target}"{mode}/></Relationships>'
    )
    path = tmp_path / "unsafe-relationship.xlsx"
    _write_archive(path, _standard_members(relationships=relationships))

    assert_failure(run_importer(path, "--dry-run", "--json"), "E_XLSX_MALFORMED")


def test_input_mutation_after_first_hash_fails_closed_stably(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / "mutated-after-hash.xlsx"
    build_masked_workbook(workbook, [1])
    spec = importlib.util.spec_from_file_location("import_spec_workbook_mutation_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    original_hash = module._hash_open_file
    calls = 0

    def hash_then_mutate(source: object) -> str:
        nonlocal calls
        calls += 1
        digest = original_hash(source)
        if calls == 1:
            with workbook.open("ab") as changed:
                changed.write(b"mutation")
        return digest

    monkeypatch.setattr(module, "_hash_open_file", hash_then_mutate)

    assert module.main(["--input", str(workbook), "--dry-run", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"error_code": "E_INPUT_CHANGED", "schema_version": "hyc.spec-workbook-dry-run.v1"}


def test_formula_and_external_link_like_text_are_not_emitted_or_fetched(tmp_path: Path) -> None:
    sentinel = "EXTERNAL_NETWORK_SENTINEL"
    path = tmp_path / "formula.xlsx"
    sheet = _sheet_xml(1).replace(
        '<c r="B3" t="inlineStr"><is><t>MASKED_VALUE</t></is></c>',
        f'<c r="B3"><f>WEBSERVICE("https://example.invalid/{sentinel}")</f><v>{sentinel}</v></c>',
    )
    _write_archive(path, _standard_members(sheet=sheet))

    result = run_importer(path, "--dry-run", "--json")
    assert result.returncode == 0
    assert result.stderr == ""
    assert sentinel not in result.stdout


@pytest.mark.parametrize(
    "mutation",
    [
        lambda fixture: fixture.__setitem__("unexpected", True),
        lambda fixture: fixture["approved_structural_expectations"].__setitem__("template_count", True),
        lambda fixture: fixture["approved_structural_expectations"].__setitem__("item_row_count", -119),
        lambda fixture: fixture["approved_structural_expectations"].__setitem__("template_count", "38"),
        lambda fixture: fixture["source_reference"].pop("source_sha256"),
        lambda fixture: fixture["source_reference"].__setitem__("unknown", "value"),
        lambda fixture: fixture["source_reference"].__setitem__("p0a_evidence_schema_version", 1.0),
        lambda fixture: fixture["discrepancy_policy"].__setitem__("auto_correct", "false"),
        lambda fixture: fixture["discrepancy_policy"].__setitem__("apply_performed", 0),
        lambda fixture: fixture["discrepancy_policy"].__setitem__("when_actual_differs", "AUTO_CORRECT"),
    ],
)
def test_baseline_rejects_incomplete_or_noncanonical_expectation_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: object
) -> None:
    fixture = json.loads((REPO_ROOT / "fixtures/spec-import/qm301-7-expected.json").read_text(encoding="utf-8"))
    mutation(fixture)  # type: ignore[operator]
    fixture_path = tmp_path / "invalid-expectations.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("import_spec_workbook_baseline_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "EXPECTATION_FIXTURE_PATH", fixture_path)

    with pytest.raises(module.DryRunFailure, match="E_EXPECTATION_FIXTURE_INVALID"):
        module._baseline()


def test_cli_argument_errors_and_unexpected_exception_are_stable_json(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    workbook = tmp_path / "masked.xlsx"
    build_masked_workbook(workbook, [1])
    assert_failure(run_importer(workbook, "--dry-run"), "E_JSON_REQUIRED")
    invalid = subprocess.run([sys.executable, str(SCRIPT), "--bogus"], text=True, capture_output=True, check=False)
    assert_failure(invalid, "E_ARGUMENTS_INVALID")

    spec = importlib.util.spec_from_file_location("import_spec_workbook_for_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "parse_dry_run", lambda _: (_ for _ in ()).throw(Exception("raw sentinel")))
    assert module.main(["--input", str(workbook), "--dry-run", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"error_code": "E_UNEXPECTED", "schema_version": "hyc.spec-workbook-dry-run.v1"}
    assert "raw sentinel" not in captured.out
