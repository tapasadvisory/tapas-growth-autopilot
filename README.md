# TAPAS Growth Autopilot — private internal platform

TAPAS Advisory's local-first Growth Autopilot. It is a private internal workspace, not a SaaS service for sale.

## Modules

- Command centre and Golden Hour 30/60/90-minute campaign planning
- Gemini-backed Smart Comments drafts (human review; no automatic comment posting)
- Community Intelligence relationship register
- Auto-Discovery rules and live scan for supported sources
- Drip Growth recurring programme calendar and due-task review queue
- Growth Analytics with provenance-backed provider snapshots
- Platform connection centre: LinkedIn, YouTube, Instagram, X, Spotify, Bluesky, Mastodon and SoundCloud

## Run on Windows

Use PowerShell from the repository checkout:

```powershell
cd growth-autopilot
.\start-local.ps1
```

On the first run, the script creates a Python virtual environment, installs dependencies, copies `.env.example` to `.env` and prints a Fernet encryption key. Paste that key into `.env`, add the Gemini API key, then add the provider app credentials you intend to use. Run the script again to start the backend at `http://127.0.0.1:8000`.

Open http://127.0.0.1:8000.

Health check: http://127.0.0.1:8000/api/health  
Provider status: http://127.0.0.1:8000/api/status  
Provider setup: see [INTEGRATIONS.md](INTEGRATIONS.md).

## Important separation of subscriptions and API credentials

Google AI Pro / Antigravity authentication is for the local development environment. It is not automatically a server-side Gemini API key. Create a Gemini API key in Google AI Studio and configure it in `.env`. Google offers an eligible free API tier for limited models/quotas; free-tier data handling differs from paid-tier data handling. Check the current Google API pricing and data policy before processing confidential material.

## Live vs. pending

- Gemini Smart Comments calls the Gemini API when `GEMINI_API_KEY` is configured.
- Provider connections remain disconnected until the OAuth callback succeeds.
- Bluesky public discovery can run without account authentication.
- Live discovery adapters are implemented for Bluesky, Mastodon, YouTube and X; they require the relevant public access, API credentials or account authorization. Other provider watch rules report unsupported capabilities instead of fabricating results.
- Analytics sync exists for connected providers where the official API exposes the metrics requested. Spotify Web API does not expose Spotify for Artists' monthly-listener dashboard.
- A 15-minute discovery worker and minute-level recurring-schedule worker run while the backend process is open.
- Due recurring schedules create durable review tasks. They do not publish or engage automatically.
- Sample dashboard KPIs and the seven-day illustration remain labelled demo data; only provider snapshots are live records.

## Privacy and security

- The backend binds to `127.0.0.1` by default.
- OAuth tokens are encrypted at rest with `TOKEN_ENCRYPTION_KEY`.
- Never commit `.env`, token database files, OAuth caches, browser profiles or app secrets.
- Do not bind to `0.0.0.0`, expose a public tunnel or deploy remotely yet. Before remote access, add private workspace authentication, CSRF/session controls, HTTPS, a secrets manager, backups and audit controls.
- No provider passwords or secrets should be entered into the browser or ChatGPT.

## Validation

GitHub Actions compiles the Python backend, syntax-checks the JavaScript and runs offline smoke tests for health, provider catalogue, Gemini fail-closed behavior, discovery-rule CRUD, recurring schedule approval, missing OAuth configuration and encryption. These tests do not authenticate or make live provider API calls.

## Release 1.1 — capabilities

An additive service layer (`services/`) ported onto the unchanged v1 backend. No v1 route, table or behaviour was modified; Gemini-backed endpoints fail closed (HTTP 503) when `GEMINI_API_KEY` is not configured, and no service fabricates metrics — unavailable data is reported as `unconfigured`, `permission_denied` (null value) or an explicit requirement.

Services:

- `services/youtube_engine.py` — the 12 content pillars, Gemini title evaluation (10 ranked suggestions), YouTube Analytics retention reports (raw ratios preserved), retention-optimisation guidance, deterministic thumbnail briefs, Shorts script drafts.
- `services/github_engine.py` — public repository statistics (no token needed), traffic metrics with honest `permission_denied`/null handling, Gemini README improvement suggestions, release launch kits with an embedded ethical-growth note (no bot stars, no exchanges).
- `services/search_geo_engine.py` — Gemini AEO generation with Schema.org FAQPage JSON-LD; deterministic GEO entity audit of submitted text (CHANGEReadyX™ trademark check, diagnostic link, attributed-statistic heuristic); keyword research with `search_volume: null` (no volume source connected — nothing invented); canonical entity registry.
- `services/content_studio_engine.py` — one topic in, a full cross-platform draft bundle out (stored in `content_studio_bundles`).
- `services/cross_platform_engine.py` — platform-native drafts from source text; drafts only, never published.
- `services/experimentation_engine.py` — two-proportion z-test (pure stdlib) for A/B growth experiments.
- `services/approval_workflow_engine.py` — approval queue plus a tamper-evident, hash-chained audit log. A gate and a record only; it publishes nothing.

New endpoints: `GET /api/dashboard/summary`, `GET /api/youtube/pillars`, `POST /api/youtube/titles/evaluate`, `POST /api/youtube/retention`, `POST /api/youtube/retention/optimize`, `POST /api/youtube/shorts/generate`, `POST /api/youtube/thumbnail/brief`, `POST /api/youtube/thumbnails/analyze`, `GET /api/youtube/videos`, `GET /api/github/stats`, `POST /api/github/audit`, `POST /api/github/launch-kit`, `POST /api/search/aeo/generate`, `POST /api/search/geo/audit`, `GET /api/search/seo/status`, `POST /api/search/keywords/research`, `GET /api/search/entities`, `POST /api/studio/generate-bundle`, `GET /api/studio/bundles`, `POST /api/crossplatform/draft`, `GET|POST /api/experiments`, `POST /api/experiments/evaluate`, `GET /api/approvals/queue`, `POST /api/approvals`, `POST /api/approvals/{id}/action`, `GET /api/audit-logs`.

Optional configuration: `GITHUB_TOKEN` (public stats need no token; traffic metrics need push access). Live SEO metrics remain unavailable until a Google Search Console integration is configured — `GET /api/search/seo/status` says so rather than inventing findings.
