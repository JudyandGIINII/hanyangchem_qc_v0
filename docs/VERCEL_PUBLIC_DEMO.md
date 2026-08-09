# Vercel public synthetic demo configuration and boundary

The public synthetic demo runs the Next.js frontend (`frontend/`) on Vercel as a synthetic, frontend-only demonstration. In that mode it must not reach backend APIs, the database, OCR workers, or any external service.

`NEXT_PUBLIC_HYC_PUBLIC_DEMO` is a **build-time** variable. Next.js inlines `NEXT_PUBLIC_*` values into the bundle when the app is built, so setting it only at runtime has no effect. Every mechanism below therefore sets it during the build.

## 1. Committed repository configuration

- **`vercel.json`** (root and `frontend/vercel.json`) pins the public build flag:

  ```json
  {
    "build": { "env": { "NEXT_PUBLIC_HYC_PUBLIC_DEMO": "1" } }
  }
  ```

  Both copies are committed because which one Vercel reads depends on the dashboard Root Directory setting. Any Vercel build therefore compiles with the flag on, which is the fail-safe direction: a public build defaults to the disconnected demo rather than to localhost-fetch mode.

- **`.vercelignore`** (root and `frontend/.vercelignore`) keeps non-frontend material out of the build context: `backend/`, `docs/`, `docker/`, `compose.yaml`, `scripts/`, `Makefile`, `*.pdf`, `*.xlsx`, `*.xls`, and `.local-ocr-models/`.

## 2. Local Compose is the opposite default

`compose.yaml` passes the same variable into the web image build:

```yaml
web:
  build:
    context: .
    dockerfile: frontend/Dockerfile
    args:
      NEXT_PUBLIC_HYC_PUBLIC_DEMO: ${NEXT_PUBLIC_HYC_PUBLIC_DEMO:-0}
```

and `frontend/Dockerfile` declares `ARG NEXT_PUBLIC_HYC_PUBLIC_DEMO=0` with a matching `ENV` before `RUN pnpm build`.

The default here is **`0` on purpose**. Compose is the local intranet stack and must keep talking to the real backend API; only an explicit operator override (`NEXT_PUBLIC_HYC_PUBLIC_DEMO=1 docker compose …`) selects demo mode. `backend/tests/contract/test_public_demo_build_contract.py` pins this default, the compose wiring, and the requirement that `ARG`/`ENV` precede `pnpm build`.

## 3. Dashboard-only settings

These are project settings that `vercel.json` cannot express. They must be set in the Vercel dashboard (or via project link) and are **not** pinned by anything in this repository:

- **Root Directory** — set to `frontend`.
- **Framework Preset** — set to `Next.js`.

Because these remain dashboard state, a missing or incorrect configuration can still produce a build that falls back to localhost-fetch mode. Any future public deployment must therefore be re-verified against the deployment API and a real browser session, as recorded in `HANDOFF.md`.

## 4. Test coverage

`frontend/tests/public-demo.test.tsx` runs under `happy-dom` and mounts the real component:

- With `publicDemo=true`, `fetch` is called **zero** times across bootstrap, stage navigation, `LEAD`/`ADMIN` role switching, and the synthetic approval action.
- With `publicDemo=false`, `fetch` **is** issued against `/api/v1/local-auth/sessions` on bootstrap and on role switch. This control is what makes the zero-fetch assertion meaningful rather than a silent failure to mount.
- Public markup must contain the synthetic status copy `합성 로컬 상태` and must not contain `검사 생성 전`, `SESSION_READY`, or raw server enum names; the local-API test asserts those are still present.

## 5. Boundary

This configuration proves only the synthetic frontend boundary. The backend, database, worker, OCR engine, models, and original documents remain local/intranet-only, and nothing here authorizes deployment, release, or production activation.
