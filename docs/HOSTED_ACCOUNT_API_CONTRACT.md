# Hosted account API contract (proposal)

Status: proposal for review. The app code in this branch targets this contract. The hosted service
(`tlibuilder-code-share`) does not implement it yet. Nothing here claims a live endpoint.

The product decisions are in [HOSTED_ACCOUNT_PLATFORM_PLAN.md](HOSTED_ACCOUNT_PLATFORM_PLAN.md). This file only fixes the wire shape so the app and the service can be built and tested separately.

## Conventions

- Base URL: the share service origin (`https://api.tlibuilder.com`, overridable for local testing).
- Bodies and responses are JSON. The service stores and returns `tli1_` codes verbatim. It never runs the engine.
- Errors use one shape: `{"error": {"code": "<stable_code>", "message": "<text for developers>"}}`.
- The user is always taken from the verified session. No endpoint accepts a user ID from the client.
- Every private resource query is scoped to the session's user. A resource owned by another account answers `404`, never `403`, so IDs cannot be probed.
- Time values are integer Unix seconds, matching the existing PostgreSQL schema.

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `unauthenticated` | Missing, expired, revoked or rotated-out session. |
| 403 | `csrf_failed` | Cookie session without a valid `X-CSRF-Token`. |
| 403 | `signup_required` | The session exists but sign-up is not complete. Every other `/v1` route refuses until `POST /v1/account/signup`. |
| 403 | `reauth_required` | Export or delete without a Discord sign-in in the last 10 minutes. |
| 404 | `not_found` | Unknown, or owned by another account. |
| 409 | `stale_revision` | `base_revision_id` is no longer current. Body carries `current_revision_id`. |
| 409 | `cloud_quota_reached` | The account already has 20 cloud builds. |
| 409 | `profile_quota_reached` | The profile already shows 10 builds. |
| 409 | `slug_taken` | The handle and slug pair is in use or permanently retired. |
| 413 | `code_too_large` | Over 100 KiB encoded or 1,000,000 bytes decoded (owner decision 2026-10-05). |
| 422 | `invalid_code` | Not a valid `tli1_` code. |
| 422 | `name_too_long` | Build name over 50 characters. |
| 422 | `invalid_handle` / `invalid_slug` | Fails the documented character rules or is reserved. |
| 429 | `rate_limited` | Per-IP, per-account or global limit. |

## Additions confirmed by the service

The service branch (`tlibuilder-code-share` draft PR 1, `docs/ACCOUNT_API.md`) implements this contract and adds the following. The app mirrors each point.

- `GET /v1/csrf` needs a live session (pending or complete); without one it answers `401`.
- A pending session gets `403 signup_required` on every other `/v1` route. `POST /v1/account/signup` answers `201 {user_id, public_name}`, or `403 signup_closed` while sign-up is closed.
- Sign-out, sign-out everywhere, and every `DELETE` answer `204` with no body.
- Web sign-in failures redirect to the web app with `?auth_error=<cancelled|discord_failed|signup_closed|reauth_failed>`. Desktop failures go to `http://127.0.0.1:<port>/callback?error=<reason>`. The app's listener accepts that form and ends the wait.
- More codes: `invalid_name` 422, `name_unavailable` 409, `handle_limit_reached` 409, `already_registered` 409, `invalid_grant` 400, `invalid_state` 400, `invalid_request` 400 (unknown or malformed field), `busy` 503.
- `data_version` and `app_version` must match `[A-Za-z0-9._+-]{1,64}`. The app sends a cleaned form (`toWireVersion`) of the season name and app version, and applies the same cleaning to both sides of a data-version comparison.
- `GET /u/{name}-{tag}` returns the public profile `{owner, builds[]}`. The app does not use it yet. `/u` redirects are `301` with a relative `Location`. Removed links answer `410 removed_by_owner`.
- The service accepts at most 1,000,000 decoded bytes (the frozen codec port's guard). The owner accepted this on 2026-10-05 and the plan now says so.
- Composition reports: at most 300 entities, 200 relations, and 32 mechanics; an `Authorization` header answers `400`.

## Sign-in

### Web

1. The browser navigates to `GET /auth/discord/start?client=web`.
2. The service sets a signed short-lived `state` cookie and redirects to Discord.
3. `GET /auth/discord/callback` verifies `state`, exchanges the code, reads the Discord user ID, discards the Discord token, creates the user if needed, sets the session cookie, and redirects to the web app origin.
4. The session cookie is `Secure; HttpOnly; SameSite=Lax; Path=/` on the API host. State-changing requests carry `X-CSRF-Token`, obtained from `GET /v1/csrf`.
5. CORS allows credentials only for the exact web app origins. Anonymous share and analytics routes are never sent with credentials.

### Desktop

1. The app opens `GET /auth/discord/start?client=desktop&port=<1024-65535>&code_challenge=<S256 challenge>` in the system browser. The app's loopback listener is bound to `127.0.0.1:<port>`.
2. After the same callback, the service redirects the browser to `http://127.0.0.1:<port>/callback?login_code=<code>`. The code is single use and expires after 60 seconds.
3. The app calls `POST /auth/desktop/exchange` with `{"login_code", "code_verifier"}`. The service checks the verifier against the stored challenge and returns `{"session_token", "expires_at"}`.
4. The app keeps the token in Electron `safeStorage` in the main process. The renderer never receives it. Requests send `Authorization: Bearer <token>`.

The service rejects a desktop start request whose port is below 1024 or whose host is anything other than `127.0.0.1`.

### Sessions

`GET /v1/account` returns the current account or `401`. `POST /v1/account/sessions/refresh` is not needed: the service rotates the token after 24 hours of use and answers with a replacement in `X-TLI-Session-Token` (desktop) or a new cookie (web). The previous token works for a short grace period.

- `POST /v1/account/signout` revokes the current session.
- `POST /v1/account/signout-everywhere` revokes every session for the account.

## Account

`GET /v1/account` returns:

```json
{
  "user_id": "usr_...",
  "public_name": {"name": "Tyra", "tag": "4472"},
  "limits": {"cloud_builds": 20, "profile_builds": 10},
  "usage": {"cloud_builds": 3, "profile_builds": 1}
}
```

Sign-up creates the account only after the user confirms the public name:

- `GET /v1/account/signup` (session in a `pending` state) returns `{"suggested_name": "<discord username>"}` and the resulting public name preview.
- `POST /v1/account/signup` with `{"name": "Tyra"}` creates the account and assigns the tag.
- `POST /v1/account/handle` with `{"name": "NewName"}` renames. The previous handle keeps redirecting to the current one and is never reassigned.

## Cloud builds

```text
GET    /v1/cloud/builds                 list the signed-in user's builds
POST   /v1/cloud/builds                 create a build, or report a content match
GET    /v1/cloud/builds/{id}            read the current revision (code included)
GET    /v1/cloud/builds/{id}/revisions/{revision_id}   read a referenced revision
PUT    /v1/cloud/builds/{id}            upload a new revision (conditional)
DELETE /v1/cloud/builds/{id}            delete the build and its named link
```

Responses wrap the summary: list answers `{"builds": [summary, ...]}`; create, put, and read answer `{"summary": summary}` (read adds `"code"`); `PUT .../link` answers `{"named_link": {...}}`. A pending signup (`GET /v1/account/signup`) answers `{"suggested_name", "preview": {"name", "tag"}}`, or `404` when none is pending.

Summary object:

```json
{
  "cloud_build_id": "cb_...",
  "name": "Fire Mage",
  "current_revision_id": "rev_...",
  "semantic_hash": "<64 hex>",
  "updated_at": 1700000000,
  "data_version": "season-9",
  "named_link": null
}
```

`named_link` is `null` or `{"url_path": "/u/tyra-4472/fire-mage", "slug": "fire-mage", "listed": false, "revision_id": "rev_..."}`.

`POST /v1/cloud/builds` body: `{"name", "code", "data_version", "app_version", "allow_duplicate": false}`.

- No existing build in the account has the same `semantic_hash`: create the build in a transaction that enforces the 20-build limit. Response `201` with the summary and the `revision`.
- A match exists and `allow_duplicate` is false: create nothing and answer `200 {"match": {"cloud_build_id", "name"}}`.
- `allow_duplicate` is true: create a separate build. It counts against the limit.

`PUT /v1/cloud/builds/{id}` body: `{"base_revision_id", "name", "code", "data_version", "app_version"}`.

- The write succeeds only when `base_revision_id` is still current, including after the user confirmed an overwrite. Otherwise `409 stale_revision`.
- A code with the same `semantic_hash` as the current revision creates no revision and answers `200` with the unchanged summary.

`GET /v1/cloud/builds/{id}` returns `{"summary": {...}, "code": "tli1_..."}`.

### Semantic hash

`semantic_hash` is the lowercase hex SHA-256 of this canonical text: the decoded top-level JSON object of the code with `id`, `createdAt` and `updatedAt` removed, keys sorted at every depth, compact separators (`,` and `:`), UTF-8 with no ASCII escaping, and integer-valued numbers written without a fraction part. `name` and `notes` stay. Arrays keep their order. The service computes it from the decoded code through its existing validation interface. The app computes the same value in `utils/sync.ts`. A mismatch between the two shows up as a false "local changes" status, so both sides carry a shared test vector.

## Named links

```text
PUT    /v1/cloud/builds/{id}/link       create or change the link
DELETE /v1/cloud/builds/{id}/link       remove the link (keeps a content-free tombstone)
GET    /u/{handle}/{slug}               public read, direct-link only
```

`PUT` body (all optional; the first call creates the link):

```json
{"slug": "fire-mage", "listed": false, "revision_id": "rev_..."}
```

- `listed: true` is rejected with `409 profile_quota_reached` when the profile already shows 10 builds. The check and the change run in one transaction.
- `revision_id` moves the link to that revision. The app only sends it from **Update shared link** after the user confirms. A normal cloud save never moves a link.
- Renaming the slug leaves a permanent redirect from the old slug.

`GET /u/{handle}/{slug}` answers the build code for the selected revision as JSON `{"name", "code", "data_version", "owner": {"name", "tag"}}`, or a redirect to the current handle or slug, or `410 {"error": {"code": "removed_by_owner"}}`. Responses carry `X-Robots-Tag: noindex`.

## Privacy

```text
POST   /v1/account/reauth                start a fresh Discord confirmation for export or delete
GET    /v1/account/export                full export (requires reauth within 10 minutes)
DELETE /v1/account                       delete the account (requires reauth within 10 minutes)
```

`POST /v1/account/reauth` (no body) returns `{"authorize_url": "<start URL>"}`, bound to the current session through the OAuth `state`. The app opens it (system browser on desktop). Open question for the owner: Discord cannot force a password or second-factor prompt, so what this step proves (a fresh interaction by the account's own Discord identity) must be explained plainly and security-reviewed. The app copy says "confirm with Discord" and makes no claim about a password or MFA. After the Discord callback the service sets the session's `reauth_at` and redirects the browser to the web app origin with `?reauth=ok`, for web and desktop alike (there is no loopback step). The desktop app cannot observe that redirect, so it shows a "Continue" button that retries the export or delete once the user has finished in the browser. Export and delete answer `403 reauth_required` outside the 10-minute window. Deletion revokes every session, removes the account, builds and links from production, and keeps only content-free handle and slug records.

## Anonymous build-composition statistics

```text
POST /v1/stats/composition
```

Sent with `credentials: omit` and no `Authorization` header. The body is exactly:

```json
{
  "data_version": "season-9",
  "entities": [{"type": "support", "id": "support_added_fire"}],
  "relations": [{"skill_id": "skill_x", "support_id": "support_y"}],
  "mechanics": ["minion"]
}
```

The service validates every ID against a catalog-ID pattern and a per-request count, increments daily aggregate counters in the `analytics` database only, and answers `204`. It stores no raw event, no request IP, and no identifier. The analytics writer role has no access to `core`.

### How the app derives each field

The app sends the report after a successful, changed calculation, once per distinct composition per session. Turning the Privacy switch off stops new reports and aborts any report still in flight. Nothing is queued on disk.

| Field | Source |
| --- | --- |
| `entities` | Catalog item IDs in the saved build: hero trait, active and passive skills, supports, legendary items and slots, crafted base types, pact spirits, core talents, slates, prisms. Each ID must match the catalog-ID pattern or it is dropped. A crafted item's own ID is never sent, only its base type. |
| `relations` | Each enabled skill with each enabled support socketed in it. |
| `mechanics` | Only these eight flags, each proven by a field of the engine's calculation result for any equipped active skill: `spell_burst` (`spell_burst_count > 0`), `tangle` (`tangle_count > 0`), `shadow_strike` (`shadow_count > 0`), `channeling` (`channeled_max_stacks > 0`), `trigger` (`trigger_interval > 0`, an activation medium), `damage_over_time` (a damage row of kind `dot`), `minion` (a modeled minion owner), `reservation` (a skill sealing mana or life). No tag guessing and no text matching. |
| Hero Memory | `hero_memory` is `<type>_<rarity>`. `memory_base_stat` is the catalog `uuid` of the base stat; the memory creator rewrites the stat's value for the memory level, so the app matches the stat's name within the memory's own type and requires exactly one catalog uuid. `memory_revival` is the catalog name of a named (tier 0) revival mod, lower-cased with non-alphanumerics replaced by `_` (for example `furious_roar`). The modifier text, rolled value, and description are never sent. |

Limits that mean the data is incomplete, not wrong:

- `damage_over_time` covers skill damage-over-time rows only. Ailment damage over time (for example Ignite) has no engine field the app reads for this flag, so it is not counted.
- A tiered revival mod has no catalog identifier (80 revival rows: 44 named tier-0 mods and 36 tiered effect-text rows, none with a `uuid`). The app does not report tiered revival choices.
- Fixed and random memory affixes are not reported; the plan names base and revival choices only.

New entity types `memory_base_stat` and `memory_revival` must be in the service's allowlist before a build that reports them ships, because an unknown type answers `400` and drops the whole report.
