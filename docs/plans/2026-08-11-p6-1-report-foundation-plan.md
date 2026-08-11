# P6-1 보고서 공통 틀 + 통합 검사보고서 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 검사 건 하나를 PRD §16.2 통합 검사보고서 Excel로 출력하는 흐름을 만들고, 이후 모든 보고서가 재사용할 비동기 Job 실행 틀을 함께 완성한다.

**Architecture:** `POST /api/v1/reports`가 `Idempotency-Key`를 요구하고 `202 Accepted` + Job ID를 반환한다. 실행은 API 프로세스 안의 `ReportRunner` 포트 구현체가 맡고, 나중에 워커로 옮겨도 HTTP 표면이 바뀌지 않는다. 생성된 바이트는 `documents`와 물리적으로 분리된 별도 저장소 루트에 content-addressed로 쓰이고 `report_artifacts` 행이 그것을 가리킨다. 보고서 본문은 판정값을 `decision_snapshots`에서만 읽고, 명칭·부적합·첨부 같은 참조 정보는 조회 시점 DB에서 읽되 출처 라벨을 셀로 함께 출력한다.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / PostgreSQL / openpyxl(신규) / Next.js 15 / Vitest

**선행 문서:** [`2026-08-11-p6-operations-scope-plan.md`](2026-08-11-p6-operations-scope-plan.md) — 범위·설계 결정 D1~D4와 §4 스냅샷 이원화가 이 계획의 근거다.

---

## Global Constraints

- **Alembic head는 `20260810_0007`이다.** 이 계획은 `20260811_0008` 하나만 추가한다. 리비전은 **순수 DDL**이어야 한다 (마이그레이션 metadata 독립성 계약).
- **`DBAPIError`를 통째로 409로 매핑하지 않는다.** `routes/nonconformances.py:106`의 `_is_domain_invariant_violation`을 재사용해 SQLSTATE `P0001`만 409로 좁힌다. 인프라 장애가 업무 충돌로 위장되면 무의미한 재시도를 유발하고 장애를 은폐한다.
- **`contracts/openapi.json`을 재생성하면 `frontend/src/lib/api/generated.ts`도 함께 재생성해야** `make contracts-check`가 통과한다.
- **프론트 신규 컴포넌트는 `canUseBackend` 가드를 통과해야 한다.** `publicDemo=true`에서 fetch 0회를 회귀로 고정하고 **반드시 `publicDemo=false` 양성 대조군을 함께 둔다.** 대조군 없는 zero-fetch 단언은 마운트 실패로도 통과하는 헛돈 테스트다.
- **판정값을 쓰는 코드 경로를 만들지 않는다.** 보고서는 검사·판정·승인 상태를 읽기만 한다.
- **산출물 삭제/만료 경로를 만들지 않는다.** 보존 정책(RET-001/AP-08)은 미승인이다.
- **OCR KPI 임계값, 샘플링 정책, 부적합 severity 기준을 만들지 않는다.**
- `make p3-e2e` 실행 시 `COMPOSE_BAKE=false`를 붙인다 (저장소 경로에 비ASCII 문자가 있어 Docker bake가 실패).
- `scripts/scan_secrets.py`의 `APPROVED_FIXTURES` 등재 파일을 수정하면 SHA-256을 갱신한다.
- Git 정책은 Mode A다. 각 Task의 커밋 단계는 **명시적 지시가 있을 때만** 수행한다. 지시가 없으면 파일 수정과 검증까지만 하고 커밋하지 않는다.

---

## File Structure

|경로|책임|
|---|---|
|`backend/alembic/versions/20260811_0008_report_jobs_and_artifacts.py`|`report_jobs`/`report_artifacts` DDL + 불변성 트리거 2종|
|`backend/src/hyc_data/models.py` (수정)|`ReportJob`, `ReportArtifact` ORM 매핑 추가|
|`backend/src/hyc_api/reports/deterministic.py`|openpyxl 워크북을 결정론적 바이트로 만드는 유일한 통로. DB·HTTP 의존 없음|
|`backend/src/hyc_api/reports/integrated.py`|REP-002 통합 검사보고서 시트 구성. 스냅샷/조회 출처 라벨 부착|
|`backend/src/hyc_api/reports/sources.py`|보고서 입력 수집. 스냅샷 읽기와 참조 정보 조회를 **명시적으로 분리**한 두 함수|
|`backend/src/hyc_api/services/reports.py`|Job 수명주기, `ReportRunner` 포트, 산출물 저장|
|`backend/src/hyc_api/routes/reports.py`|HTTP 표면. Idempotency, 상태 폴링, 다운로드, 감사|
|`backend/src/hyc_api/contracts.py` (수정)|요청/응답 Pydantic 모델|
|`backend/src/hyc_api/config.py` (수정)|`p6_report_storage_root` 설정|
|`backend/src/hyc_api/main.py` (수정)|라우터 등록|
|`backend/scripts/check_migrations.py` (수정)|신규 트리거 2종을 계약으로 검증|
|`frontend/src/components/reports/ReportPanel.tsx`|생성 요청 → 진행 표시 → 다운로드|

**분리 근거:** `deterministic.py`는 DB를 모른다. 그래서 재현성 테스트가 DB 없이 밀리초 단위로 돈다. `sources.py`가 스냅샷과 조회를 두 함수로 갈라 놓기 때문에 "판정값이 조회 결과로 오염됐다"는 사고를 타입 수준에서 잡을 수 있다.

---

## Task 1: 결정론적 워크북 기반

가장 위험한 항목을 DB 없이 먼저 잠근다. openpyxl은 기본적으로 워크북 메타에 생성 시각을 넣어 **같은 데이터라도 저장할 때마다 바이트가 달라진다.** 이걸 잡지 못하면 이후 모든 재현성 테스트가 불규칙하게 깨진다.

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/src/hyc_api/reports/__init__.py`
- Create: `backend/src/hyc_api/reports/deterministic.py`
- Test: `backend/tests/unit/reports/test_deterministic_workbook.py`

**Interfaces:**
- Produces:
  - `SheetSpec = dataclass(title: str, rows: list[list[str]])`
  - `render_workbook(sheets: Sequence[SheetSpec]) -> bytes`
  - `workbook_digest(payload: bytes) -> str` — 소문자 hex SHA-256

- [ ] **Step 1: openpyxl 의존성 추가**

`backend/pyproject.toml`의 `dependencies` 배열에 추가한다. optional이 아니다 — 보고서는 기본 기능이다.

```toml
    "openpyxl>=3.1,<4",
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/unit/reports/__init__.py`를 빈 파일로 만들고, 아래를 `test_deterministic_workbook.py`로 저장한다.

```python
from __future__ import annotations

import io
import zipfile

from hyc_api.reports.deterministic import SheetSpec, render_workbook, workbook_digest

_SHEETS = (
    SheetSpec(title="Summary", rows=[["항목", "값"], ["판정", "ACCEPTED"]]),
    SheetSpec(title="Items", rows=[["코드", "결과"], ["CA-01", "3.14"]]),
)


def test_same_input_renders_identical_bytes() -> None:
    first = render_workbook(_SHEETS)
    second = render_workbook(_SHEETS)
    assert workbook_digest(first) == workbook_digest(second)
    assert first == second


def test_zip_member_timestamps_are_pinned() -> None:
    # openpyxl writes the current clock into every zip member; an unpinned
    # timestamp makes the digest change once per second.
    with zipfile.ZipFile(io.BytesIO(render_workbook(_SHEETS))) as archive:
        stamps = {info.date_time for info in archive.infolist()}
    assert stamps == {(1980, 1, 1, 0, 0, 0)}


def test_changed_cell_changes_the_digest() -> None:
    # Guards against a render that pins so much it stops reflecting input.
    changed = (
        SheetSpec(title="Summary", rows=[["항목", "값"], ["판정", "REJECTED"]]),
        _SHEETS[1],
    )
    assert workbook_digest(render_workbook(_SHEETS)) != workbook_digest(render_workbook(changed))


def test_sheet_titles_and_cells_survive_the_round_trip() -> None:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(render_workbook(_SHEETS)))
    assert workbook.sheetnames == ["Summary", "Items"]
    assert workbook["Items"].cell(row=2, column=1).value == "CA-01"
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports/test_deterministic_workbook.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hyc_api.reports'`

- [ ] **Step 4: 구현**

`backend/src/hyc_api/reports/__init__.py`는 빈 파일로 만든다. `deterministic.py`:

```python
from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass

from openpyxl import Workbook

_PINNED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


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
    workbook.properties.created = None
    workbook.properties.modified = None
    workbook.properties.creator = ""
    workbook.properties.lastModifiedBy = ""
    buffer = io.BytesIO()
    workbook.save(buffer)
    return _pin_archive(buffer.getvalue())


def workbook_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 5: 테스트 통과 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports/test_deterministic_workbook.py
```

Expected: 4 passed.

`workbook.properties.created = None`이 openpyxl 버전에 따라 거부되면 `datetime(1980, 1, 1, tzinfo=UTC)` 같은 **고정 상수**로 대체한다. 현재 시각만 들어가지 않으면 계약은 성립한다.

- [ ] **Step 6: 잠금파일 갱신과 정적 게이트**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend ruff check backend
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend mypy --strict backend/src
```

Expected: 둘 다 통과. mypy 파일 수가 77에서 늘어난다.

---

## Task 2: 마이그레이션과 ORM 모델

**Files:**
- Create: `backend/alembic/versions/20260811_0008_report_jobs_and_artifacts.py`
- Modify: `backend/src/hyc_data/models.py`
- Modify: `backend/scripts/check_migrations.py:51-60` 부근
- Test: `backend/tests/integration/db/test_report_artifact_immutability.py`

**Interfaces:**
- Consumes: 없음
- Produces: `ReportJob`, `ReportArtifact` ORM 클래스

**설계 요지**

- `report_jobs.state`는 `QUEUED`/`RUNNING`/`SUCCEEDED`/`FAILED` allowlist CHECK.
- `report_artifacts`는 성공한 job당 최대 1건. **UPDATE/DELETE를 트리거로 거부**한다 — 산출물이 바뀌면 "그때 받은 그 파일"을 증명할 수 없다.
- **삭제 경로를 만들지 않는다.** 보존 정책 미승인이므로 만료·정리 컬럼을 두지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/integration/db/test_report_artifact_immutability.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgres

_DOMAIN_INVARIANT_SQLSTATE = "P0001"


def _sqlstate(error: DBAPIError) -> str | None:
    original = getattr(error, "orig", None)
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


def test_report_artifact_update_is_rejected(postgres_session) -> None:
    job_id, artifact_id = _seed_succeeded_job(postgres_session)
    with pytest.raises(DBAPIError) as caught:
        postgres_session.execute(
            text("UPDATE report_artifacts SET byte_size = 1 WHERE id = :id"),
            {"id": artifact_id},
        )
    postgres_session.rollback()
    assert _sqlstate(caught.value) == _DOMAIN_INVARIANT_SQLSTATE


def test_report_artifact_delete_is_rejected(postgres_session) -> None:
    job_id, artifact_id = _seed_succeeded_job(postgres_session)
    with pytest.raises(DBAPIError) as caught:
        postgres_session.execute(
            text("DELETE FROM report_artifacts WHERE id = :id"), {"id": artifact_id}
        )
    postgres_session.rollback()
    assert _sqlstate(caught.value) == _DOMAIN_INVARIANT_SQLSTATE


def test_report_artifact_insert_still_works(postgres_session) -> None:
    # Without this the two denial tests could pass on a table that rejects
    # everything, including the write path the feature depends on.
    job_id, artifact_id = _seed_succeeded_job(postgres_session)
    stored = postgres_session.execute(
        text("SELECT content_digest FROM report_artifacts WHERE id = :id"), {"id": artifact_id}
    ).scalar_one()
    assert len(stored) == 64
```

`_seed_succeeded_job`은 같은 디렉터리 기존 테스트의 시딩 헬퍼 패턴을 따라 작성한다. 인접 파일(`test_evidence_immutability.py`)에서 fixture 이름과 시딩 방식을 먼저 확인한 뒤 맞춘다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

```
COMPOSE_BAKE=false make p3-postgres-check
```

Expected: FAIL — `relation "report_artifacts" does not exist`

- [ ] **Step 3: 마이그레이션 작성**

`20260811_0008_report_jobs_and_artifacts.py`. `20260810_0007`의 구조(role grant 가드, `_ROLE` 정규식)를 그대로 따른다.

```python
"""Add report job and immutable report artifact tables.

Revision ID: 20260811_0008
Revises: 20260810_0007
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260811_0008"
down_revision = "20260810_0007"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "report_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("requested_by_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name="ck_report_job_state_allowlist",
        ),
        sa.CheckConstraint(
            "(state <> 'FAILED') OR (failure_code IS NOT NULL)",
            name="ck_report_job_failure_code_present",
        ),
    )
    op.create_table(
        "report_artifacts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("report_job_id", uuid, nullable=False, unique=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["report_job_id"], ["report_jobs.id"], name="fk_report_artifacts_report_job"
        ),
        sa.CheckConstraint("length(content_digest) = 64", name="ck_report_artifact_digest_length"),
        sa.CheckConstraint(
            "content_digest = lower(content_digest)", name="ck_report_artifact_digest_lowercase"
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_report_artifact_byte_size_positive"),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION hyc_deny_report_artifact_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'report artifacts are immutable once written';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_report_artifact_immutable
        BEFORE UPDATE OR DELETE ON report_artifacts
        FOR EACH ROW EXECUTE FUNCTION hyc_deny_report_artifact_mutation();
        """
    )
    role = os.environ.get("HYC_APP_ROLE", "hyc_app")
    if not _ROLE.fullmatch(role):
        raise RuntimeError("invalid HYC_APP_ROLE")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            GRANT SELECT, INSERT, UPDATE ON report_jobs TO {role};
            GRANT SELECT, INSERT ON report_artifacts TO {role};
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_report_artifact_immutable ON report_artifacts;")
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_report_artifact_mutation();")
    op.drop_table("report_artifacts")
    op.drop_table("report_jobs")
```

`report_jobs`에만 `UPDATE` 권한을 준다. 상태 전이가 필요하기 때문이다. `report_artifacts`에는 주지 않는다.

- [ ] **Step 4: ORM 모델 추가**

`backend/src/hyc_data/models.py`의 `AuditLog` 정의 앞에 추가한다. 파일의 기존 import와 `utc_now`, `lower_hex_check` 헬퍼를 재사용한다.

```python
class ReportJob(Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name="ck_report_job_state_allowlist",
        ),
        CheckConstraint(
            "(state <> 'FAILED') OR (failure_code IS NOT NULL)",
            name="ck_report_job_failure_code_present",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    requested_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        CheckConstraint("length(content_digest) = 64", name="ck_report_artifact_digest_length"),
        CheckConstraint(
            lower_hex_check("content_digest"), name="ck_report_artifact_digest_lowercase"
        ),
        CheckConstraint("byte_size > 0", name="ck_report_artifact_byte_size_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    report_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_jobs.id"), unique=True, nullable=False
    )
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
```

- [ ] **Step 5: 트리거를 마이그레이션 계약에 등재**

`backend/scripts/check_migrations.py`에서 `EXPECTED_NCR_TRIGGER_FUNCTIONS` / `EXPECTED_NCR_TRIGGERS` 정의(51~60행 부근)를 찾아 같은 모양으로 추가하고, 그 아래 head 검사(167~170행)와 downgrade 검사에 동일하게 끼워 넣는다.

```python
EXPECTED_REPORT_TRIGGER_FUNCTIONS: frozenset[str] = frozenset(
    {"hyc_deny_report_artifact_mutation"}
)
EXPECTED_REPORT_TRIGGERS: frozenset[str] = frozenset({"trg_report_artifact_immutable"})
```

head 검사부:

```python
                if not EXPECTED_REPORT_TRIGGER_FUNCTIONS.issubset(functions):
                    raise RuntimeError("report trigger functions are incomplete at head")
                if not EXPECTED_REPORT_TRIGGERS.issubset(triggers):
                    raise RuntimeError("report mutation triggers are incomplete at head")
```

downgrade 검사부는 `intersection`을 쓰는 기존 블록과 동일한 형태로 잔존 여부를 확인한다.

- [ ] **Step 6: 테스트 통과 확인**

```
COMPOSE_BAKE=false make p3-postgres-check
make migration-check
```

Expected: 신규 3건 포함해 통과. `p3-postgres-check`는 이전 125에서 128로 오른다.

---

## Task 3: 보고서 종류와 파라미터 정규화

Job 파라미터가 정규화되지 않으면 같은 요청이 다른 `request_hash`를 만들어 Idempotency가 무의미해진다.

**Files:**
- Create: `backend/src/hyc_domain/reports.py`
- Test: `backend/tests/unit/reports/test_report_parameters.py`

**Interfaces:**
- Produces:
  - `class ReportKind(StrEnum)` — 값 `INTEGRATED_INSPECTION`
  - `canonical_report_parameters(kind: ReportKind, raw: Mapping[str, Any]) -> dict[str, Any]`
  - `class UnsupportedReportKind(CodedDomainError)`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from __future__ import annotations

import pytest

from hyc_domain.reports import (
    ReportKind,
    UnsupportedReportKind,
    canonical_report_parameters,
)

_CASE = "3f1d9c8e-0b2a-4c7d-9e1f-5a6b7c8d9e0f"


def test_key_order_does_not_change_the_canonical_form() -> None:
    first = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE, "include_audit": True}
    )
    second = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"include_audit": True, "inspection_case_id": _CASE}
    )
    assert first == second
    assert list(first) == sorted(first)


def test_uuid_case_is_normalised() -> None:
    upper = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE.upper()}
    )
    assert upper["inspection_case_id"] == _CASE


def test_unknown_parameter_is_rejected() -> None:
    # Silently dropping an unknown key would make two different requests share
    # one idempotency hash and return each other's artifact.
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(
            ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE, "surprise": 1}
        )


def test_missing_required_parameter_is_rejected() -> None:
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(ReportKind.INTEGRATED_INSPECTION, {})


def test_include_audit_defaults_to_false() -> None:
    result = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE}
    )
    assert result["include_audit"] is False
```

- [ ] **Step 2: 실패 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports/test_report_parameters.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hyc_domain.reports'`

- [ ] **Step 3: 구현**

```python
from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from uuid import UUID

from hyc_domain.errors import CodedDomainError, FailureCode


class UnsupportedReportKind(CodedDomainError):
    """Raised when a report kind or its parameter set is not supported."""

    code = FailureCode.INVALID_SNAPSHOT


class ReportKind(StrEnum):
    INTEGRATED_INSPECTION = "INTEGRATED_INSPECTION"


_REQUIRED: dict[ReportKind, frozenset[str]] = {
    ReportKind.INTEGRATED_INSPECTION: frozenset({"inspection_case_id"}),
}
_OPTIONAL: dict[ReportKind, dict[str, Any]] = {
    ReportKind.INTEGRATED_INSPECTION: {"include_audit": False},
}


def canonical_report_parameters(kind: ReportKind, raw: Mapping[str, Any]) -> dict[str, Any]:
    required = _REQUIRED[kind]
    optional = _OPTIONAL[kind]
    unknown = set(raw) - required - set(optional)
    if unknown:
        raise UnsupportedReportKind(
            "unsupported report parameters: " + ",".join(sorted(unknown))
        )
    missing = required - set(raw)
    if missing:
        raise UnsupportedReportKind(
            "missing report parameters: " + ",".join(sorted(missing))
        )
    canonical: dict[str, Any] = {}
    for key in sorted(required):
        try:
            canonical[key] = str(UUID(str(raw[key])))
        except ValueError as error:
            raise UnsupportedReportKind(f"{key} is not a UUID") from error
    for key in sorted(optional):
        canonical[key] = bool(raw.get(key, optional[key]))
    return dict(sorted(canonical.items()))
```

`FailureCode.INVALID_SNAPSHOT`이 의미상 맞지 않으면 `hyc_domain/errors.py`의 기존 열거를 확인해 더 맞는 코드를 쓰거나 하나 추가한다. **임의로 새 실패 코드 체계를 만들지 않는다.**

- [ ] **Step 4: 통과 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports/test_report_parameters.py
```

Expected: 5 passed.

---

## Task 4: 보고서 입력 수집 — 스냅샷과 조회의 분리

설계 결정 D4를 **타입으로** 강제한다. 두 함수가 서로 다른 dataclass를 반환하므로, 판정 셀에 조회값을 넣으려면 명백히 틀린 코드를 써야 한다.

**Files:**
- Create: `backend/src/hyc_api/reports/sources.py`
- Test: `backend/tests/integration/api/test_report_source_separation.py`

**Interfaces:**
- Consumes: `hyc_data.models.DecisionSnapshotRow`, `InspectionCase`, `Nonconformance`, `Document`
- Produces:
  - `@dataclass(frozen=True) class FrozenDecisionSource` — 필드 `payload: dict[str, Any]`, `content_hash: str`
  - `@dataclass(frozen=True) class LookedUpReferenceSource` — 필드 `material_name`, `supplier_name`, `model_name`, `documents: list[tuple[str, str]]`, `nonconformances: list[dict[str, str]]`, `attachments: list[str]`, `observed_at: datetime`
  - `load_frozen_decision(session: Session, case_id: UUID) -> FrozenDecisionSource`
  - `load_reference_information(session: Session, case_id: UUID) -> LookedUpReferenceSource`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from __future__ import annotations

from hyc_api.reports.sources import load_frozen_decision, load_reference_information


def test_frozen_decision_is_read_only_from_the_snapshot(api_client, approved_case) -> None:
    before = load_frozen_decision(approved_case.session, approved_case.case_id)
    approved_case.rename_material("변경된 품목명")
    after = load_frozen_decision(approved_case.session, approved_case.case_id)
    assert after.content_hash == before.content_hash
    assert after.payload == before.payload


def test_reference_information_reflects_the_current_database(api_client, approved_case) -> None:
    # The positive control for the test above: if lookups were also frozen,
    # the immutability assertion would pass for the wrong reason.
    before = load_reference_information(approved_case.session, approved_case.case_id)
    approved_case.rename_material("변경된 품목명")
    after = load_reference_information(approved_case.session, approved_case.case_id)
    assert before.material_name != after.material_name
    assert after.material_name == "변경된 품목명"


def test_nonconformance_created_after_approval_appears_in_lookups(api_client, approved_case) -> None:
    assert load_reference_information(approved_case.session, approved_case.case_id).nonconformances == []
    approved_case.raise_nonconformance(title="입도 미달")
    found = load_reference_information(approved_case.session, approved_case.case_id).nonconformances
    assert [item["title"] for item in found] == ["입도 미달"]


def test_missing_snapshot_fails_closed(api_client, unapproved_case) -> None:
    import pytest

    from hyc_api.reports.sources import ReportSourceUnavailable

    with pytest.raises(ReportSourceUnavailable):
        load_frozen_decision(unapproved_case.session, unapproved_case.case_id)
```

`approved_case` / `unapproved_case` fixture는 이 디렉터리의 기존 P3 fixture를 재사용하거나 확장한다. **먼저 `backend/tests/integration/api/conftest.py`를 읽고 기존 승인 케이스 시딩 헬퍼를 찾아 재사용한다.** 없으면 그때 추가한다.

- [ ] **Step 2: 실패 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/integration/api/test_report_source_separation.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hyc_api.reports.sources'`

- [ ] **Step 3: 구현**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_data.models import DecisionSnapshotRow


class ReportSourceUnavailable(Exception):
    """Raised when a report input does not exist; reporting must fail closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FrozenDecisionSource:
    """Values fixed at approval time. Never reconciled against current rows."""

    payload: dict[str, Any]
    content_hash: str


@dataclass(frozen=True, slots=True)
class LookedUpReferenceSource:
    """Values read at report time. May differ between two renders."""

    material_name: str
    supplier_name: str
    model_name: str
    documents: list[tuple[str, str]]
    nonconformances: list[dict[str, str]]
    attachments: list[str]
    observed_at: datetime


def load_frozen_decision(session: Session, case_id: UUID) -> FrozenDecisionSource:
    row = session.scalar(
        select(DecisionSnapshotRow).where(DecisionSnapshotRow.inspection_case_id == case_id)
    )
    if row is None:
        raise ReportSourceUnavailable("APPROVAL_SNAPSHOT_MISSING")
    return FrozenDecisionSource(payload=dict(row.payload), content_hash=row.content_hash)


def load_reference_information(session: Session, case_id: UUID) -> LookedUpReferenceSource:
    ...
```

`load_reference_information` 본문은 `InspectionCase`에서 allocation/lot을 거쳐 `materials`/`suppliers`/`material_models`로 조인하고, `nonconformances`와 첨부 링크를 읽는다. **정확한 관계는 `backend/src/hyc_data/models.py`에서 직접 확인해 작성한다** — 이 계획이 조인 경로를 추측해 적으면 틀린 경로가 그대로 구현된다. `observed_at`은 `datetime.now(UTC)`로 채운다.

- [ ] **Step 4: 통과 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/integration/api/test_report_source_separation.py
```

Expected: 4 passed.

---

## Task 5: 통합 검사보고서 생성기

**Files:**
- Create: `backend/src/hyc_api/reports/integrated.py`
- Test: `backend/tests/unit/reports/test_integrated_report.py`

**Interfaces:**
- Consumes: Task 1 `SheetSpec`/`render_workbook`, Task 4 `FrozenDecisionSource`/`LookedUpReferenceSource`
- Produces: `render_integrated_inspection_report(frozen: FrozenDecisionSource, reference: LookedUpReferenceSource, *, include_audit: bool) -> bytes`

**시트 구성 (PRD §16.2 13개 항목 전부)**

|시트|내용|출처|
|---|---|---|
|`요약`|입고/LOT, 품목·공급사·모델, 기준 버전, 최종 판정, 승인자|혼합 — 행마다 출처 라벨|
|`공급사결과`|공급사 항목·규격·결과, HYC 기준 대비 참고 판정|스냅샷|
|`자체검사`|항목·샘플·계산값·판정|스냅샷|
|`판정근거`|최종 유효값, 판정 근거, 누락 항목 처리|스냅샷|
|`부적합`|부적합·특채 목록|조회|
|`문서`|원본 COA 정보와 해시, 첨부 목록|해시는 스냅샷, 파일명·첨부는 조회|
|`감사`|`include_audit=True`일 때만|조회|

**출처 라벨 규약:** 각 시트 1행은 반드시 `["출처", "<라벨>"]`이다. 라벨은 `승인 시점 고정 (snapshot <앞12자리>)` 또는 `조회 시점 <ISO8601 UTC>`. 혼합 시트는 데이터 행마다 마지막 열에 라벨을 붙인다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from __future__ import annotations

import io
from datetime import UTC, datetime

from openpyxl import load_workbook

from hyc_api.reports.deterministic import workbook_digest
from hyc_api.reports.integrated import render_integrated_inspection_report
from hyc_api.reports.sources import FrozenDecisionSource, LookedUpReferenceSource

_FROZEN = FrozenDecisionSource(
    payload={
        "overall_decision": "ACCEPTED",
        "spec_version": {"semantic_version": "1.2.0", "status": "ACTIVE"},
        "spec_items": [],
        "supplier_results": [],
        "internal_results": [],
        "item_decisions": [],
        "missing_policy": [],
        "sample_policy": [],
        "decision_reasons": {"final": "ACCEPTED", "reason": "ENGINE_MATCH"},
        "document_hashes": ["a" * 64],
        "approver": {"actor_id": "1", "role": "LEAD"},
        "lot_reference": {"lot_id": "lot-1"},
        "allocation_reference": {"allocation_id": "alloc-1"},
    },
    content_hash="b" * 64,
)


def _reference(material: str = "염화칼슘") -> LookedUpReferenceSource:
    return LookedUpReferenceSource(
        material_name=material,
        supplier_name="세계로비드",
        model_name="비드",
        documents=[("coa.pdf", "a" * 64)],
        nonconformances=[],
        attachments=[],
        observed_at=datetime(2026, 8, 11, 3, 0, tzinfo=UTC),
    )


def _sheets(payload: bytes) -> dict[str, list[list[object]]]:
    workbook = load_workbook(io.BytesIO(payload))
    return {
        name: [list(row) for row in workbook[name].iter_rows(values_only=True)]
        for name in workbook.sheetnames
    }


def test_every_prd_sheet_is_present() -> None:
    sheets = _sheets(render_integrated_inspection_report(_FROZEN, _reference(), include_audit=False))
    assert list(sheets) == ["요약", "공급사결과", "자체검사", "판정근거", "부적합", "문서"]


def test_audit_sheet_appears_only_when_requested() -> None:
    with_audit = _sheets(
        render_integrated_inspection_report(_FROZEN, _reference(), include_audit=True)
    )
    assert "감사" in with_audit


def test_snapshot_sheets_carry_the_frozen_provenance_label() -> None:
    sheets = _sheets(render_integrated_inspection_report(_FROZEN, _reference(), include_audit=False))
    assert sheets["판정근거"][0] == ["출처", "승인 시점 고정 (snapshot bbbbbbbbbbbb)"]


def test_lookup_sheets_carry_the_observed_at_label() -> None:
    sheets = _sheets(render_integrated_inspection_report(_FROZEN, _reference(), include_audit=False))
    assert sheets["부적합"][0] == ["출처", "조회 시점 2026-08-11T03:00:00Z"]


def test_changing_a_lookup_does_not_change_snapshot_sheets() -> None:
    original = _sheets(
        render_integrated_inspection_report(_FROZEN, _reference(), include_audit=False)
    )
    renamed = _sheets(
        render_integrated_inspection_report(_FROZEN, _reference("다른 품목"), include_audit=False)
    )
    assert renamed["판정근거"] == original["판정근거"]
    assert renamed["공급사결과"] == original["공급사결과"]
    assert renamed["요약"] != original["요약"]


def test_identical_inputs_render_an_identical_digest() -> None:
    first = render_integrated_inspection_report(_FROZEN, _reference(), include_audit=False)
    second = render_integrated_inspection_report(_FROZEN, _reference(), include_audit=False)
    assert workbook_digest(first) == workbook_digest(second)
```

- [ ] **Step 2: 실패 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports/test_integrated_report.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hyc_api.reports.integrated'`

- [ ] **Step 3: 구현**

`integrated.py`는 `SheetSpec` 목록을 만들어 `render_workbook`에 넘긴다. 라벨 헬퍼를 먼저 둔다.

```python
def _frozen_label(frozen: FrozenDecisionSource) -> str:
    return f"승인 시점 고정 (snapshot {frozen.content_hash[:12]})"


def _lookup_label(reference: LookedUpReferenceSource) -> str:
    stamp = reference.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"조회 시점 {stamp}"
```

각 시트 빌더는 `list[list[str]]`을 반환하고 첫 행이 `["출처", label]`이다. **모든 셀 값은 문자열로 변환해서 넣는다** — `SheetSpec` 계약이 그렇고, Decimal 포맷을 openpyxl에 맡기면 재현성이 깨진다.

- [ ] **Step 4: 통과 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports/test_integrated_report.py
```

Expected: 6 passed.

---

## Task 6: Job 수명주기와 ReportRunner 포트

**Files:**
- Create: `backend/src/hyc_api/services/reports.py`
- Modify: `backend/src/hyc_api/config.py`
- Modify: `.env.example`
- Test: `backend/tests/integration/api/test_report_job_lifecycle.py`

**Interfaces:**
- Consumes: Task 3 `ReportKind`/`canonical_report_parameters`, Task 4 로더, Task 5 렌더러, `hyc_api.storage.HashAddressedStorage`
- Produces:
  - `class ReportRunner(Protocol)` — `def run(self, session: Session, job: ReportJob) -> ReportArtifact: ...`
  - `class InProcessReportRunner` — `ReportRunner` 구현체
  - `create_report_job(session, *, kind, parameters, principal, idempotency_key, runner) -> dict[str, Any]`
  - `load_report_job(session, job_id) -> ReportJob`

**설계 요지**

- 산출물 저장은 **`documents`와 다른 저장소 루트**를 쓴다 (`p6_report_storage_root`). ARCH-003 §17.3의 원본/파생 물리 분리다. 클래스는 `HashAddressedStorage`를 그대로 재사용한다.
- 상태 전이는 job 행 `with_for_update()` 잠금 아래에서만 한다. 같은 job을 두 요청이 동시에 실행하지 못한다.
- 실패 시 `state='FAILED'` + `failure_code`를 남기고 **HTTP는 202로 이미 응답했으므로** 상태 폴링으로 드러난다.

- [ ] **Step 1: config에 저장소 루트 추가**

`backend/src/hyc_api/config.py`의 `Settings`에 `p3_storage_root`와 같은 형태로 추가한다.

```python
    p6_report_storage_root: str = "./.local-report-artifacts"
```

`.env.example`에도 같은 키를 주석과 함께 추가한다.

- [ ] **Step 2: 실패하는 테스트 작성**

```python
from __future__ import annotations

import pytest

from hyc_api.services.reports import create_report_job, load_report_job
from hyc_domain.reports import ReportKind


def test_successful_run_produces_one_immutable_artifact(api_client, approved_case, runner) -> None:
    body = create_report_job(
        approved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(approved_case.case_id)},
        principal=approved_case.lead,
        idempotency_key="key-1",
        runner=runner,
    )
    job = load_report_job(approved_case.session, body["job_id"])
    assert job.state == "SUCCEEDED"
    assert job.failure_code is None


def test_same_key_and_payload_replays_byte_identically(api_client, approved_case, runner) -> None:
    first = create_report_job(
        approved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(approved_case.case_id)},
        principal=approved_case.lead,
        idempotency_key="key-2",
        runner=runner,
    )
    second = create_report_job(
        approved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(approved_case.case_id)},
        principal=approved_case.lead,
        idempotency_key="key-2",
        runner=runner,
    )
    assert first == second


def test_same_key_with_a_different_payload_conflicts(api_client, approved_case, other_case, runner) -> None:
    create_report_job(
        approved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(approved_case.case_id)},
        principal=approved_case.lead,
        idempotency_key="key-3",
        runner=runner,
    )
    with pytest.raises(Exception) as caught:
        create_report_job(
            approved_case.session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(other_case.case_id)},
            principal=approved_case.lead,
            idempotency_key="key-3",
            runner=runner,
        )
    assert getattr(caught.value, "status_code", None) == 409


def test_regenerating_the_same_case_creates_a_new_job_not_an_overwrite(
    api_client, approved_case, runner
) -> None:
    # PRD 16.2: a correction produces a new version, never a rewritten one.
    first = create_report_job(
        approved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(approved_case.case_id)},
        principal=approved_case.lead,
        idempotency_key="key-4a",
        runner=runner,
    )
    second = create_report_job(
        approved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(approved_case.case_id)},
        principal=approved_case.lead,
        idempotency_key="key-4b",
        runner=runner,
    )
    assert first["job_id"] != second["job_id"]


def test_unapproved_case_fails_closed_with_a_failure_code(api_client, unapproved_case, runner) -> None:
    body = create_report_job(
        unapproved_case.session,
        kind=ReportKind.INTEGRATED_INSPECTION,
        parameters={"inspection_case_id": str(unapproved_case.case_id)},
        principal=unapproved_case.lead,
        idempotency_key="key-5",
        runner=runner,
    )
    job = load_report_job(unapproved_case.session, body["job_id"])
    assert job.state == "FAILED"
    assert job.failure_code == "APPROVAL_SNAPSHOT_MISSING"
```

- [ ] **Step 3: 실패 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/integration/api/test_report_job_lifecycle.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hyc_api.services.reports'`

- [ ] **Step 4: 구현**

Idempotency는 **새로 만들지 않는다.** `hyc_api.services.p3`의 `require_idempotency_key`, `reserve_idempotency`, `complete_idempotency`를 그대로 import해 scope `"p6.reports"`로 쓴다.

```python
class ReportRunner(Protocol):
    def run(self, session: Session, job: ReportJob) -> ReportArtifact: ...
```

`create_report_job` 골격:

```python
def create_report_job(
    session: Session,
    *,
    kind: ReportKind,
    parameters: Mapping[str, Any],
    principal: Principal,
    idempotency_key: str,
    runner: ReportRunner,
) -> dict[str, Any]:
    canonical = canonical_report_parameters(kind, parameters)
    payload = {"kind": kind.value, "parameters": canonical}
    record, replay = reserve_idempotency(
        session, principal=principal, scope="p6.reports", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return replay
    job = ReportJob(
        kind=kind.value,
        parameters=canonical,
        state="QUEUED",
        requested_by_id=principal.actor_id,
        actor_role=principal.role,
    )
    session.add(job)
    session.flush()
    body = _execute(session, job=job, runner=runner)
    complete_idempotency(
        record, status=202, body=body, resource_ref=f"report_jobs/{job.id}"
    )
    return body
```

`_execute`는 job을 `with_for_update()`로 다시 읽어 `RUNNING`으로 올리고, `runner.run`을 호출하고, 성공하면 `SUCCEEDED`, `ReportSourceUnavailable`이면 `FAILED` + `error.code`를 기록한다. **예상치 못한 예외는 삼키지 않고 그대로 전파한다** — 인프라 장애를 업무 실패로 위장하지 않기 위해서다.

`InProcessReportRunner.run`은 Task 4 로더 → Task 5 렌더러 → `HashAddressedStorage(settings.p6_report_storage_root)`에 저장 → `ReportArtifact` 삽입 순서다.

- [ ] **Step 5: 통과 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/integration/api/test_report_job_lifecycle.py
```

Expected: 5 passed.

---

## Task 7: HTTP 표면

**Files:**
- Create: `backend/src/hyc_api/routes/reports.py`
- Modify: `backend/src/hyc_api/contracts.py`
- Modify: `backend/src/hyc_api/main.py`
- Test: `backend/tests/integration/api/test_report_api.py`

**Interfaces:**
- Consumes: Task 6 서비스 함수
- Produces:
  - `POST /api/v1/reports` → 202, `{"job_id": str, "state": str}`
  - `GET /api/v1/reports/{job_id}` → 200, `{"job_id", "kind", "state", "failure_code", "artifact_digest"}`
  - `GET /api/v1/reports/{job_id}/download` → 200 xlsx 스트림, 또는 409 (미완료), 404 (없음)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from __future__ import annotations


def test_create_returns_202_with_a_job_id(api_client, approved_case) -> None:
    response = api_client.post(
        "/api/v1/reports",
        headers={**approved_case.lead_headers, "Idempotency-Key": "http-1"},
        json={
            "kind": "INTEGRATED_INSPECTION",
            "parameters": {"inspection_case_id": str(approved_case.case_id)},
        },
    )
    assert response.status_code == 202
    assert response.json()["job_id"]


def test_missing_idempotency_key_is_422(api_client, approved_case) -> None:
    response = api_client.post(
        "/api/v1/reports",
        headers=approved_case.lead_headers,
        json={
            "kind": "INTEGRATED_INSPECTION",
            "parameters": {"inspection_case_id": str(approved_case.case_id)},
        },
    )
    assert response.status_code == 422


def test_download_before_completion_is_409(api_client, approved_case, blocked_runner) -> None:
    job_id = blocked_runner.enqueue(approved_case.case_id)
    response = api_client.get(
        f"/api/v1/reports/{job_id}/download", headers=approved_case.lead_headers
    )
    assert response.status_code == 409


def test_download_streams_the_artifact_and_writes_one_audit_row(api_client, approved_case) -> None:
    created = api_client.post(
        "/api/v1/reports",
        headers={**approved_case.lead_headers, "Idempotency-Key": "http-2"},
        json={
            "kind": "INTEGRATED_INSPECTION",
            "parameters": {"inspection_case_id": str(approved_case.case_id)},
        },
    ).json()
    before = approved_case.count_audit_logs(action="REPORT_DOWNLOADED")
    response = api_client.get(
        f"/api/v1/reports/{created['job_id']}/download", headers=approved_case.lead_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content[:2] == b"PK"
    assert approved_case.count_audit_logs(action="REPORT_DOWNLOADED") == before + 1


def test_unknown_job_is_404(api_client, approved_case) -> None:
    response = api_client.get(
        "/api/v1/reports/00000000-0000-4000-8000-000000000000",
        headers=approved_case.lead_headers,
    )
    assert response.status_code == 404


def test_inspector_may_generate_and_download(api_client, approved_case) -> None:
    # Reports are read-only output, so they are not LEAD-gated. AP-04 governs
    # approval authority, not report access.
    response = api_client.post(
        "/api/v1/reports",
        headers={**approved_case.inspector_headers, "Idempotency-Key": "http-3"},
        json={
            "kind": "INTEGRATED_INSPECTION",
            "parameters": {"inspection_case_id": str(approved_case.case_id)},
        },
    )
    assert response.status_code == 202
```

- [ ] **Step 2: 실패 확인**

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/integration/api/test_report_api.py
```

Expected: FAIL — 404 on every route.

- [ ] **Step 3: 구현**

`routes/reports.py`는 `routes/nonconformances.py`의 구조를 따른다. `_commit` 헬퍼와 `_is_domain_invariant_violation`을 그대로 복제하지 말고 **공용 위치로 올려 재사용**한다. 두 번째 사용처가 생겼으므로 지금이 옮길 시점이다. `hyc_api/db_errors.py`를 만들고 두 라우트가 모두 import한다.

다운로드 감사 기록:

```python
    session.add(
        AuditLog(
            entity_type="report_job",
            entity_id=job.id,
            action="REPORT_DOWNLOADED",
            payload={
                "actor_id": str(principal.actor_id),
                "role": principal.role,
                "content_digest": artifact.content_digest,
            },
        )
    )
```

`AuditLog`에는 actor 컬럼이 없다. actor는 `payload`에 넣는다 — 기존 감사 행들과 같은 방식인지 `models.py`와 인접 사용처를 확인하고 맞춘다.

- [ ] **Step 4: 라우터 등록과 통과 확인**

`main.py`에 `app.include_router(reports.router)`를 추가한 뒤:

```
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.uv-cache}" uv run --project backend pytest -q backend/tests/integration/api/test_report_api.py
```

Expected: 6 passed.

- [ ] **Step 5: OpenAPI와 클라이언트 재생성**

```
make contracts
make contracts-check
```

Expected: `contracts/openapi.json`과 `frontend/src/lib/api/generated.ts`가 함께 갱신되고 drift 검사 통과. **둘 중 하나만 갱신하면 여기서 실패한다.**

---

## Task 8: 프론트엔드 보고서 패널

**Files:**
- Create: `frontend/src/components/reports/ReportPanel.tsx`
- Test: `frontend/tests/report-panel.test.tsx`

**Interfaces:**
- Consumes: Task 7 HTTP 표면, 기존 `canUseBackend` 가드

- [ ] **Step 1: 실패하는 테스트 작성**

```tsx
// @vitest-environment happy-dom
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportPanel } from "@/components/reports/ReportPanel";

describe("ReportPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("public demo issues zero fetches", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    render(<ReportPanel publicDemo caseId="case-1" />);
    const button = await screen.findByRole("button", { name: /보고서 생성/ });
    expect(button).not.toBeNull();
    button.click();
    await waitFor(() => expect(screen.getByText(/공개 합성 데모/)).not.toBeNull());
    expect(spy).not.toHaveBeenCalled();
  });

  it("local mode does fetch — the positive control", async () => {
    // Without this the zero-fetch assertion above would also pass if the
    // component silently failed to mount.
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ job_id: "j1", state: "SUCCEEDED" }), { status: 202 }),
    );
    render(<ReportPanel publicDemo={false} caseId="case-1" />);
    const button = await screen.findByRole("button", { name: /보고서 생성/ });
    button.click();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toContain("/api/v1/reports");
  });

  it("shows a readable message when the job fails", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "j1", state: "QUEUED" }), { status: 202 }),
      )
      .mockResolvedValue(
        new Response(
          JSON.stringify({ job_id: "j1", state: "FAILED", failure_code: "APPROVAL_SNAPSHOT_MISSING" }),
          { status: 200 },
        ),
      );
    render(<ReportPanel publicDemo={false} caseId="case-1" />);
    (await screen.findByRole("button", { name: /보고서 생성/ })).click();
    await waitFor(() =>
      expect(screen.getByText(/승인 스냅샷이 없어 보고서를 만들 수 없습니다/)).not.toBeNull(),
    );
  });
});
```

- [ ] **Step 2: 실패 확인**

```
cd frontend && pnpm vitest run tests/report-panel.test.tsx
```

Expected: FAIL — 모듈 없음.

- [ ] **Step 3: 구현**

`publicDemo`가 true면 fetch를 하지 않고 "공개 합성 데모 · 서버 연결 없음" 안내만 렌더한다. false면 POST → 상태 폴링 → 완료 시 다운로드 링크를 보인다. `failure_code`는 사용자가 읽을 수 있는 한국어 문구로 매핑하되, **매핑에 없는 코드는 코드 자체를 그대로 노출한다** — 조용히 "알 수 없는 오류"로 뭉개면 운영 중 원인 파악이 불가능해진다.

- [ ] **Step 4: 통과 확인**

```
cd frontend && pnpm vitest run tests/report-panel.test.tsx
```

Expected: 3 passed.

---

## Task 9: 게이트 등록과 전체 검증

**Files:**
- Modify: `Makefile`
- Modify: `docs/KANBAN.md`, `docs/TRACEABILITY_MATRIX.md`, `docs/DEVLOG.md`

- [ ] **Step 1: Makefile 타깃 추가**

`p4-golden-check` 인근에 추가한다.

```make
p6-report-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports backend/tests/integration/api/test_report_api.py backend/tests/integration/api/test_report_job_lifecycle.py backend/tests/integration/api/test_report_source_separation.py
```

- [ ] **Step 2: 전체 게이트 실행**

```
make check
make p6-report-check
make p2-postgres-check
COMPOSE_BAKE=false make p3-postgres-check
make p4-golden-check
make p4-preflight-check
```

Expected: 전부 exit 0. 기준선 대비 예상 변화 — 백엔드 pytest 705 → 증가, mypy 77 → 증가, frontend Vitest 61 → 64, P3 PostgreSQL 125 → 128. **P4 golden 199와 preflight 97은 변하지 않아야 한다.** 변했다면 이 증분이 P4 경계를 침범한 것이므로 멈추고 원인을 찾는다.

- [ ] **Step 3: Docker 잔여 확인**

```
docker ps -aq --filter label=com.docker.compose.project | wc -l
docker network ls -q --filter label=com.docker.compose.project | wc -l
docker volume ls -q --filter label=com.docker.compose.project | wc -l
```

Expected: 0 / 0 / 0.

- [ ] **Step 4: 문서 동기화**

KANBAN에 `P6-1-report-foundation` 카드를 추가하고 실제 측정 수치를 적는다. 매트릭스의 REP-002, API-002, API-003 행 근거를 신규 테스트 경로로 갱신한다. **수치는 실제 실행 출력에서 옮겨 적고 이 계획의 예상값을 베끼지 않는다.**

---

## Self-Review 결과

**스펙 커버리지.** 범위 계획서 §5 P6-1의 "만드는 것" 항목 대조: 마이그레이션 2테이블(Task 2) · 3개 라우트(Task 7) · `ReportRunner` 포트(Task 6) · 통합보고서 생성기(Task 5) · 출처 이원화(Task 4·5) · 정정 버전 새 job(Task 6 네 번째 테스트) · 프론트 `canUseBackend` 가드(Task 8) · openpyxl 의존성(Task 1) · `p6-report-check`(Task 9). **모두 대응 태스크가 있다.**

**미해결로 남긴 것 두 가지.**

1. **Task 4의 조인 경로와 Task 6의 fixture 이름을 계획이 확정하지 않았다.** 각 태스크에 "모델/conftest를 직접 읽고 맞추라"고 명시했다. 계획이 관계를 추측해 적으면 틀린 경로가 그대로 구현되므로, 여기서는 추측을 코드로 위장하지 않는 쪽을 택했다.
2. **`FailureCode.INVALID_SNAPSHOT` 재사용이 의미상 맞는지 확인이 필요하다.** Task 3 Step 3에 확인 지시와 "새 실패 코드 체계를 만들지 말 것"을 함께 적었다.

**타입 일관성.** `SheetSpec`/`render_workbook`/`workbook_digest`(T1) → `render_integrated_inspection_report`(T5) → `InProcessReportRunner`(T6), `FrozenDecisionSource`/`LookedUpReferenceSource`/`ReportSourceUnavailable`(T4) → T5·T6, `ReportKind`/`canonical_report_parameters`(T3) → T6·T7, `ReportJob`/`ReportArtifact`(T2) → T6. 태스크 간 이름과 시그니처가 일치한다.

**의도적으로 넣지 않은 것.** 산출물 삭제/만료, Redis 큐·DLQ·자동 재시도, Raw Data 호환 시트, OCR KPI 임계값, 보고서의 판정값 쓰기 경로.
