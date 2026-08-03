# P4 local-only low-quality PDF OCR implementation note

- Date: 2026-08-03
- State: `COMPLETE_ACCEPTED_COMMITTED_FRESH_MAIN_FF_INTEGRATED_DELIVERED_TO_ORIGIN_MAIN`
- Source/integration baseline: `91fd4a8229b12d2b229f2ef9abb9dceef93591b5`
- Pre-closure main baseline: `96413d20230b62033ecb754a12e5a1a621a7b95c` (later descendant)
- Scope: generated non-sensitive synthetic documents only
- Runtime boundary: local model files, zero outbound network, zero external OCR/AI

## Decision

The authorized local-only OCR engineering lane is complete, independently accepted, committed, fresh-`origin/main` fast-forward integrated, and delivered. It uses a page-level native-text-first pipeline and invokes locally installed PaddleOCR models only when a page has no sufficient native text layer. Source/integration baseline `91fd4a8…` is an ancestor of pre-closure main `96413d2…`; the commit containing this documentation closure will be a newer descendant, and Git history is authoritative for the exact SHA and remote-tip state. External Provider benchmarking and account/credential requests are deferred and are not active work. Existing P4-C research and approval templates remain future-gate material and grant no approval.

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

Candidates preserve page, normalized source-frame rectangular bbox, spatial reading order, confidence, selected variant/recipe, rotation, deskew status/angle, and perspective provenance. Polygons are not implemented or claimed. The native and local-OCR routes use the same stable review-reason evaluator for human review, low confidence, missing values, native/OCR disagreement, variant disagreement, numeric/unit/LOT conflicts, and table-layout review. Native table suspicion comes from a bounded but broad/over-inclusive three-row/three-column alignment signal over native word geometry, without rendering or OCR; it may add `TABLE_LAYOUT_REVIEW_REQUIRED` to ordinary multi-line native text and is intentionally not described as a precise table detector. PP-StructureV3 is deferred.

Logs and the canonical report omit document paths, source/OCR bodies, and full payloads. The report carries hashes and aggregate metrics only.

## Synthetic verification

The fixed-seed generator creates non-company-specific Korean/English/numeric COA-style documents. Unit/contract coverage includes 0/90/180/270 rotation, positive/negative skew, a deterministic positive perspective-correction case with a finite invertible source transform, uneven illumination/shadow, low contrast, Gaussian and salt-pepper noise, blur/JPEG artifacts, downsample/oversample, mixed native/scanned pages, native and scanned tables, blank/corrupt/oversized inputs, runtime network denial, model absence/hash mismatch, provider candidate-only behavior, and worker readiness.

The real-engine smoke uses five compound-degradation cases. The earlier pre-final-remediation candidate runs passed twice serially, and the later Hermes final-source post-remediation run passed with the same sanitized digests and metrics:

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
- `make p4-local-ocr-smoke`: the pre-final-remediation candidate passed twice with the digests above. The independent reviewer did not rerun the expensive smoke after the final native-route remediation and retained that as a minor documentation/evidence caveat. Hermes later ran the final source post-remediation; it passed with the same output/aggregate digests, field-associated `1.0000/1.0000/1.0000` metrics, and network `0/0`.
- Migration contract (`4 passed`), secret scan, sensitive-document scan, and Compose configuration passed.

Initial setup evidence is separate from final validation: the fresh worktree lacked development packages and frontend `node_modules`; locked `uv sync --extra dev` and `pnpm install --frozen-lockfile` supplied them. During exploratory smoke polling, overlapping worktree-local OCR processes caused memory pressure; only those exact processes were terminated. The final smoke runs were serialized. No n8n or unrelated process/service was changed.

## Delivery, remaining gates, and prohibitions

Source/integration commit `91fd4a8229b12d2b229f2ef9abb9dceef93591b5` (`feat: add local-only low-quality PDF OCR`) was independently accepted, fresh-main fast-forward integrated, and non-force pushed. Pre-closure main `96413d20230b62033ecb754a12e5a1a621a7b95c` is its later descendant. This closure's commit will be newer; Git history is authoritative for the exact continuing tip.

P4-B remains `BLOCKED_QUALITY_CORPUS_APPROVAL` for any future representative real-corpus benchmark. Aggregate inventory is 4 candidate documents and 0 eligible because human-label and independent-review evidence are absent. This is a future quality-validation gate, not unfinished implementation debt, and it is not required to call the authorized local-only engineering lane complete. P4-C remains `BLOCKED_AP02_PROVIDER_OPT_IN` for any future external Provider, but no Provider is selected/approved and the lane is deferred/not required for the local-only architecture. No account, credential, endpoint, network call, or external-provider implementation is active.

No real source body was opened, copied, committed, uploaded, or transmitted. No external Provider/OCR/AI call, credential, telemetry, DB migration, DB-role change, real-data import/apply, deployment, release, public exposure, or production activation occurred.

## Independent review remediation

The independent Claude review initially returned `REQUEST_CHANGES` with blocker/major/minor counts `1/9/14`. The accepted source closes the blocker and all nine majors:

- one shared native-text predicate now controls both rendering and routing, with real generated-PDF regressions for insufficient and sufficient text layers;
- OpenCV 4.10 `(x,y)` deskew and signed-angle normalization are tested at positive/negative three degrees, and synthetic skew borders are white in all channels;
- smoke scoring is field/physical-line-associated and review exposure is based on public provider candidates with negative reason controls;
- dominant image area controls DPI, so tiny logos do not force 400 DPI;
- selected variant and transforms are explicit, rotated bboxes map back to the source frame, local candidate bboxes normalize to `0..1`, and polygons are not claimed;
- readiness verification is thread-offloaded and caches both success and failure once per worker app;
- documented `HYC_LOCAL_OCR_*` names work while legacy unprefixed names remain compatible;
- concurrency one is enforced across pipeline instances and tested with overlapping threads;
- bounded hardening covers render-DPI upper bounds, deadlines inside document load, stable page-error mapping, dot/root manifest rejection, structured validation-error mapping, nested bootstrap destinations, redirect validation before following, reason severity order, fail-closed variant limits, spatial reading order, and bounded resolver reads after open.

The fresh Claude re-review confirmed the original blocker and majors B1/M1-M9 closed, then returned `REQUEST_CHANGES` for one new major: the native route was not applying the shared stable reason evaluator. MA-1 was remediated. Final independent review returned `ACCEPT_WITH_MINOR` with BLOCKER 0, MAJOR 0, MINOR 4, NOTE 8 and confirmed B1/M1-M9 plus MA-1 closed. Focused regressions prove native missing LOT emits `MISSING_REQUIRED`, evaluator wiring can emit `LOW_CONFIDENCE`, and real native table-like layout emits `TABLE_LAYOUT_REVIEW_REQUIRED` without rendering or OCR; mandatory Human Review remains present. A separate deterministic positive regression proves perspective correction can set `perspective_corrected=true` while retaining a finite invertible source transform.

The four final-review minors remain open and bounded:

1. Native table detection is a broad/over-inclusive alignment signal and can add a table-review reason to ordinary multi-line native text. This fails closed but reduces reason-code specificity.
2. Native `LOW_CONFIDENCE` evaluator wiring is tested with a fake backend. Production `PyMuPdfDocumentBackend` native lines use confidence `1.00`, so the live native route cannot currently generate that reason from confidence alone.
3. The independent reviewer did not rerun the expensive real smoke after final native-route remediation. Later Hermes final-source smoke passed with the final digests/metrics recorded above; both the review-time caveat and later controller evidence are preserved.
4. Native pages call `page.get_text("words", sort=True)` twice, duplicating word extraction on the fast path.

Separately, a carried-forward first-review residual remains open and is not one of the final review's four minors or eight notes: an adversarial ancestor-directory swap is not fully eliminated despite resolved containment, `O_NOFOLLOW`, descriptor metadata, regular-file validation, and `max+1` bounded reads. It is not claimed fixed.

The eight final-review notes also remain explicit: (1) SIGALRM cannot interrupt in-flight Paddle C-level inference, and restoring a pre-existing outer timer can delay it; (2) network denial is a process-wide socket patch and requires process/container isolation before service wiring; (3) concurrency one is process-local, so future multi-worker wiring needs a singleton worker/queue/lock; (4) the shared bbox schema does not enforce the local provider's `0..1` convention; (5) left/top defensive clamping remains narrower than right/bottom; (6) failed readiness is cached for the worker lifetime and recovery requires restart; (7) ordinary CI excludes `local_ocr_runtime`, so the separate local preflight remains mandatory; and (8) scope limits include English-only native markers, no per-line 180-degree orientation, host/font-bound synthetic bytes, table-specific smoke review controls, and no production route wired to `LocalOcrExtractionProvider`. These limitations fail closed and do not support a production-readiness claim.

## Public synthetic-demo boundary

Frontend remediation commit `96413d2…` keeps the existing local API path when `NEXT_PUBLIC_HYC_PUBLIC_DEMO` is absent and, when it equals `1`, confines the public Vercel demo to synthetic browser-local state with no backend/internal API call or server persistence. Its independent review returned `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 6). The six bounded residuals remain open: (1) one approval-button assertion is vacuous in the static initial render; (2) no runtime fetch-spy/effect coverage proves the network guards; (3) source-slicing tests are formatting-brittle; (4) public workflow-status copy can remain server-oriented; (5) no committed `vercel.json`/`.vercelignore` pins the flag or Root Directory, so correctness depends on saved environment/project configuration; and (6) root `.env.example` does not feed the Compose web image build. None is claimed fixed. Controller frontend verification was 36 passed plus build. Verified 2026-08-03 KST production evidence is Vercel project `hanyangchem_qc`, target production deployment `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y`, `READY` at `https://hanyangchem-739r15g9t-judy-ng-ii-nii-s-projects.vercel.app`; production alias `https://hanyangchemqc.vercel.app` points to it and deployment meta is `sourceCommit=cf6d6327172fb09da0fe0e3b12159f6596553c41`. The Vercel build completed Next.js 15.5.22 compile/lint/type validity, five static pages/routes and `/api/health` in 57s; root returned HTTP 200 and health returned `{"status":"ready"}`. Browser QA at the alias observed title `HANYANG QUALITY | 입고 검사`, public/no-backend/no-server-persistence boundary, no `Failed to fetch`, no `localhost`/`127.0.0.1` resource entries, only the alias resource host, and zero console messages/errors. Team-lead interaction exposed no API approval button, did expose the local synthetic approval button, and had no failed-fetch copy. Production/Preview flag values are saved. This proves only the public synthetic frontend boundary of this exact deployment; backend, DB, worker, OCR, model artifacts, and original documents remain local/intranet-only. Any future missing or incorrect flag/configuration can fall back to localhost-fetch mode and must repeat deployment API and browser network/behavior verification. The commit containing this post-deployment documentation is a later docs-only descendant with `frontend/` unchanged from `cf6d632…`; the verified deployment therefore remains the relevant frontend artifact and a rebuild is not required solely to serve unchanged frontend bytes. Git history is authoritative for the later docs-only tip. The independent reviewer ran Vitest 36, `tsc`, and `eslint`; it did not run a build or Playwright.
