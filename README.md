# TAPAS Growth Autopilot — private internal platform

TAPAS Advisory's local-first Growth Autopilot. It is a private internal workspace, not a SaaS service for sale.

## Featured — The Layoff Paradox (latest analysis)

**Why AI layoffs announced before value arrives cost more than they save.** The latest CHANGEReadyX™ analysis breaks down the pattern — and what readiness-first leaders do instead.

- Read the post on LinkedIn: https://www.linkedin.com/feed/update/urn:li:activity/7526156595622264832
- Run the CHANGEReadyX™ readiness diagnostic: https://tapasadvisory.com/diagnostic

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

## Release 1.6 — publishing growth integrations

Release 1.6 is the integration foundation for publishing growth: a provider capability registry, YouTube view-target reporting, a publication campaign planner, and an engagement-intelligence webhook. It was merged after a line-by-line audit and its four required fixes. The runtime now reports version `1.6.0`.

- **Provider capability registry** (`services/provider_integrations_v16.py`) — a fail-closed validator. A provider is never reported connected on credential presence alone: `connected: False` is hard-coded, and configured credentials yield `configured_unverified` at most. vidIQ and TubeBuddy actions are always refused until a vendor API contract exists. ConnectSafely comment/reaction actions return human-review mode only. The registry is library code: it ships no provider adapters, makes no HTTP calls, and is not wired into `server.py`.
- **YouTube 5,000-view targets** (`services/youtube_growth_targets.py`) — reporting arithmetic over source-reported YouTube view counts only. Missing metrics report `awaiting_metrics`; no estimate is ever substituted. 5,000 views is a campaign target, not a guaranteed outcome.
- **Publication campaign planner** (`services/publication_orchestrator_v16.py`) — a pure planner with no I/O. Every distribution task it creates is `queued_for_approval`; comment, reaction and share tasks go to a human-review queue; paid promotion is plan-only and still requires spend approval.
- **Engagement Intelligence webhook** (`services/engagement_intelligence_engine.py` + a hook in `server.py`) — the one active behaviour in this release. After a successful *approved* publication, the auto-publish worker can dispatch an HMAC-SHA256-signed, minimal-payload `post.published`-style event to an operator-owned endpoint. It is opt-in and **off by default** (it does nothing unless `ENGAGEMENT_INTELLIGENCE_ENABLED=true` plus a webhook URL and secret are configured), and dispatch is failure-isolated: it can never block, undo or retry a publication.
- **What this release does not activate.** YouTube upload: no upload code exists in this release, and the Google connection lacks the `youtube.upload` scope — uploading needs the maintainer's OAuth re-consent first. LinkedIn organisation publishing has no code or scopes here. ConnectSafely, MagicPost and Supergrow have no adapters, so nothing dispatches to them. The engagement webhook stays inert until an endpoint and secret are configured.
- **Tests:** 94 offline tests (30 smoke + 7 reliability + 9 publication + 14 GSC/Apple + 13 auto-publish + 3 publication-event webhook + 7 v1.6 integrations + 6 engagement intelligence + 5 publication orchestrator), each suite in its own process.

## Release 1.5 — auto-publish execution layer

Release 1.5 changes exactly one property of the system, on Ram's explicit decision (8 Nov 2026): **nothing publishes without approval — and approved items now publish automatically.** The approval gate is unchanged and absolute:

- **Gate.** Only `approval_queue` items with status `approved` may execute. Expired approvals never execute (the worker retires them to `expired` and audits the refusal). Rejected, pending and expired items are never touched.
- **Publish-type only.** An item executes only if its `action_type` is `publish_post`, its platform column names the target provider, and its payload carries actual post text (direct `text`/`content`/`post_text`/`post` fields, or a cross-platform `drafts` dict). The `publication_optimization` approvals produced by publication detection are informational metadata suggestions — they **never** trigger a post, even if approved.
- **Worker.** An `auto_publish` scheduler job (default every 5 minutes, `AUTO_PUBLISH_INTERVAL_MINUTES`) polls the approved queue under the 1.2 scheduler policy. Each item is claimed atomically (`approved` → `executing`) before any provider call, so it executes at most once per claim. Every attempt — success, failure, blocked, expired — writes a tamper-evident audit entry (`autopublish.*`). Outcomes are recorded on the item's payload (`execution.post_id` / `execution.url`): terminal states `executed`, `blocked_scope`, `execution_failed`.
- **Providers, honestly scoped.** Live routes: LinkedIn personal-profile text posts (existing connection, `w_member_social`) and Bluesky (AT Protocol — needs `BLUESKY_HANDLE` + `BLUESKY_APP_PASSWORD`; until the app password is configured, Bluesky items are blocked with that reason). X is connected and will be attempted, but its granted scopes lack `tweet.write` and the account carries $0 API credits, so X posts are expected to fail (HTTP 402/403) until Ram re-consents with the write scope and adds credits — failures are bounded (default 3 attempts, 5m/10m/20m backoff, `AUTO_PUBLISH_MAX_ATTEMPTS`) and then parked as `execution_failed`, never hot-looped. YouTube items are `blocked_scope`: the Google connection holds no `youtube.upload` scope and uploads are never attempted. Mastodon, Instagram, Spotify and Substack items are likewise `blocked_scope` with the specific reason (no posting route/connection on this backend).
- **Kill switch + dry run.** `AUTO_PUBLISH_ENABLED` (default `true` per Ram's decision) stops the worker entirely; `AUTO_PUBLISH_DRY_RUN` (default `false`) simulates provider calls for the live routes so the pipeline can be proven without a public post — blocked providers stay blocked in dry-run too. `GET /api/autopublish/status` reports both flags, per-provider readiness, publish-item counts by status, and the last cycle summary.
- **Verification.** The pipeline was proven with dry-run mode + mocked provider clients (no public test post): a synthetic approved item is claimed, "published" (mock), marked `executed` and audited. The first real execution happens on Ram's next genuinely approved `publish_post` item.
- **Superseded wording.** Earlier release notes said the approval workflow "publishes nothing" and that cross-platform drafts are "never published". Those described Releases ≤1.4. From 1.5: drafts and detection approvals still never publish on their own — publication happens only through this worker, only for approved publish-type items.
- **Tests:** 73 offline tests (30 smoke + 7 reliability + 9 publication + 14 GSC/Apple + 13 auto-publish), each suite in its own process.

## Release 1.4 — Google Search Console (live) + Apple Podcasts detection

Release 1.4 is additive on the 1.3 spine: two new data sources, no route, table or behaviour removed.

- **Google Search Console** (`services/gsc_service.py` + server wiring): live search-performance data for `https://tapasadvisory.com/` via the Search Console API (webmasters v3) — sites list plus a searchAnalytics query over the last 28 days (dimensions: query, page; metrics: clicks, impressions, CTR, position), normalized into totals, top queries and top pages and stored as snapshots in `gsc_snapshots`. It rides the existing Google connection in the encrypted token store — no new OAuth flow. The module is **fail-closed**: without the `https://www.googleapis.com/auth/webmasters.readonly` scope on that connection, every endpoint reports `not_configured` with the exact missing scope and the re-consent path (set `GOOGLE_EXTRA_SCOPES` to the scope, restart, re-run the existing Google connect — the mirror of the existing `LINKEDIN_EXTRA_SCOPES` mechanism). The connected Google account already carries the scope, so sync is live: the first pull (12 Oct – 8 Nov 2026) returned 179 impressions across 28 query×page rows. Endpoints: `GET /api/gsc/status`, `POST /api/gsc/sync`, `GET /api/gsc/report`. A daily `gsc_sync` scheduler job (`GSC_SYNC_INTERVAL_MINUTES`, default 1440) runs under the 1.2 scheduler policy.
- **Apple Podcasts detection**: episodes of "Ram's CHANGEReadyX™ from TAPAS Advisory" (show id 6831708010) are detected through the public iTunes lookup API — no credentials — and registered with platform `apple_podcasts` through the same dedup → Gemini optimization → pending-approval path as Substack/YouTube. Spotify episodes share the same Anchor RSS, but Spotify-side detection waits on the parked Spotify connection (this VM's egress refuses Spotify's token exchange); no Spotify connection is attempted.
- **Tests:** 60 offline tests (30 smoke + 7 reliability + 9 publication + 14 GSC/Apple), each suite in its own process. The GSC HTTP layer and the iTunes response are stubbed/fixture-based; no live Google calls in tests.

## Release 1.3 — publication detection

Release 1.3 adds publication *detection* on the unchanged 1.2 spine. It ports the audited-good parts of an external "Gemini Core" starter (Substack RSS detection, the optimizer's enriched output fields, its no-promises system prompt) and rejects the rest (a parallel app and database, static-token provider auth, Google Ads / paid-promotion plumbing, `uvicorn[standard]`).

- **Detectors** (`services/publication_engine.py` + server wiring) observe Ram's own publications only, through authorized routes: Substack's public RSS feed (no auth), and the existing OAuth connections for YouTube (uploads playlist via the Data API) and LinkedIn (own-posts read attempted via the REST API — LinkedIn currently refuses it because the app lacks the `r_member_social` permission; the endpoint reports `permission_denied` with that exact gap and never scrapes).
- **Register + dedup:** detections land in a `publications` table with `UNIQUE(platform, external_id)`; repeat runs register nothing twice (verified live and in tests).
- **Optimize + approve:** each new publication is optimized by the existing Gemini engine (fail-closed, HTTP 503 without a key) into an enriched record — title, description, keywords, hashtags, a 40–80 word answer snippet, entity map, schema and GEO recommendations, audience, hook options, CTA, **risk flags** and a **confidence score** — and queued as a *pending* item in the existing approval queue with a 72-hour expiry. Detection never publishes, posts or promotes anything; every optimization is a draft for human decision.
- **Scheduling:** a `publication_detection` job (default every 30 minutes, `PUBLICATION_DETECTION_INTERVAL_MINUTES`) runs under the 1.2 scheduler policy — fixed id, coalesce, misfire grace, single instance.
- **Endpoints:** `GET /api/publications`, `POST /api/publications/detect`, `POST /api/publications/analyze` (the starter's `/v1/analyze`, on this API's surface and auth model), `POST /api/publications/reoptimize`.
- **Burst resilience:** Gemini's free tier rate-limits back-to-back optimization calls during a first-scan backfill (live on day one: roughly half of a 45-publication burst). Optimizations therefore retry once after a 20-second backoff, failures are recorded per publication (`optimization_error` on its approval) instead of being hidden, and `/api/publications/reoptimize` re-fetches source text and fills failed optimizations with pacing. The steady-state cadence (a few new publications per 30-minute cycle) stays well under the limit.
- **Out of scope, deliberately:** Google Ads / YouTube Promote and all paid promotion (no advertiser authorization exists); cross-platform attribution beyond the existing per-provider analytics snapshots; LinkedIn detection beyond the permission-gated attempt above.
- **Tests:** 46 offline tests (30 smoke + 7 reliability + 9 publication), each suite in its own process.

## Release 1.2 — runtime reliability

Release 1.2 is a reliability release: no new growth features, and no v1/1.1 route, table or behaviour removed. It fixes the failure mode where the backend silently disappeared when its shell session, host or process ended.

- **Persistent service (Linux):** the backend runs as a systemd system service (`deploy/tapas-growth-backend.service`) with `Restart=always` — it survives session logout, restarts automatically after a crash, and starts at boot. It is no longer a child of any shell.
- **Watchdog:** a systemd timer (`deploy/tapas-backend-watchdog.timer`) probes `/api/health` every minute; two consecutive failures restart the service and write an ALERT line to the watchdog alert log. Crash recovery is systemd's job; the watchdog covers the process-alive-but-unresponsive case.
- **Scheduler reliability:** APScheduler jobs use fixed ids with `replace_existing=True` (no duplicate registrations), `coalesce=True` and `misfire_grace_time=300` (runs missed during downtime collapse into one catch-up run instead of being dropped or duplicated), and `max_instances=1` (no overlapping executions). Schedules whose `next_run_at` passed during downtime are counted in the startup log and picked up by the one-minute schedules job — that is the defined missed-job recovery path.
- **Observability:** `/api/health` now reports `version`, `uptime_seconds` and the live scheduler job ids; startup/shutdown are logged (journald under systemd) with the job list and missed-schedule count.
- **Approval workflow:** pending approvals now carry an `expires_at` (default 72h, `APPROVAL_TTL_HOURS`). Deciding an expired item transitions it to `expired`, writes a tamper-evident audit entry and returns HTTP 410; `POST /api/approvals/{id}/renew` returns an expired item to `pending_approval` with a fresh expiry, also audited.
- **Provider verification:** live OAuth refresh + analytics sync verified for LinkedIn and YouTube; Gemini generation verified live. X analytics remains limited by the account's API credit balance (HTTP 402 from X — an account state, not a backend fault).
- **Deployment & rollback:** see `deploy/DEPLOYMENT.md` for the checklist, the VM-replacement restore script and the rollback procedure (previous release = git tag `v1.1`; code rollback is a checkout of that tag, service rollback is re-running its restore).

## Release 1.1 — capabilities

An additive service layer (`services/`) ported onto the unchanged v1 backend. No v1 route, table or behaviour was modified; Gemini-backed endpoints fail closed (HTTP 503) when `GEMINI_API_KEY` is not configured, and no service fabricates metrics — unavailable data is reported as `unconfigured`, `permission_denied` (null value) or an explicit requirement.

Services:

- `services/youtube_engine.py` — the 12 content pillars, Gemini title evaluation (10 ranked suggestions), YouTube Analytics retention reports (raw ratios preserved), retention-optimisation guidance, deterministic thumbnail briefs, Shorts script drafts.
- `services/github_engine.py` — public repository statistics (no token needed), traffic metrics with honest `permission_denied`/null handling, Gemini README improvement suggestions, release launch kits with an embedded ethical-growth note (no bot stars, no exchanges).
- `services/search_geo_engine.py` — Gemini AEO generation with Schema.org FAQPage JSON-LD; deterministic GEO entity audit of submitted text (CHANGEReadyX™ trademark check, diagnostic link, attributed-statistic heuristic); keyword research with `search_volume: null` (no volume source connected — nothing invented); canonical entity registry.
- `services/content_studio_engine.py` — one topic in, a full cross-platform draft bundle out (stored in `content_studio_bundles`).
- `services/cross_platform_engine.py` — platform-native drafts from source text. Drafts publish only if they are placed in the approval queue as `publish_post` items and approved (Release 1.5 worker).
- `services/experimentation_engine.py` — two-proportion z-test (pure stdlib) for A/B growth experiments.
- `services/approval_workflow_engine.py` — approval queue plus a tamper-evident, hash-chained audit log. The gate: from Release 1.5, approved `publish_post` items are executed by the auto-publish worker; everything else in the queue remains a record only.

New endpoints: `GET /api/dashboard/summary`, `GET /api/youtube/pillars`, `POST /api/youtube/titles/evaluate`, `POST /api/youtube/retention`, `POST /api/youtube/retention/optimize`, `POST /api/youtube/shorts/generate`, `POST /api/youtube/thumbnail/brief`, `POST /api/youtube/thumbnails/analyze`, `GET /api/youtube/videos`, `GET /api/github/stats`, `POST /api/github/audit`, `POST /api/github/launch-kit`, `POST /api/search/aeo/generate`, `POST /api/search/geo/audit`, `GET /api/search/seo/status`, `POST /api/search/keywords/research`, `GET /api/search/entities`, `POST /api/studio/generate-bundle`, `GET /api/studio/bundles`, `POST /api/crossplatform/draft`, `GET|POST /api/experiments`, `POST /api/experiments/evaluate`, `GET /api/approvals/queue`, `POST /api/approvals`, `POST /api/approvals/{id}/action`, `GET /api/audit-logs`.

Optional configuration: `GITHUB_TOKEN` (public stats need no token; traffic metrics need push access). Live SEO metrics are provided by the Release 1.4 Google Search Console module (`GET /api/gsc/report`); `GET /api/search/seo/status` continues to report the Gemini-side SEO tooling state.
