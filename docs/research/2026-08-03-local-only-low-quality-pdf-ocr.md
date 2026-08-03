# P4 local-only low-quality PDF OCR implementation note

- Date: 2026-08-03
- State: `SECOND_REQUEST_CHANGES_REMEDIATED_READY_FOR_INDEPENDENT_REREVIEW`
- Scope: generated non-sensitive synthetic documents only
- Runtime boundary: local model files, zero outbound network, zero external OCR/AI

## Decision

The active OCR implementation lane is local-only. It uses a page-level native-text-first pipeline and invokes locally installed PaddleOCR models only when a page has no sufficient native text layer. External Provider benchmarking and account/credential requests are deferred and are not active Next or Blocked work for this increment. Existing P4-C research and approval templates remain historical/future-gate material and grant no approval.

The implementation adds `LocalOcrExtractionProvider` behind the existing extraction port; no database migration or provider persistence-schema change was required. Every local OCR result is an extraction candidate with `review_required=true`. There is no automatic final decision, approval, or fallback to synthetic/external OCR.

## Runtime and model contract

- Python 3.12 project environment with exact locked optional dependencies: PaddleOCR 3.7.0, PaddlePaddle 3.3.1, NumPy 2.3.5, OpenCV contrib 4.10.0.84, Pillow 12.3.0, and PyMuPDF 1.28.0.
- Detection: `PP-OCRv5_mobile_det`; recognition: `korean_PP-OCRv5_mobile_rec`.
- The versioned manifest records engine, model, language, upstream/version, license, official source URL, archive byte size and SHA-256, unpacked tree SHA-256, and local path.
- Bootstrap is an explicit setup-only command. Normal runtime requires the declared local paths and rejects missing/mismatched models, path escape, unsupported engine, endpoint/source overrides, credentials, or network access with stable non-sensitive error codes.
- Worker readiness verifies models off the event-loop thread and caches its first result. A cached failure is deliberately fail closed and restart-required: installing or repairing model files after a failed probe does not retry in the same worker process; restart the worker and rerun `make p4-local-ocr-preflight`.
- Model archives and unpacked binaries live under ignored `.local-ocr-models/`; none is Git-tracked.

Ordinary CI (`make check` / `make backend-check`) remains credential-free, network-free, and independent of installed model binaries; it excludes tests marked `local_ocr_runtime`. Exact package/model hashes, real engine initialization, PyMuPDF/OpenCV runtime behavior, and zero-network initialization are a separate required local-runtime controller gate under `make p4-local-ocr-preflight`. This separation does not waive that gate for a local OCR deployment candidate.

## Pipeline

PDF input is immutable. The pipeline enforces PDF-only input, 25 MiB/file, 10 pages, 120 million total rendered pixels, 12 variants/page, 120 seconds, and process-wide concurrency 1 with overlapping attempts rejected by a stable fail-closed error. Encrypted, corrupt, oversized, and over-budget inputs fail closed.

Each page is classified independently. A sufficient native text layer is used without rendering or OCR. An insufficient page renders at 300 DPI, or bounded 400 DPI when its embedded raster evidence is below 200 effective DPI. The original rendering is always retained. Deterministic variants include 0/90/180/270-degree originals, grayscale/CLAHE, adaptive threshold, Otsu, conservative denoise/sharpen, bounded deskew, and conservative four-corner perspective correction.

Candidates preserve page, normalized source-frame rectangular bbox, spatial reading order, confidence, selected variant/recipe, rotation, deskew status/angle, and perspective provenance. Polygons are not implemented or claimed. The native and local-OCR routes use the same stable review-reason evaluator for human review, low confidence, missing values, native/OCR disagreement, variant disagreement, numeric/unit/LOT conflicts, and table-layout review. Native table suspicion comes from a conservative bounded three-row/three-column alignment signal over native word geometry, without rendering or OCR. PP-StructureV3 is deferred: table-like pages fail closed with `TABLE_LAYOUT_REVIEW_REQUIRED`.

Logs and the canonical report omit document paths, source/OCR bodies, and full payloads. The report carries hashes and aggregate metrics only.

## Synthetic verification

The fixed-seed generator creates non-company-specific Korean/English/numeric COA-style documents. Unit/contract coverage includes 0/90/180/270 rotation, positive/negative skew, a deterministic positive perspective-correction case with a finite invertible source transform, uneven illumination/shadow, low contrast, Gaussian and salt-pepper noise, blur/JPEG artifacts, downsample/oversample, mixed native/scanned pages, native and scanned tables, blank/corrupt/oversized inputs, runtime network denial, model absence/hash mismatch, provider candidate-only behavior, and worker readiness.

The real-engine smoke uses five compound-degradation cases and passed twice serially with byte-identical sanitized output:

- output SHA-256: `581ed7dad0973c3a999ce6e1b48bc9368452e5f6f9aab3fdc3e8c1fbe72437c1`
- aggregate digest: `6545119c4a18c2e788024521a3e77fbdd38b4fc902a01900063d79327b1c6a9c`
- required-header accuracy: `1.0000` (gate `>=0.95`)
- numeric accuracy: `1.0000` (gate `>=0.98`)
- review-trigger exposure: `1.0000` (gate `=1.00`)
- initialization/prediction network attempts: `0/0`

Header and numeric scoring require each expected field and value to share one reconstructed physical line using normalized candidate bboxes; it is not document-wide substring/set membership. Review exposure is evaluated on the public `LocalOcrExtractionProvider` candidate, including mandatory child review/reasons and positive/negative table-reason controls. These are generated-synthetic engineering gates, not representative-corpus KPIs or a production-readiness claim. Exact bytes remain host/font-bound because the generated fixture uses an allowlisted installed Korean font; the target proves repeatability for the recorded local environment, not cross-host font identity.

## Commands actually verified

- `make backend-check`: Ruff passed; strict mypy passed for 67 source files; backend `641 passed, 92 deselected`; compileall passed.
- `make frontend-check`: lint, type generation/check, Vitest `32 passed`, and Next production build passed.
- `make contracts-check`: generated contract drift passed.
- `make p4-golden-check`: `198 passed`.
- `make p4-preflight-check`: `97 passed` with default DENY and no side effects.
- `make p4-local-ocr-preflight`: exact package/model checks, engine initialization with zero network, manifest binding `cf6721ea4ebe2e54946fa85c81d45d8d96261cf7ef864f55d8bd5ad864aaeec9`, and focused tests (`43 passed`) passed.
- `make p4-local-ocr-smoke`: the earlier final candidate's real generated-input local PaddleOCR inference passed twice with the identical digests above and field-associated `1.0000/1.0000/1.0000` metrics. It was not rerun for this remediation because only native-text review routing, a native-layout signal, tests, and documentation changed; image preprocessing/OCR output and metric payload code did not change.
- Migration contract (`4 passed`), secret scan, sensitive-document scan, and Compose configuration passed.

Initial setup evidence is separate from final validation: the fresh worktree lacked development packages and frontend `node_modules`; locked `uv sync --extra dev` and `pnpm install --frozen-lockfile` supplied them. During exploratory smoke polling, overlapping worktree-local OCR processes caused memory pressure; only those exact processes were terminated. The final smoke runs were serialized. No n8n or unrelated process/service was changed.

## Remaining gates and prohibitions

This uncommitted worktree candidate has not received independent acceptance and has not been delivered. It is ready for another independent read-only review. P4-B remains `BLOCKED_QUALITY_CORPUS_APPROVAL` for any future representative real-corpus benchmark, but that deferred gate is not required for this synthetic/local implementation candidate. P4-C remains `BLOCKED_AP02_PROVIDER_OPT_IN` for any future external Provider and is also deferred from the active lane.

No real source body was opened, copied, committed, uploaded, or transmitted. No external Provider/OCR/AI call, credential, telemetry, DB migration, DB-role change, real-data import/apply, deployment, release, public exposure, or production activation occurred.

## Independent review remediation

The independent Claude review initially returned `REQUEST_CHANGES` with blocker/major/minor counts `1/9/14`. This candidate closes the blocker and all nine majors:

- one shared native-text predicate now controls both rendering and routing, with real generated-PDF regressions for insufficient and sufficient text layers;
- OpenCV 4.10 `(x,y)` deskew and signed-angle normalization are tested at positive/negative three degrees, and synthetic skew borders are white in all channels;
- smoke scoring is field/physical-line-associated and review exposure is based on public provider candidates with negative reason controls;
- dominant image area controls DPI, so tiny logos do not force 400 DPI;
- selected variant and transforms are explicit, rotated bboxes map back to the source frame, local candidate bboxes normalize to `0..1`, and polygons are not claimed;
- readiness verification is thread-offloaded and caches both success and failure once per worker app;
- documented `HYC_LOCAL_OCR_*` names work while legacy unprefixed names remain compatible;
- concurrency one is enforced across pipeline instances and tested with overlapping threads;
- bounded hardening covers render-DPI upper bounds, deadlines inside document load, stable page-error mapping, dot/root manifest rejection, structured validation-error mapping, nested bootstrap destinations, redirect validation before following, reason severity order, fail-closed variant limits, spatial reading order, and bounded resolver reads after open.

The fresh Claude re-review confirmed the original blocker and majors B1/M1-M9 closed, then returned `REQUEST_CHANGES` for one new major: the native route was not applying the shared stable reason evaluator. That major is now fixed in code. Focused regressions prove native missing LOT emits `MISSING_REQUIRED`, a low-confidence native candidate emits `LOW_CONFIDENCE`, and real native table-like layout emits `TABLE_LAYOUT_REVIEW_REQUIRED` without rendering or OCR; mandatory Human Review remains present in every case. A separate deterministic positive regression proves conservative perspective correction can set `perspective_corrected=true` while retaining a finite invertible source transform, so no image-preprocessing change was required.

Remaining review minors are disclosed rather than overclaimed: SIGALRM cannot safely terminate Paddle C-level inference from a non-main thread, although pre/post inference and in-load deadline checks fail closed; the in-process network-deny audit uses process-wide socket patching and therefore still requires process/container isolation before service wiring; an adversarial ancestor-directory swap is not fully eliminated even though resolved containment, `O_NOFOLLOW`, descriptor metadata, regular-file validation, and `max+1` bounded reads close the reported unbounded-growth race; and cross-host synthetic bytes depend on the installed allowlisted font. These are bounded candidate-stage limitations, not production approvals.

Fresh re-review residuals are also bounded and explicit. Smoke review-exposure controls remain table-reason-specific rather than exhaustive across every reason, while focused tests cover the newly relevant native missing/low-confidence/table paths. Restoring a pre-existing outer `ITIMER_REAL` uses its original interval and can delay that outer timer by the inference duration; changing inference timing now would require another real-engine smoke. Concurrency one is process-wide, so any future multi-worker service needs a single OCR worker process or an external singleton queue/lock before wiring. A defensive off-crop native bbox case was not constructible through PyMuPDF, but API normalization clamps only right/bottom and the shared schema does not yet enforce the local provider's `0..1` convention. Those defensive schema/clamping changes are deferred to a separately reviewed contract increment rather than expanding this candidate after its public contracts passed. Korean-only marker recognition and per-line orientation also remain fail-closed limitations: they route to OCR/review and do not authorize a download or automatic decision.
