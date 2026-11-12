# Tapas Content Amplifier — independent GitHub starter

This package is a standalone, dependency-free Python application that can be added as
an `amplifier/` folder to `tapasadvisory/tapas-growth-autopilot`.
It is **not** a verified patch against the repository's v1.6.0 source; review compatibility before merging.

## Features

- Responsive desktop/mobile dashboard.
- LinkedIn, YouTube, Instagram, Threads and X HTTPS content registry.
- Campaign goals, post registration, tenant separation and roles.
- Administrator login, password hashing, server-side sessions, HttpOnly cookies and CSRF protection.
- Manually recorded metrics are explicitly **unverified**.
- Outbound clicks are tracked as **opens**, never represented as views.
- Links open on the user's device; their existing browser/app authentication may be reused locally.

## Quick start — no pip install needed

From the repository root, where `amplifier/` exists:

```bash
export AMPLIFIER_ADMIN_EMAIL='you@example.com'
export AMPLIFIER_ADMIN_PASSWORD='Use-A-Strong-Unique-Password-Here!'
export AMPLIFIER_SECURE_COOKIES=0
python -m amplifier
```

Open http://127.0.0.1:8765. The initial administrator is created only on the
first start of a new SQLite database.

For Docker, copy `amplifier/.env.example` to `amplifier/.env`, set a unique password,
then run `cd amplifier && docker compose up --build`.

For public production access, use an HTTPS reverse proxy, set
`AMPLIFIER_SECURE_COOKIES=1`, restrict network access and perform a full security review.

## Tests

From the repository root:

```bash
python -m unittest discover -s amplifier/tests -v
```

## Integration with the existing repository

1. Create a feature branch, e.g. `feature/tapas-content-amplifier`.
2. Extract the ZIP into the cloned repository root without overwriting files.
3. Run tests and inspect the `amplifier/` folder.
4. Connect this independent service to the existing app through a reverse proxy or
   navigation link after reviewing actual v1.6.0 routes and deployment configuration.
5. Open a pull request. No GitHub push or automatic merge has been performed.

## API

- `POST /api/login` — sign in (returns session cookie and CSRF token).
- `GET /api/me` — current account and CSRF token.
- `GET /api/platforms` — platforms and integration state.
- `GET|POST /api/campaigns` — campaign registry.
- `GET|POST /api/assets` — validated social content registry.
- `POST /api/metrics` — manual, explicitly unverified entry.
- `GET /api/stats` — campaign, asset and outbound open summary.
- `POST /api/workspaces` — superadmin creates another tenant and admin.
- `GET /out/{asset_id}` — authenticated redirect to the existing HTTPS social post.
- `POST /api/logout` — revoke session.

Authenticated POST calls require the `X-CSRF-Token` header.
The browser UI handles this.

## Deliberately not implemented

Official OAuth connectors, AI content generation, social publishing and
platform-reported analytics require credentials and approved API access.
No browser/mobile social cookies are extracted, shared, replayed or injected.
No likes, views, subscriptions or comments are artificially generated.

This is a functional starter, **not production-certified**. Audit logs,
external identity-provider integration, distributed rate limiting, advanced
moderation, and complete enterprise controls require additional work.
