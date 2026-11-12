# Tapas Growth Autopilot — v1.7 owned-channel distribution (review branch)

## What changed

**Real authorized platform publishing, not a click counter.** This patch extends the existing approval queue and worker with:
- Threads text publishing (Meta Threads create + publish).
- Instagram Professional **image** publishing (Meta container + media_publish).
- YouTube owner video upload (Data API resumable session).
- Existing LinkedIn member-text and X publishing remains unchanged.
- Gemini cross-platform drafts now include Threads and a YouTube description.
- Distribution planner accepts Threads and Instagram.

These are **live API call implementations** but were tested offline with mocked provider responses. They require your own approved developer application, actual permissions and authorized accounts before they can publish. No social content has been posted.

## Existing approval and worker controls

Use the existing \`POST /api/approvals\` endpoint to create a \`publish_post\` proposal for one platform and the existing \`POST /api/approvals/{id}/action\` endpoint to approve it. Only **approved** items are executed by the existing auto-publish worker; the admin can inspect status using \`GET /api/autopublish/status\`. Start with \`AUTO_PUBLISH_DRY_RUN=true\` and verify readiness. Do not expose the current local-only API publicly without adding application authentication and access controls.

Duplicate-publication protection (added on this branch after review): YouTube uploads use the resumable protocol with session-status recovery, and on any worker retry (attempt 2+) the adapters first check the account's recent posts/media/uploads for an exact match and adopt that result instead of publishing again. A retry after a lost acknowledgement therefore resolves to the original post rather than a duplicate.

## Configure provider permissions

Set these only on the backend, never in a repository:

| Platform | Configure | Required granted scope | Payload requirement |
|---|---|---|---|
| LinkedIn | Existing LinkedIn OAuth | \`w_member_social\` | \`{"text":"..."}\` |
| X | Existing X OAuth and API credits | \`tweet.write\` (add via \`X_EXTRA_SCOPES\`) | \`{"text":"..."}\` |
| Threads | \`THREADS_APP_ID\`, \`THREADS_APP_SECRET\`; register redirect URL \`/api/oauth/threads/callback\` | \`threads_basic threads_content_publish\` | \`{"text":"..."}\` |
| Instagram | Existing \`META_APP_ID\`, \`META_APP_SECRET\` | \`instagram_business_content_publish\` (add via \`META_EXTRA_SCOPES\`) | \`{"text":"caption","media":{"image_url":"https://your-approved-cdn.example/image.jpg"}}\` |
| YouTube | Existing Google OAuth credentials | \`https://www.googleapis.com/auth/youtube.upload\` (add via \`GOOGLE_EXTRA_SCOPES\`) | \`{"text":"Video title","media":{"video_path":"/your/media/clip.mp4","title":"Video title","description":"...", "privacy":"private"}}\` |

Add \`TAPAS_MEDIA_HOSTS\` containing the exact authorized CDN hostnames for Instagram, and \`TAPAS_MEDIA_ROOT\` as the absolute local media directory for YouTube. Never place secrets, OAuth tokens, mobile sessions or browser cookies in GitHub.

The OAuth callback stores granted scopes where returned by the provider. If a provider does not expose scopes, readiness stays **blocked** rather than assuming a successful authorization. Also implemented on this branch after review: Instagram container status polling before media_publish, YouTube resumable-session recovery, retry dedupe checks, and the Threads long-lived token exchange (th_exchange_token at connect, th_refresh_token on refresh). Live-account validation is still required before a production rollout.

## Example: propose an owned-channel publication (DO NOT EXECUTE until reviewed)

\`\`\`json
{
  "action_type": "publish_post",
  "platform": "threads",
  "title": "Approved transformation insight",
  "payload": {"text": "CHANGEReadyX™: operational readiness before go-live."},
  "proposed_by": "Tapas Advisory",
  "risk_level": "Medium"
}
\`\`\`

The user must review and approve the exact post, destination and action through the application's approval queue. The backend will only dispatch the post after approval.

## Tests

\`\`\`bash
python -m unittest test_owned_channel_publisher_v17 -v
python -m unittest test_v15_autopublish test_publication_orchestrator_v16 -v
\`\`\`

Tests use mocked HTTP calls and do not publish to social media.

## What this does *not* do

It does not generate traffic, impersonate users, extract/replay cookies, automate likes, manufacture views, or purchase advertisements. Reaching audiences beyond owned accounts requires an approved paid advertising or opt-in audience-distribution workflow. A Google Ads/Meta Ads campaign connector is a separate implementation and needs an ad account, campaign objectives, targeting, budgets, and explicit approvals.

### Known limitations

This patch does not implement a verified social analytics sync for the new channels, a Meta Ads or Google Ads campaign creation workflow, Instagram Reels publishing, YouTube Shorts classification, multi-user mobile authentication, or production-safe hosting. The existing application remains a local/private MVP.
