# TAPAS Growth Autopilot — live-integration backend

Private internal platform. This backend adds live Gemini drafting, provider OAuth, public discovery sources, persistent data and scheduled workflow execution. It does not make artificial views, followers, likes or reciprocal comments.

## Run on Windows

1. Copy `.env.example` to `.env`.
2. Generate a token encryption key:
   ```powershell
   py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Put the generated value in `TOKEN_ENCRYPTION_KEY`.
3. Add a Gemini API key from Google AI Studio to `GEMINI_API_KEY`. Google AI Pro / Antigravity authentication is separate from Gemini API billing and quota.
4. Add provider OAuth app credentials to `.env` only for platforms you want to connect.
5. Run:
   ```powershell
   .\start-local.ps1
   ```
6. Open http://127.0.0.1:8000. API health: http://127.0.0.1:8000/api/health.

The first run installs backend dependencies and creates `.env.example` as `.env` when absent, then stops so secrets can be configured. The second run starts FastAPI.

## OAuth redirect URIs

Register the exact callback URLs for each developer app. With the default local URL:

- LinkedIn: `http://127.0.0.1:8000/api/oauth/linkedin/callback`
- YouTube / Google: `http://127.0.0.1:8000/api/oauth/youtube/callback`
- Instagram: `http://127.0.0.1:8000/api/oauth/instagram/callback`
- X: `http://127.0.0.1:8000/api/oauth/x/callback`
- Spotify: `http://127.0.0.1:8000/api/oauth/spotify/callback`
- Mastodon: `http://127.0.0.1:8000/api/oauth/mastodon/callback`
- SoundCloud: `http://127.0.0.1:8000/api/oauth/soundcloud/callback`

Use the identical URL in `TAPAS_BASE_URL` and the provider's developer console. For remote access, use a stable HTTPS domain and set redirect URIs to that domain.

## Provider setup and limitations

- **Gemini:** `GEMINI_API_KEY` is required for server-side live drafting. A Google AI Pro subscription does not automatically provide a server API key. Default model is `gemini-3.8-flash`; change `GEMINI_MODEL` if your project does not have access. Google documents a free API tier for limited model/usage combinations, while its paid tier has higher limits and different data-use terms. Check the current pricing and data policy before processing confidential content.
- **LinkedIn:** OAuth requests OIDC identity and `w_member_social`. Company Page analytics need approved Community Management API access, the approved `rw_organization_admin` permission and an organization admin role. This starter does not request restricted permissions automatically. Keyword search of the LinkedIn feed is not implemented in this build.
- **YouTube:** Google OAuth requests `youtube.readonly` and `yt-analytics.readonly`. Enable YouTube Data API v3 and YouTube Analytics API in the Google Cloud project.
- **Instagram:** Configure an Instagram Login app and eligible Professional account. Insights metrics depend on the account type and Meta permissions approved for the app. Keyword/hashtag discovery is not yet enabled in this build.
- **X:** OAuth2 PKCE profile and recent-post search are implemented. X's current developer access is consumption-metered; review read charges, endpoint limits and app permissions before enabling frequent background scans.
- **Spotify:** The user profile/top-artist/recent-listening scopes connect the Spotify listener account, and catalog search is available for keyword discovery. Spotify Web API does not expose Spotify for Artists monthly listeners or its full creator dashboard data. Spotify content metadata is retained as source data only and is not submitted to Gemini.
- **Bluesky:** Public AppView keyword discovery works without account login. Setting `BLUESKY_HANDLE` enables public author-feed snapshots. Account-private actions require a separate AT Protocol OAuth setup.
- **Mastodon:** OAuth app registration is performed dynamically on the user's chosen HTTPS instance. Search support depends on instance configuration and scopes.
- **SoundCloud:** OAuth2.1 PKCE profile, track reads and public track search are implemented. SoundCloud currently requires an Artist Pro subscription to register API applications and receive client credentials.

## Background jobs

- Discovery rules are scanned every `DISCOVERY_INTERVAL_MINUTES` minutes while the backend process is running. Implemented sources are Bluesky public post search, Mastodon instance search, YouTube video search, X recent-post search, Spotify catalog search and SoundCloud track search. LinkedIn and Instagram keyword search are not enabled in this version; their rules return an explicit unsupported capability rather than fake results.
- Recurring schedules are checked every minute. Due entries create durable review tasks and advance the cadence. Schedules themselves do not publish. Publishing runs through the approval queue: from Release 1.5, an item approved as a `publish_post` is executed automatically by the auto-publish worker (see README, Release 1.5) — approval is the publishing decision; nothing unapproved ever publishes.
- Background workers run only while this local backend process remains open. Analytics polling is opt-in: set `ANALYTICS_AUTO_SYNC_ENABLED=true` and choose `ANALYTICS_SYNC_INTERVAL_MINUTES` (minimum 15) after reviewing the provider's API quota/cost. It is disabled by default. A production deployment needs a persistent worker/queue and monitoring.

## API

- `GET /api/health`
- `GET /api/status`
- `POST /api/ai/comments`
- `GET|POST /api/discovery/rules`
- `DELETE /api/discovery/rules/{id}`
- `POST /api/discovery/scan`
- `GET /api/discovery/items`
- `GET|POST /api/schedules`
- `POST /api/schedules/{id}/approve`
- `GET /api/tasks`
- `POST /api/analytics/sync/{provider}`
- `GET /api/analytics/snapshots`
- `GET /api/connect/{provider}/start`

## Security

- The app binds to `127.0.0.1` by default and is intended for local private use.
- OAuth states expire after 10 minutes; X/Spotify/SoundCloud/Mastodon use PKCE.
- Provider access and refresh tokens are encrypted at rest using Fernet and `TOKEN_ENCRYPTION_KEY`.
- Do not commit `.env`, the SQLite data directory, OAuth caches, API keys or tokens.
- Before remote deployment, add workspace authentication, CSRF/session protection, HTTPS, a secrets manager, database backup, audit policy and production job queue.
- No credentials are accepted in the browser UI or chat.


## Provider console quick links and setup checklist

Create provider applications using the accounts you own. Copy the credentials into the local `.env` on your Windows machine; do not send them in chat.

| Platform | Developer console / documentation | Local configuration |
|---|---|---|
| Gemini | [Google AI Studio API keys](https://aistudio.google.com/app/apikey) · [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) | `GEMINI_API_KEY`, optionally change `GEMINI_MODEL` |
| LinkedIn | [LinkedIn Developer Apps](https://www.linkedin.com/developers/apps) · [OAuth guide](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow) | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`; register the callback URL; request only scopes shown as approved for the app |
| YouTube | [Google Cloud Credentials](https://console.cloud.google.com/apis/credentials) · [YouTube Analytics API](https://developers.google.com/youtube/analytics/reference/reports/query) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; enable YouTube Data API v3 and YouTube Analytics API |
| Instagram | [Meta for Developers Apps](https://developers.facebook.com/apps/) · [Instagram API documentation](https://developers.facebook.com/docs/instagram-platform/) | `META_APP_ID`, `META_APP_SECRET`; configure Instagram Login, redirect URL and required permissions |
| X | [X Developer Console](https://developer.x.com/en/portal/dashboard) · [API pricing](https://developer.x.com/) | `X_CLIENT_ID`; configure OAuth 2.0 Authorization Code + PKCE and the callback URL; add secret only for confidential clients |
| Spotify | [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) · [Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`; add the callback URL and allowlist the user in development mode |
| Bluesky | [AT Protocol docs](https://docs.bsky.app/) | Public keyword search works without login; optional `BLUESKY_HANDLE` for public author feed snapshots |
| Mastodon | [Mastodon API docs](https://docs.joinmastodon.org/) | No developer client ID needed in advance; enter the HTTPS instance URL in TAPAS, which registers a read-only app |
| SoundCloud | [Register API app](https://developers.soundcloud.com/docs/api/register-app) · [API guide](https://developers.soundcloud.com/docs/api/guide) | `SOUNDCLOUD_CLIENT_ID`, `SOUNDCLOUD_CLIENT_SECRET`; API app registration currently requires Artist Pro |

### Important account / API constraints

- **Gemini:** Google AI Pro / Antigravity is not an application API key or server-side quota. Google AI Studio offers a limited free API tier for eligible models and projects; free-tier data handling differs from paid-tier data handling. Do not send confidential client or personal information through the free API tier unless its data-use terms are acceptable for that content.
- **LinkedIn:** OAuth consent only grants scopes approved for the developer app. Open permissions include OpenID Connect and Share on LinkedIn. Organization/Page analytics require Community Management API product access, the approved scope(s) and Page-admin authorization. LinkedIn's documented redirect URI guidance requires a registered absolute HTTPS URL; the default loopback HTTP URL may not be accepted for this provider.
- **YouTube:** Analytics reports require the owner's OAuth consent with the `yt-analytics.readonly` scope. YouTube API quota and any Google app verification requirements still apply.
- **Instagram:** Insights are limited by the professional-account type, selected Login product, approved permissions and account eligibility.
- **X:** The current developer platform is usage/credit-metered. Do not enable repeated scans until you have checked endpoint costs and set an account-level budget.
- **Spotify:** Development-mode apps require the app owner to have Spotify Premium and are limited to five allowlisted authenticated users. Spotify Web API listener-account data is not the Spotify for Artists dashboard; it does not return monthly listeners or full artist analytics.
- **Bluesky:** Public AppView discovery is the easiest no-credential live source in this build.
- **Mastodon:** Search of statuses depends on the instance's search configuration; a successful connection does not guarantee full-text status search on every server.
- **SoundCloud:** Creating an API application requires SoundCloud Artist Pro. OAuth 2.1 uses PKCE, tokens expire after about one hour and refresh tokens are single-use.

### Private-access requirement

The local backend binds to `127.0.0.1`; do not change it to `0.0.0.0`, publish a tunnel or expose it to the public internet yet. The current local MVP is not a remotely authenticated multi-user service. Before using a public HTTPS callback or remote hosting, add private workspace authentication / access proxy, CSRF protections, HTTPS, audit logging and a managed secret store. In particular, do not expose OAuth callbacks and token-status endpoints through an unprotected public tunnel.

## Release 1.1 — additive endpoints

The `services/` layer adds analytics and drafting endpoints on top of the connections above. Scope note: YouTube retention reporting (`POST /api/youtube/retention`) uses the connected Google account's OAuth token and requires the YouTube Analytics API with the `yt-analytics.readonly` scope (already requested by the v1 YouTube connection). GitHub statistics read the public `tapasadvisory/tapas-growth-autopilot` repository and need no token; an optional `GITHUB_TOKEN` with push access additionally enables traffic metrics — without it, traffic is reported as `unconfigured`, never estimated. Keyword research reports `search_volume: null` because no volume provider is connected. Live SEO data requires a Google Search Console API integration, which is not configured; `GET /api/search/seo/status` reports that requirement explicitly.
