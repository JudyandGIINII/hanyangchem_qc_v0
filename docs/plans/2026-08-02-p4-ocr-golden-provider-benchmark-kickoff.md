# P4 OCR Golden / Provider benchmark kickoff plan

**작성일:** 2026-08-02
**정본:** [`../../Prd.md`](../../Prd.md)
**상위 delivery contract:** [`2026-07-30-integrated-implementation-plan.md`](2026-07-30-integrated-implementation-plan.md)
**추적표:** [`../TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md)
**상태:** P4-A Offline/Synthetic complete/independently accepted/committed/fresh-main fast-forward integrated/delivered; P4-B/P4-C independently blocked

## 1. 목적과 현재 사실

이 문서는 P4 lane의 범위, 계약, 검증 및 승인 경계를 고정하고 P4-A Offline/Synthetic의 최종 acceptance/delivery evidence를 기록한다. P3 source commit `91465f0413d0c0ca2633577078ec1300a6096442`는 accepted/delivered 상태다. P4-A source/integration commit `aeedceb2c3b7008439a9c72e3984be77f6135e51` (`feat: complete P4-A offline synthetic evaluator`)은 baseline `2d5c02dbc612f9b612f27a36263b95e842c24e75`의 direct descendant이며 complete/independently accepted/committed/fresh-main fast-forward integrated/`origin/main` delivered 상태다.

Final 25-path candidate의 fresh independent read-only review는 `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 3)를 반환했다. Review 전후 recomputation에서 16-path source-only digest `0d5c259f59293f35e4cf6b83ffff13820c3c07194f5db48e54d8c8b1d09db632`와 25-path full candidate digest `ba938518beca8f3718abdf4eb44430e26b3a775aea8f8b33dc5dc01937218f23`가 모두 불변이었다. Full-candidate digest는 이 docs-only closure 전 accepted candidate의 capture-time evidence다. `make p4-golden-check`와 `make p4-benchmark-fixture`는 존재하고 검증됐다. 실제 대표 코퍼스 승인 증거와 Provider별 AP-02 opt-in은 여전히 없다.

이 문서는 기존 P3 acceptance/test evidence를 변경하거나 P3의 historical handoff를 무효화하지 않는다. Fresh Orca integration worktree는 fetched `origin/main`의 baseline `2d5c02d…`에서 생성됐다. `git merge --ff-only aeedceb…`는 merge commit/rebase 없이 성공했고 non-force `git push origin HEAD:main`도 성공했다. Post-fetch capture time에 integration HEAD, `origin/main`, `git ls-remote origin refs/heads/main`은 모두 `aeedceb…`였고 baseline/source ancestry 및 implementation/integration worktree clean state가 확인됐다. 이 nine-file documentation closure를 포함하는 commit은 `aeedceb…`의 newer descendant이고, exact SHA와 remote-tip 상태는 Git history가 정본이다. `aeedceb…`는 continuing tip이 아니라 P4-A source/integration baseline으로 남는다.

## 2. 세 개의 독립 lane과 gate

|Lane|현재 상태|허용 범위|해제 조건|
|---|---|---|---|
|P4-A — Offline/Synthetic foundation|`COMPLETE_ACCEPTED_DELIVERED_TO_ORIGIN_MAIN`|생성된 비민감 synthetic fixture, 기존 fixture-provider seam, 결정론적 golden/schema/scorer/runner, staged artifact contract|Final controller QA/review와 source delivery 완료; 범위를 real corpus/Provider/full P4로 확대하지 않음|
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

### 4.1 계약 점검 결과

P4-A 구현 전에 아래 기존 파일을 읽고 contract/client 영향 범위를 정했다.

- [`../../backend/src/hyc_api/extraction.py`](../../backend/src/hyc_api/extraction.py)
- [`../../backend/src/hyc_api/contracts.py`](../../backend/src/hyc_api/contracts.py)
- [`../../backend/tests/contract/test_extraction_contract.py`](../../backend/tests/contract/test_extraction_contract.py)

`ExtractionCandidate.provider_name`의 `Literal["synthetic-fixture"]` synthetic-only 계약과 기존 `ExtractionProvider` seam을 유지했다. P4-A는 real Provider identity/model/endpoint를 추가하지 않았고 contract/client drift gate를 통과했다. 향후 P4-C에서 identity/version을 표현하려면 이 literal을 무심코 넓히지 말고 backward-compatible schema evolution과 fail-closed unknown-provider 검증을 먼저 수행한다.

### 4.2 권장 패키지 경계

구현 결과는 다음 의존 방향을 따른다.

```text
existing hyc_api contracts / ExtractionProvider port
                    |
                    v
standalone hyc_evaluation golden package
  schema -> fixture loader -> staged artifact contract -> matcher/scorer -> report digest
                    ^
                    |
          SyntheticFixtureExtractionProvider
```

- `WORKER`: `backend/src/hyc_evaluation/` 아래 versioned golden model, deterministic runner, staged artifact manifest, matcher/scorer, canonical report를 소유한다.
- `QUALITY`: golden identity, allowed normalization vocabulary, low-confidence taxonomy, 향후 corpus representativeness/KPI threshold를 승인한다.
- `API`: 기존 extraction contract 변경이 필요할 때만 backward compatibility와 generated contract/client drift를 소유한다.
- `DOMAIN`: pure decision engine은 Provider/evaluation package를 import하지 않는다. 평가 package는 계약을 소비할 수 있지만 pure domain이 Provider code에 의존하게 만들지 않는다.
- `HERMES-QA`: gate, 실제 실행 command, scan, network absence, deterministic digest를 독립 검증한다.

실제 P4-A source paths는 다음과 같다.

- `backend/src/hyc_evaluation/{__init__.py,artifacts.py,fixture.py,normalization.py,runner.py,schema.py,scoring.py,synthetic_data.py}`
- `backend/tests/golden/{test_schema.py,test_artifacts_and_scoring.py,test_runner_stages_metrics_edges.py}`
- `backend/tests/fixtures/p4/synthetic/p4a_edge_dataset.v1.json`
- `backend/scripts/{generate_p4_synthetic_fixture.py,run_p4_golden.py}`
- root `Makefile`의 `p4-golden-check`, `p4-benchmark-fixture` targets
- 기존 `backend/tests/contract/test_extraction_contract.py` 보강

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

## 8. P4-A completed implementation slice

1. Isolated Orca worktree에서 base HEAD `2d5c02dbc612f9b612f27a36263b95e842c24e75`를 고정했다.
2. Existing extraction contracts를 검토하고 synthetic-only Provider literal/seam을 유지했다.
3. Strict/versioned golden, fixture, stage, candidate, report, benchmark-output schema와 provenance/hash/version validation을 구현했다.
4. Canonical JSON, Decimal/SHA-256 exact binding, deterministic scorer/report digest와 independent candidate payload를 real Provider adapter보다 먼저 구현했다.
5. Eight-stage common runner, fail-closed upstream propagation, stage/error compatibility와 candidate-observed canonical warning/error order를 구현했다.
6. Generated non-sensitive 20-edge matrix를 executable/disjoint disposition과 exact reason-code binding으로 구현했다. Concave, self-intersecting, degenerate, malformed geometry도 fail closed다.
7. `make p4-golden-check`와 `make p4-benchmark-fixture`를 추가하고 repeatability를 검증했다.
8. P2/P3와 repository 전체 gate를 보존하고 regression을 통과했다.

## 9. P4-A remediation verification/traceability matrix

아래 `Verified`는 generated non-sensitive offline/synthetic scope에만 적용된다. P4-B/P4-C, real OCR/Provider quality 또는 full P4를 뜻하지 않는다.

|Requirement/control|P4-A actual evidence|Gate|
|---|---|---|
|AT-001|Synthetic COA fields/rows/page/polygon과 low-confidence/reference-only evidence; report exact 35/44, page mismatch 1, non-unit IoU 1|P4-A synthetic Verified; approved real corpus는 P4-B|
|AT-004|Sample identity/value/raw/source order/cardinality exact binding; duplicate/unmapped/value-mismatch/fixed-shape loss fail closed|P4-A synthetic Verified|
|FR-OCR-001|Eight-stage deterministic runner, fail-closed upstream propagation and stage/error compatibility; no real OCR in CI|P4-A synthetic Verified|
|FR-OCR-002|Existing synthetic Provider port preserved; independent candidate payload; scorer-first; contract/client drift passed|P4-A seam Verified; external use P4-C|
|FR-OCR-003|Strict structured schemas plus exact canonical JSON/Decimal/SHA-256 dataset→output binding|P4-A synthetic Verified|
|FR-OCR-004|20-edge matrix preserves handwriting/reference-only and prevents business-field promotion|P4-A synthetic Verified|
|FR-OCR-005|Disjoint candidate/review/manual/stable-failure disposition and exact reasons; low confidence remains Human Review|P4-A synthetic Verified; threshold QUALITY approval 별도|
|FR-OCR-006|Duplicate/unmapped/unapproved-normalization/value-mismatch and warning/error order; no automatic change|P4-A synthetic Verified|
|Human Review/fail closed|Invalid/missing/unsupported/geometry/logic paths fail closed; no auto-finalization|Verified in P4-A synthetic scope|
|AP-02|CI network/provider call/credential absence proof; external Provider는 OFF|P4-C blocked|
|QUALITY corpus representativeness|Synthetic provenance만 명시하고 real representative claim 금지|P4-B blocked|
|Commands|Final controller focused selector 15/47; golden 183; Ruff; backend 501/77 + strict mypy 49 files/0 errors + compileall; full `make check` exit 0; frontend lint/typegen/typecheck, Vitest 32/build; migration 4; scans/Compose; P2/P3 PostgreSQL 10/67; cleanup 0/0/0|P4-A final QA/acceptance passed; delivered|
|Reproducibility/tamper|Byte-identical benchmark; output/report/fixture digests `354d7c10…fd23`/`7b0601d2…8933`/`05f77739…18d0`; truncated/swapped/foreign/digest tamper rejected; Decimal precision 12/28/50 plus `ROUND_UP`/`ROUND_DOWN`/`ROUND_CEILING`/`ROUND_FLOOR`/`ROUND_HALF_EVEN` identical; all 20 dispositions bound|P4-A final QA/acceptance passed; delivered|

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

## 12. 완료된 final acceptance와 delivery

Final controller QA와 fresh independent review에서 실제 확인된 결과:

1. Exact focused controller selector: 15 passed, 47 deselected. Earlier 20/42 worker-remediation evidence remains a historical checkpoint, not the final controller count.
2. `make p4-golden-check`: 183 passed.
3. `make p4-benchmark-fixture`: repeatable/byte-identical; output/report/fixture digests `354d7c10…fd23`, `7b0601d2…8933`, `05f77739…18d0`.
4. `make backend-check`: Ruff passed, strict mypy 49 files/0 errors, pytest 501 passed/77 deselected, compileall passed.
5. `make check`: exit 0; contract/client drift, backend, frontend lint/typegen/typecheck, Vitest 32, Next production build, migration contract 4, secret scan, sensitive-document scan, Compose config passed.
6. The precision/rounding regression reran scoring and canonical revalidation at ambient precisions 12/28/50 with `ROUND_UP`, `ROUND_DOWN`, `ROUND_CEILING`, `ROUND_FLOOR`, and `ROUND_HALF_EVEN`; output/report bytes and digests were identical.
7. P2 PostgreSQL passed 10 and P3 PostgreSQL passed 67; disposable Docker containers/networks/volumes ended at 0/0/0.
8. P3 browser E2E was not run because P4-A changes no runtime/API/UI/workflow path; this is an explicit non-run, not a pass claim.
9. Fresh final independent review returned `ACCEPT_WITH_MINOR`, BLOCKER 0, MAJOR 0, MINOR 3. It recomputed source-only 16-path `0d5c259f59293f35e4cf6b83ffff13820c3c07194f5db48e54d8c8b1d09db632` and full 25-path `ba938518beca8f3718abdf4eb44430e26b3a775aea8f8b33dc5dc01937218f23` unchanged before and after review.

Accepted minor notes, none of which is a blocker/major or claimed source-fixed here:

1. Strict geometry가 required이므로 dead `missing_polygons`/`invalid_polygons` counters는 현재 unrepresentable하다. Optional-geometry semantics 변경 전에 정리한다.
2. Schema-level polygon validation arithmetic는 empirical stability를 보였지만 scorer의 explicit Decimal context 안에 있지 않다. P4-B real-corpus geometry expansion 전에 닫는다.
3. 기존 DEVLOG의 “below” cross-reference는 이 docs closure에서 [`../HANDOFF.md`](../HANDOFF.md)와 이 P4 plan을 가리키도록 보정한다.

Delivery evidence:

1. Source/integration commit `aeedceb2c3b7008439a9c72e3984be77f6135e51` is a direct descendant of baseline `2d5c02dbc612f9b612f27a36263b95e842c24e75`.
2. Fresh Orca integration worktree was created from fetched `origin/main` at that baseline.
3. `git merge --ff-only aeedceb…` succeeded with no merge commit/rebase, and non-force `git push origin HEAD:main` succeeded.
4. At capture time, post-fetch integration HEAD, `origin/main`, and remote main all equaled `aeedceb…`; baseline/source ancestry and both clean worktrees passed.
5. The commit containing this nine-file documentation closure is a newer descendant of `aeedceb…`; Git history is authoritative for its exact SHA and remote-tip status, while `aeedceb…` remains the P4-A source/integration baseline rather than the continuing tip.

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

## 14. 다음 Hermes/Orca/Codex decision/evidence prompt

```text
Prd.md, AGENTS.md, docs/plans/2026-07-30-integrated-implementation-plan.md,
docs/plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md,
docs/TRACEABILITY_MATRIX.md를 정본/계약으로 읽어라.

P4-A Offline/Synthetic은 complete/independently accepted/committed/fresh-main fast-forward
integrated/delivered 상태다. Source/integration baseline aeedceb2c3b7008439a9c72e3984be77f6135e51은
base 2d5c02dbc612f9b612f27a36263b95e842c24e75의 direct descendant다. 이 nine-file documentation
closure를 포함하는 commit은 aeedceb…의 newer descendant이고 exact SHA/remote-tip 상태는 Git
history가 정본이며, aeedceb…는 continuing tip이 아니라 P4-A source/integration baseline이다.

P4-B는 QUALITY corpus approval이 없어 blocked이고 P4-C는 provider-specific AP-02 opt-in이 없어
blocked다. Real PDF/XLS/XLSX, external OCR/AI, credential, provider call, deployment, production
DB/migration/role, auto-finalization은 금지한다. 실제 명령과 결과만 DEVLOG/KANBAN/traceability에
기록하라. 다음 gate로 P4-B QUALITY packet과 P4-C Provider-specific AP-02 packet을 각각
준비하되, named approval 전 real-corpus benchmark 또는 external Provider invocation을 시작하지 마라.
P4-A evidence는 어느 gate도 충족하지 않고 real OCR/Provider quality나 production readiness를 증명하지 않는다.
```
