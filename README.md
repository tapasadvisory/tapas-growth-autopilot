# TAPAS Growth Autopilot

**A local-first command centre for one practice's entire social growth engine** — built by [TAPAS Advisory](https://tapasadvisory.com) to run its own multi-platform presence without handing credentials to a third-party SaaS.

It connects eight platforms behind one local backend, plans the daily "Golden Hour" of engagement, drafts AI-assisted comments that a human always reviews, tracks community relationships, and records analytics snapshots with provenance — so every number can be traced to the provider response that produced it.

## Why local-first?

Consulting practices live on trust. Growth Autopilot keeps OAuth tokens on your own machine, encrypted at rest, and binds to localhost by default. No third-party service ever holds your accounts. Discovery and drafting are automated; **publishing and engagement decisions stay human** — by design, not by limitation.

## Modules

- **Command Centre & Golden Hour planning** — 30/60/90-minute campaign plans built from connected accounts and due tasks
- **Smart Comments (Gemini)** — AI-drafted comment suggestions, fail-closed when unconfigured, always human-reviewed; nothing posts automatically
- **Community Intelligence** — a relationship register for the people who actually engage with your work
- **Auto-Discovery** — rule-based scans across supported sources (Bluesky, Mastodon, YouTube, X), reporting unsupported capabilities honestly instead of fabricating results
- **Drip Growth** — recurring programme calendar with an approval-gated review queue
- **Growth Analytics** — provider snapshots with provenance; demo figures are always labelled demo
- **Connection Centre** — OAuth 2.0 (with PKCE where applicable) for LinkedIn, YouTube, Instagram, X, Spotify, Bluesky, Mastodon and SoundCloud

## Architecture

- **Backend:** FastAPI (Python), SQLite local storage, APScheduler workers for discovery and recurring schedules
- **Frontend:** single-page vanilla JS app served by the backend
- **Security:** Fernet-encrypted token storage (`TOKEN_ENCRYPTION_KEY`), server-side OAuth state with expiry, secrets only in a local `.env` (never committed)
- **Tests:** offline smoke suite covering health, provider catalogue, Gemini fail-closed behaviour, discovery-rule CRUD, schedule approval, missing-OAuth handling and encryption

## Quickstart (Windows)

```powershell
git clone https://github.com/tapasadvisory/tapas-growth-autopilot
cd tapas-growth-autopilot
.\start-local.ps1   # first run creates .venv, installs deps, scaffolds .env and prints an encryption key
# fill in .env (Gemini key + the provider apps you want), then run again
```

Backend at `http://127.0.0.1:8000` · health check `/api/health` · provider status `/api/status` · per-provider setup in `INTEGRATIONS.md`.

> Note: install `uvicorn` plain rather than `uvicorn[standard]` if your Python is very new — the optional `pyyaml` wheel can fail to build; the Autopilot runs identically without the extras.

## Honest status

This is a working internal tool released as-is, not a commercial SaaS. Some providers expose less analytics than their dashboards (e.g. Spotify's general Web API has no monthly-listener figures), and some connections require the platform's own app review. Where a metric or capability isn't available, the Autopilot says so rather than inventing it.

## Built by

**Ram Narayanan** — Transformation Leader, Architect of CHANGEReadyX™, Founder, TAPAS Advisory.
Part of the CHANGEReadyX™ growth engine behind the *AI Transformation Failures* content series and the *CHANGEReadyX™ Insights* podcast.

If this project is useful to you, a ⭐ helps other practitioners find it.

## Licence

© TAPAS Advisory. Released publicly for study and adaptation with attribution — please contact TAPAS Advisory for commercial reuse.
