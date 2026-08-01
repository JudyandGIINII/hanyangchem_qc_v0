# P4 OCR Golden / Provider benchmark kickoff plan

**작성일:** 2026-08-02
**정본:** [`../../Prd.md`](../../Prd.md)
**상위 delivery contract:** [`2026-07-30-integrated-implementation-plan.md`](2026-07-30-integrated-implementation-plan.md)
**추적표:** [`../TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md)
**상태:** P4 preparation ready; P4 implementation unstarted

## 1. 목적과 현재 사실

이 문서는 다음 세션이 P4의 안전한 offline/synthetic 기반만 시작하도록 범위, 계약, 검증 및 승인 경계를 고정한다. P3 source commit `91465f0413d0c0ca2633577078ec1300a6096442`는 accepted, fresh-main fast-forward integrated, `origin/main` delivered 상태다. 이 문서를 작성한 격리 worktree의 capture-time baseline은 `f3020e2fe90996de9b5b0e502da4360976db0a9f`이지만, 이는 새 문서 commit 전의 관측 기준일 뿐 continuing live tip이나 최종 commit이 아니다. Git history가 이후 live tip의 정본이다.

이 preparation increment에는 P4 application code가 없다. `make p4-golden-check`와 `make p4-benchmark-fixture`도 아직 존재하지 않으며 아래 첫 구현 slice의 planned output이다. 실제 대표 코퍼스 승인 증거와 Provider별 AP-02 opt-in도 없다. 따라서 시작 가능한 것은 P4-A뿐이다.

이 문서는 기존 P3 acceptance/test evidence를 변경하거나 P3의 historical handoff를 무효화하지 않는다. 사용자의 현재 요청은 Hermes/controller가 이 여섯 문서를 QA한 뒤 일반 commit과 non-force push로 전달하는 것을 승인했다. 문서 작성 agent에게는 Git mutation 권한이 없으며, 추가 사용자 승인을 기다리는 gate 없이 writer/controller 역할 분리만 유지한다.

## 2. 세 개의 독립 lane과 gate

|Lane|현재 상태|허용 범위|해제 조건|
|---|---|---|---|
|P4-A — Offline/Synthetic foundation|`READY_TO_START_IN_NEW_SESSION`|생성된 비민감 synthetic fixture, 기존 fixture-provider seam, 결정론적 golden/schema/scorer/runner, staged artifact contract|추가 product gate 불필요. 새 세션에서 fresh `origin/main` 기준과 clean isolated Orca worktree를 먼저 확인|
|P4-B — Approved corpus benchmark|`BLOCKED_QUALITY_CORPUS_APPROVAL`|승인된 로컬 코퍼스에 동일 runner 적용|QUALITY가 문서 유형/공급사/난이도 대표성과 비식별 정책을 증거로 승인하고 decision packet의 모든 필수 필드가 채워짐|
|P4-C — External Provider benchmark/selection|`BLOCKED_AP02_PROVIDER_OPT_IN`|특정 Provider/model/endpoint에 대한 재현 가능한 benchmark와 선택|해당 Provider에 한정된 AP-02 opt-in 및 승인된 코퍼스 destination. Generic approval은 다른 Provider를 열지 않음|

P4-B와 P4-C는 서로 독립적으로 blocked다. 코퍼스 승인은 외부 전송 승인이 아니며, Provider opt-in은 코퍼스 대표성 승인도 아니다. 실제 Provider 선정은 두 gate가 모두 해당 실행에 대해 충족되고 재현 가능한 benchmark와 Human Review fallback이 증명된 뒤에만 가능하다.

## 3. 공통 안전 불변식

- OCR/LLM 출력은 candidate뿐이며 사람이 최종값을 검토한다. AI가 검사 결과를 최종 확정하거나 승인하지 않는다.
- 공급사 규격/결과, HYC 규격/결과, 최종 업무 결정을 분리한다.
- 수치 비교와 golden expected value는 `Decimal`/canonical decimal string을 사용하며 binary float로 품질 결정을 하지 않는다.
- 필수 누락, unmapped, low-confidence, 논리 검증 실패, 필요한 자체검사 미완료는 fail closed로 Human Review 또는 manual fallback에 남긴다.
- 손글씨는 reference-only다. 핵심 매칭이나 최종 판정의 business field로 자동 승격하지 않는다.
- CI는 fixture provider만 사용하고 network와 외부 credential을 사용하지 않는다. 실제 PDF/XLS/XLSX body, source document, credential, Provider payload는 Git, mirror, prompt, transcript 또는 외부 시스템에 넣지 않는다.
- 원본과 파생 artifact는 분리하고 input hash와 모든 version binding을 보존한다.

## 4. P4-A 아키텍처와 의존 방향

### 4.1 구현 전 필수 계약 점검

다음 세션은 변경 전에 반드시 아래 기존 파일을 읽고 contract/client 영향 범위를 정한다.

- [`../../backend/src/hyc_api/extraction.py`](../../backend/src/hyc_api/extraction.py)
- [`../../backend/src/hyc_api/contracts.py`](../../backend/src/hyc_api/contracts.py)
- [`../../backend/tests/contract/test_extraction_contract.py`](../../backend/tests/contract/test_extraction_contract.py)

현재 `ExtractionCandidate.provider_name`은 `Literal["synthetic-fixture"]`인 synthetic-only 계약이다. Provider identity, model, endpoint 또는 version을 표현하려면 이 literal을 무심코 넓히지 말고 backward-compatible schema evolution을 설계해야 한다. 기존 synthetic payload의 round trip, required/extra-field 거부, generated JSON Schema/OpenAPI/client drift, 구/신 version 호환 및 fail-closed unknown-provider 테스트를 먼저 작성한다. P4-A는 real Provider adapter가 필요 없으므로 이 계약 변경이 첫 slice에 반드시 필요한지 먼저 증명한다.

### 4.2 권장 패키지 경계

아래는 다음 세션의 suggested ownership/path plan이며, 표시된 새 경로가 현재 존재한다고 주장하지 않는다.

```text
existing hyc_api contracts / ExtractionProvider port
                    |
                    v
planned standalone hyc_evaluation golden package
  schema -> fixture loader -> staged artifact contract -> matcher/scorer -> report digest
                    ^
                    |
          SyntheticFixtureExtractionProvider
```

- `WORKER`: planned `backend/src/hyc_evaluation/` 아래 versioned golden model, deterministic runner, staged artifact manifest, matcher/scorer, canonical report를 소유한다.
- `QUALITY`: golden identity, allowed normalization vocabulary, low-confidence taxonomy, 향후 corpus representativeness/KPI threshold를 승인한다.
- `API`: 기존 extraction contract 변경이 필요할 때만 backward compatibility와 generated contract/client drift를 소유한다.
- `DOMAIN`: pure decision engine은 Provider/evaluation package를 import하지 않는다. 평가 package는 계약을 소비할 수 있지만 pure domain이 Provider code에 의존하게 만들지 않는다.
- `HERMES-QA`: gate, 실제 실행 command, scan, network absence, deterministic digest를 독립 검증한다.

Planned new paths의 한 가지 권장 배치는 다음과 같다.

- `backend/src/hyc_evaluation/{schema.py,normalization.py,artifacts.py,matching.py,scoring.py,runner.py,report.py}`
- `backend/tests/golden/{test_schema.py,test_scoring.py,test_pipeline_regression.py,test_required_edge_cases.py,test_calcium_chloride_coa.py,test_domestic_8p_samples.py,test_handwriting_never_business_field.py}`
- `backend/tests/fixtures/p4/synthetic/` 아래 generated fixture와 versioned expected JSON
- `backend/scripts/run_p4_golden.py` 또는 동등한 얇은 CLI entrypoint
- root `Makefile`의 planned `p4-golden-check`, `p4-benchmark-fixture` targets

경로 이름은 current contracts 검토 후 조정할 수 있지만 standalone evaluator, provider-before-scorer 금지, domain 의존 역전 금지, CI external-call 금지는 바꿀 수 없다.

## 5. Versioned golden schema contract

첫 schema version은 strict/extra-forbid이며 최소한 다음을 값으로 고정한다.

|영역|필수 binding|
|---|---|
|Dataset/case|`golden_schema_version`, dataset ID/version, case ID, deterministic ordering key|
|Input|SHA-256 source hash, MIME/document kind, `synthetic: true`, generator name/version/seed, non-sensitive provenance marker|
|Page|page identity/index, rendered DPI, declared/detected rotation, width/height, coordinate system/version|
|Identity|document identity, section identity, row identity, sample identity; row/sample ordering and parent identity|
|Expected value|field/item key, required/ignored flag, raw text/value, normalized value as canonical decimal/string, unit, LOT/date/text kind|
|Geometry|page number and bbox polygon vertices in declared coordinate space; degenerate/out-of-page polygon은 schema error|
|Review|expected review flag, low-confidence reason code, handwriting reference-only marker|
|Normalization|field별 허용 normalization ID와 version; 무승인 transformation은 허용 목록 밖|
|Version binding|fixture/provider identity and version, model if applicable, parser version, prompt/schema version if applicable, pipeline/stage version, runner/scorer/report version|

Golden file 자체의 canonical JSON SHA-256, 각 input/artifact SHA-256, schema version 및 runner/scorer version을 report에 결합한다. Fixture generator는 고정 seed를 사용하고 locale/timezone/clock 영향을 제거한다. 중복 case/document/row/sample identity, unknown normalization, binary float, 빠진 version binding은 실행 전 schema validation에서 실패한다.

## 6. Staged artifact contract

Runner는 다음 stage를 순서대로 기록하되 실제 OCR 수행을 CI 요구조건으로 만들지 않는다.

1. text-layer detection
2. page render
3. rotation / deskew / contrast preprocessing
4. table detection
5. extraction (CI에서는 fixture provider output)
6. parse
7. schema validation
8. logic validation

각 stage artifact에는 stage name/version, deterministic input refs/hashes, output hash, status, structured warning/error, started ordering token과 stable clock, upstream artifact refs를 둔다. Raw bytes나 전체 OCR payload를 일반 log에 넣지 않는다. 실패 stage 뒤의 결과를 성공으로 가장하지 않고 명시적 `SKIPPED_UPSTREAM_FAILURE` 또는 fail-closed review state로 남긴다. CI fixture는 stage-shaped synthetic artifact를 생성해 contract와 lineage를 검증하며 network, real OCR binary/service 또는 external credential을 요구하지 않는다.

## 7. Deterministic metric contract

### 7.1 공통 집합과 denominator

- Schema-valid golden expected fields를 `E`, schema-valid predicted fields를 `P`로 둔다. `ignored=true` 필드는 별도 ignored count에만 포함하고 모든 정확도 denominator에서 제외한다.
- Field matching key는 versioned `(document_id, section_id, row_id, sample_id-or-null, field_key)` tuple의 exact equality다. 암묵적 fuzzy/position matching은 금지한다.
- Duplicate case/row/sample/field identity는 greedy matching하지 않고 validation error 및 review condition으로 기록한다. 해당 run은 acceptance-eligible report가 아니다.
- 모든 metric은 numerator, denominator, excluded/ignored/error count를 함께 출력한다. denominator가 0이면 값은 `null`/`NOT_APPLICABLE`이며 임의로 0 또는 1을 주지 않는다.
- 허용 normalization은 golden에 명시된 ID/version만 field별 순서대로 적용한다. 무승인 normalization은 error/review condition이며 match가 아니다.

### 7.2 Field exact와 normalized match

- `exact_field_match = exact_raw_matches / eligible_expected_fields`. Raw text/value와 type이 exact해야 한다.
- `normalized_field_match = allowed_normalized_matches / eligible_expected_fields`. Golden allow-list transformation 후 canonical type/value가 같아야 한다.
- 두 metric은 항상 별도 출력하고 normalized match로 exact mismatch를 숨기지 않는다. Expected field를 못 찾으면 두 metric 모두 mismatch이며 required이면 required-missing 평가에도 들어간다.

### 7.3 Row precision/recall

- Canonical row identity는 golden에 명시된 `(document_id, section_id, row_id)`이며 predicted row도 동일 identity contract를 가져야 한다. 한 expected row와 한 predicted row만 one-to-one exact identity로 match한다.
- `TP_rows = |E_rows ∩ P_rows|`, `FP_rows = |P_rows - E_rows|`, `FN_rows = |E_rows - P_rows|`.
- `row_precision = TP_rows / (TP_rows + FP_rows)`; `row_recall = TP_rows / (TP_rows + FN_rows)`.
- Identity가 맞아도 row field/value 오류는 field/numeric/unit/LOT metric에 별도 반영한다. Duplicate row identity는 validation error이며 TP를 늘리지 않는다.

### 7.4 분리된 품질 지표

- Numeric value: canonical decimal string을 `Decimal`로 비교한다. Exact numeric equality와 allowed numeric normalization equality를 분리하며 float coercion은 error다.
- Unit: raw unit exact와 approved unit-alias/canonical-unit match를 분리한다. 차원 변환 또는 반올림은 명시된 formula/version/normalization 없이는 match가 아니다.
- LOT: raw LOT exact와 명시된 LOT normalization match를 분리한다. 다른 입고값과 충돌하면 자동 선택하지 않고 Human Review로 보낸다.
- Required-missing detection: golden의 required-field presence/missing label과 predicted missing signal에 대해 `TP_missing`, `FP_missing`, `FN_missing`, `TN_missing`을 출력한다. `missing_recall = TP_missing / (TP_missing + FN_missing)`, `missing_precision = TP_missing / (TP_missing + FP_missing)`이며 zero-denominator 규칙을 적용한다. 누락을 빈 문자열/0으로 채워 match시키지 않는다.
- Sample value/ordering은 sample identity와 원문 순서로 평가하며 fixed-column truncation을 허용하지 않는다.

### 7.5 Page/bbox geometry

- Page match는 matched field 중 expected page number와 predicted page number exact equality의 count/rate로 보고한다.
- Bbox polygon은 같은 declared coordinate system으로 검증 후 intersection-over-union `IoU = area(E ∩ P) / area(E ∪ P)`를 field별 및 distribution으로 보고한다. Union area 0은 schema error다.
- QUALITY 승인 없이 임의의 IoU acceptance threshold를 만들지 않는다. Page mismatch, missing polygon, invalid polygon count를 별도 출력하고 geometry를 text match에 합쳐 숨기지 않는다.

### 7.6 운영성 지표와 재현성

- Latency, document/provider cost, Human correction time은 서로 다른 metric이다. P4-A CI acceptance에 포함하지 않으며 Provider와 approved corpus가 있는 non-CI benchmark에서만 측정한다. P4-A report에는 `NOT_APPLICABLE`과 사유를 남긴다.
- Latency는 stage별 monotonic duration과 end-to-end를, cost는 provider/model/currency/pricing-version 단위로, correction time은 Human Review session의 명시적 start/end와 correction count로 기록한다.
- CI runner는 injected stable clock, fixed timezone/locale/seed, canonical path-independent identifiers, sorted case/row/field output을 사용한다.
- Reproducible report digest는 canonical JSON serialization의 SHA-256이며 input hashes, golden/schema versions, fixture/provider/parser/pipeline/scorer/report versions, normalization IDs, runner configuration, metric numerator/denominator/error counts를 모두 포함한다. 동일 binding은 동일 digest를 내야 한다.

## 8. P4-A first implementation slice

1. `git fetch` 후 현재 `origin/main`의 exact commit과 P3 ancestry를 읽기 전용으로 확인하고 clean isolated Orca worktree를 만든다. Capture-time `f3020e2...`를 continuing live tip으로 가정하지 않는다.
2. 위 세 existing extraction contract 파일을 읽고 contract change 필요성을 tests-first로 판정한다.
3. Strict versioned golden schema와 synthetic provenance/hash/version validation tests를 먼저 red로 만든다.
4. Deterministic matcher/scorer와 canonical report digest tests를 real Provider adapter보다 먼저 구현한다.
5. Common fixture runner와 staged artifact contract를 추가하되 CI extraction stage는 existing fixture-provider seam만 사용한다.
6. Generated non-sensitive synthetic edge matrix를 만든다: decimals, percent, O/0, I/l, plus-minus, micro/mm symbols, merged cells, multi-LOT, stamp overlap, rotation/low-resolution, encrypted/corrupt PDF, missing required rows, variable sample counts, handwriting-as-reference-only.
7. `make p4-golden-check`와 `make p4-benchmark-fixture`를 첫 implementation output으로 추가한다. 이 handoff 시점에는 둘 다 absent/planned다.
8. P3와 repository 전체 기존 gate를 보존하고 regression을 실행한다.

## 9. P4-A planned acceptance/traceability matrix

아래는 planned verification이며 아직 `Verified`가 아니다.

|Requirement/control|P4-A planned evidence|Gate|
|---|---|---|
|AT-001|Synthetic image-like COA fixture에서 supplier/product/LOT/rows/spec/result/page/bbox, stamp-overlap low-confidence, handwriting reference-only|P4-A fixture contract; approved real corpus는 P4-B|
|AT-004|항목별 5개/3개 등 variable sample identity/value/source order 무손실, fixed-column truncation 거부|P4-A synthetic golden|
|FR-OCR-001|Staged artifacts + deterministic fixture runner; no real OCR in CI|P4-A|
|FR-OCR-002|Existing Provider port 유지, scorer-first; provider identity evolution은 backward-compatible contract/drift tests|P4-A contract gate; external use P4-C|
|FR-OCR-003|Strict structured golden/extraction schema, page/polygon/raw/normalized provenance|P4-A|
|FR-OCR-004|Handwriting reference-only test; business field 승격 금지|P4-A|
|FR-OCR-005|Confidence/reason/review-required를 score/report하고 low-confidence는 Human Review|P4-A; threshold QUALITY approval 별도|
|FR-OCR-006|날짜/숫자·단위/O↔0/I↔l/누락/중복/병합 의심을 candidate warning으로만 생성, 자동 변경 금지|P4-A|
|Human Review/fail closed|필수 누락, unapproved normalization, invalid/duplicate schema, low confidence, logic conflict는 review/manual fallback; auto-finalization 없음|항상|
|AP-02|CI network/provider call/credential absence proof; external Provider는 OFF|P4-C blocked|
|QUALITY corpus representativeness|Synthetic provenance만 명시하고 real representative claim 금지|P4-B blocked|
|Commands|focused unit/golden, planned Make targets, full P3/regression gates, scans/cleanup|실행 exit 0 뒤에만 Verified|

## 10. P4-B QUALITY decision packet — 현재 `PENDING`

아래 필드 중 하나라도 빠지면 approval이 아니다.

- Corpus manifest ID/version: `PENDING`
- 각 source의 SHA-256 및 classification: `PENDING`
- 문서 유형/공급사/난이도 representativeness matrix와 포함 근거: `PENDING`
- De-identification method, reviewer, review date, 재식별 위험: `PENDING`
- 허용 local storage 위치/접근권한/암호화: `PENDING`
- Git status 및 real body가 Git/mirror/prompt/transcript에 없다는 증거: `PENDING`
- Retention/deletion owner, 기간, 삭제 증거 방식: `PENDING`
- 허용 benchmark destination과 금지 destination: `PENDING`
- Exclusions와 한계: `PENDING`
- QUALITY approver, approval date, 승인 evidence link/ID: `PENDING`

Real PDF/XLS/XLSX body는 계속 Git, mirror, prompt, transcript, 외부 전송에서 금지된다. QUALITY 승인은 승인된 로컬 보관/benchmark 목적만 열며 AP-02를 대신하지 않는다.

## 11. P4-C Provider-specific AP-02 decision packet — 현재 `PENDING`

각 Provider별로 아래를 결정한다. 한 Provider의 승인은 다른 Provider를 자동 승인하지 않는다.

- Provider/model/version, endpoint, processing region: `PENDING`
- Payload 종류와 redacted field/document allow-list: `PENDING`
- Data retention/deletion, training use/opt-out: `PENDING`
- Subprocessors, 계약/DPA/보안 검토: `PENDING`
- Credential source, rotation, least privilege, log redaction: `PENDING`
- Cost model, currency, pricing version, budget/cap/owner: `PENDING`
- Request/audit/correlation 기록과 raw response 보존정책: `PENDING`
- Disable switch, rollback/manual fallback, incident owner: `PENDING`
- Approved corpus destination과 P4-B approval reference: `PENDING`
- AP-02 approver, provider-specific decision date/evidence: `PENDING`

선정은 exact/normalized/row/numeric/unit/LOT/missing/geometry와 latency/cost/correction-time report가 동일 runner로 재현된 후 이루어진다. KPI 미달이나 KPI 부재는 review/manual fallback 확대 사유이며 auto-finalization 또는 임계값 완화 사유가 아니다.

## 12. 다음 세션 verification sequence

실제로 실행한 명령과 exit/result만 기록한다.

1. Initial `git fetch`; exact `origin/main`, clean base, P3 ancestry, isolated worktree 확인.
2. Dependency가 없을 때만 `make bootstrap`.
3. 구현한 focused P4 unit/golden/schema/scorer/runner tests.
4. 추가 후 `make p4-golden-check`.
5. 추가 후 `make p4-benchmark-fixture`.
6. `make check`.
7. `make p2-postgres-check`.
8. `make p3-postgres-check`.
9. P4가 extraction/runtime/API/UI path를 바꾸면 `make p3-e2e`. P4-A가 evaluator-only라 생략한다면 changed-path/import/runtime 영향 분석과 omission justification을 verification evidence에 명시.
10. `git diff --check`.
11. `python3 scripts/scan_secrets.py`.
12. `python3 scripts/check_sensitive_documents.py`.
13. Tracked/untracked sensitive-document scan, network/provider-call absence proof, external credential absence proof.
14. 사용한 disposable Docker containers/networks/volumes/storage cleanup; user-owned n8n은 untouched.

## 13. Stop 및 rollback

다음에는 즉시 중단하고 controller에게 escalation한다.

- real source document/body/hash 외 민감 내용 발견 또는 사용 요구
- 외부 전송, Provider network call, credential 요청
- QUALITY corpus approval이 모호하거나 packet이 `PENDING`
- 해당 Provider의 AP-02 opt-in 부재
- 이 documentation preparation에서 허용되지 않은 non-doc change 또는 다음 implementation에서 승인 범위 밖 change
- fresh `origin/main` baseline/ancestry drift를 해석 없이 진행해야 하는 상황
- OCR candidate의 auto-finalization, Human Review 축소, fail-closed 완화 요구
- PRD와 integrated plan 충돌

Push 전 문제가 발견되면 main을 mutate하지 말고 candidate branch/worktree를 폐기한다. Push 뒤에는 correction/revert commit을 사용하며 force push/reset하지 않는다. Real artifact가 생성되었다면 승인된 retention/deletion 절차 없이는 임의 이동·전송하지 않고 즉시 접근을 제한해 escalation한다.

## 14. 다음 Hermes/Orca/Codex 세션 시작 prompt

```text
Prd.md, AGENTS.md, docs/plans/2026-07-30-integrated-implementation-plan.md,
docs/plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md,
docs/TRACEABILITY_MATRIX.md를 정본/계약으로 읽어라.

P4-A Offline/Synthetic foundation만 시작한다. 먼저 git fetch 후 현재 origin/main의 exact
commit, clean state, P3 commit 91465f0413d0c0ca2633577078ec1300a6096442 ancestry를 확인하고
isolated Orca worktree를 만들어라. f3020e2fe90996de9b5b0e502da4360976db0a9f는
2026-08-02 documentation capture-time baseline일 뿐 live tip으로 가정하지 마라.

변경 전에 backend/src/hyc_api/extraction.py, backend/src/hyc_api/contracts.py,
backend/tests/contract/test_extraction_contract.py를 읽어라. provider_name은 현재
synthetic-fixture literal이므로 real Provider identity/version을 무심코 넓히지 말고 필요한 경우
tests-first backward-compatible contract와 generated schema/OpenAPI/client drift를 설계하라.

Strict versioned synthetic golden schema, deterministic scorer/common fixture runner, staged artifact
contract를 real Provider adapter보다 먼저 구현하라. CI는 fixture provider, fixed seed/clock/order,
no network, no external credentials만 사용한다. 첫 output으로 make p4-golden-check와
make p4-benchmark-fixture를 추가하고 synthetic edge matrix와 AT-001/AT-004,
FR-OCR-001~006, Human Review/fail-closed tests를 만든다. Pure domain이 provider/evaluator에
의존하지 않게 유지하라.

P4-B는 QUALITY corpus approval이 없어 blocked이고 P4-C는 provider-specific AP-02 opt-in이 없어
blocked다. Real PDF/XLS/XLSX, external OCR/AI, credential, provider call, deployment, production
DB/migration/role, auto-finalization은 금지한다. 실제 명령과 결과만 DEVLOG/KANBAN/traceability에
기록하고 Git mutation은 별도 권한 없이는 하지 마라.
```
