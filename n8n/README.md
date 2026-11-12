# n8n integration: TAPAS REA observation workflow

This integration adds **n8n as the deterministic workflow automation layer**, alongside Muse (AI coordination) and the existing FastAPI publication/analytics backend.

## Architecture
- **Muse**: research and AI-assisted hypotheses, content improvements and operator coordination.
- **REA Intelligence Engine**: experiments and evidence-based recommendations (a separate future module; not created by this workflow).
- **n8n**: scheduling, collecting existing backend status and saved analytics observations, operational handoffs.
- **Existing TAPAS backend**: OAuth tokens, approvals, publishing decisions and their audit logs.
- **Postiz (optional, not connected by this PR)**: publishing only after a separate approved integration exists.

**No change to existing publishing controls is introduced by this PR.**

## Functional deliverable

Import `n8n/workflows/rea_observation_workflow.json` into an n8n instance. Every 30 minutes, after you activate it, it:
1. GETs `/api/autopublish/status` from the TAPAS backend.
2. GETs `/api/analytics/snapshots` from the TAPAS backend.
3. Produces an REA observation JSON record inside n8n's execution history.

The record distinguishes available platform snapshots from real confirmed views and impressions; no growth is claimed from queue executions or click counts. The workflow is **inactive by default** and only performs GET requests. It does not create approvals, publish posts, like/comment, manipulate views or use social session cookies.

## Quick local connection (Windows / Mac)

1. Start the existing TAPAS backend locally and check `http://127.0.0.1:8000/api/health`.
2. Install or start a **local n8n instance on the same machine**; follow the [official n8n self-hosting guide](https://docs.n8n.io/hosting/).
3. In n8n, use **Import from File** and choose `n8n/workflows/rea_observation_workflow.json`.
4. Confirm the two HTTP Request nodes point to your backend's local address and run **Execute workflow**.
5. Check the `Create REA observation` output. Activate the workflow only after inspecting the output and ensuring that n8n is appropriately access-controlled.

**Docker warning:** Inside an n8n container, `127.0.0.1` refers to the n8n container, **not** the TAPAS backend running on the host. Use a private, approved network path; do **not** expose the current unauthenticated TAPAS backend to the public internet just to connect Docker. A host-network configuration on a trusted Linux machine or co-located native execution can keep the backend private. Where appropriate, deploy a properly authenticated internal API gateway instead.

## Production safety requirements

- The present TAPAS backend is a local/private MVP and its analytics/status APIs are not production authenticated. Do not publish these endpoints to the public internet.
- Protect n8n accounts, workflow editor, stored executions and credentials; n8n execution logs may contain analytics details.
- Keep secrets in n8n credentials or private server settings, never workflow JSON or GitHub.
- The existing `PUBLICATION_EVENTS_WEBHOOK_URL` can notify a receiving service on publication. A direct n8n receiver must **verify the `X-TAPAS-Signature` HMAC over the exact request body** before routing the event; this PR intentionally does not create an unverified public webhook.
- Do not let workflows execute external social publishing unless exact content, destination account, visibility and approval are confirmed.
- Use the existing approval queue as the single source of truth for publication; an n8n trigger is not approval.
- Verify rate limits and license/hosting costs before rollout.

## To extend this toward actual amplification

The first functional workflow reports baseline performance. A later, separately reviewed release can add:
1. Content intake and REA hypothesis generation.
2. Draft generation and an **approval queue**, not autonomous public posting.
3. Approved publisher handoff through authorized connectors (Postiz or direct APIs).
4. Platform-reported reach and conversions as feedback; comparison with control groups and baseline.
5. Additional opt-in open feed and community distribution, without fake engagement or cookie replay.

**Status:** Importable workflow + offline contract tests provided. This PR does **not** establish a live n8n connection or claim verified audience growth.
