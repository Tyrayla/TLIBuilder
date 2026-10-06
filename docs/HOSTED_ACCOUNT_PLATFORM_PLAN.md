# Hosted accounts, storage, and analytics plan

> Status: in progress. Migration steps 1–7 are complete (see [Progress](#progress)). Steps 8–11 are partly built on the app side (see [Implementation progress, steps 8–11](#implementation-progress-steps-811)); nothing is deployed and sign-up is closed. This document records product decisions. Deployment runbooks live in the `tlibuilder-code-share` repository (`deployment/DOKPLOY.md`, `deployment/RESTORE.md`).

## Progress

Last updated 2026-10-04.

| Step | Status | Notes |
| --- | --- | --- |
| 1. Inspect servers | Done | Old 2 GB US server: systemd + Caddy, SQLite in WAL mode, 3.2 GB unbounded journal, backups only on the same disk. |
| 2. Select the panel | Done: **Dokploy** | Chosen over Coolify for its lower overhead on 4 GB and its Compose-first model. Dokploy's panel uses about 1 GB of RAM; re-measure its steady state and cap it if it keeps growing. |
| 3. Move to the 4 GB server | Done | `2.28.108.8` (Falkenstein), rebuilt clean on Ubuntu 24.04, Hetzner firewall (ICMP, 22, 80, 443 only), journald capped at 256 MiB, Docker logs to journald, 2 GB swap, automatic security updates. `api` and `admin` DNS moved; all 54 shares verified. The old server and its snapshot are deleted. |
| 4. Provision PostgreSQL | Done | PostgreSQL 18, database `core` (schemas `sharing`, `reports`), roles `tli_migrator` / `tli_app` / `tli_backup`, bounded pool, versioned migrations in a one-shot `migrate` container, no published port, no SQL in logs. The `analytics` database comes with step 10. |
| 5. Encrypted R2 backup | Done | `pg_dump` every 15 minutes → `age` (public key only on the server) → R2 bucket `tlibuilder-backups`; tiered prefixes with matching lifecycle rules and bucket locks; failure alerts to Discord. A delete attempt by the server's own credential is refused. Restore-tested twice with the owner's key. |
| 6. Migrate share and report records | Done | 54 shares and 7 reports imported with IDs preserved and every row verified by hash; all 54 live links match the pre-migration copy. |
| 7. Ship the PostgreSQL service | Done | Live since 2026-10-04 (code-share `prod` `ab7a91c`). The SQLite files stay in the `tli-data` volume for the rollback window; then remove the one-time import bridge and delete the volume. |
| 8–11. Accounts, sync flows, analytics, privacy | In progress (app side) | Audited 2026-10-05: the service had no account, cloud, or analytics code and the app had none either. App-side work is on `Tyrayla/hosted-account-platform` (draft PR #9); the service side is a paired task. See below. |

### Implementation progress, steps 8–11

Last updated 2026-10-05. "Built" means code and tests exist on the task branch. It does not mean deployed, reviewed by the owner, or proven against the live service.

| Area | State | Proof so far | Remaining |
| --- | --- | --- | --- |
| Wire contract | Proposed, [API contract](HOSTED_ACCOUNT_API_CONTRACT.md) and [hash vectors](HOSTED_ACCOUNT_HASH_VECTORS.json) | The service worker confirmed the contract points and wrote 19 vectors; the app canonicalizer passes all 19. | Owner review; the service implements it. |
| Sync decisions (status, upload, download, link, conflict, 50-character name) | Built | Unit tests against an in-memory service that follows the contract: no silent overwrite, conditional writes after confirmation, unchanged upload makes no revision, link-or-new prompt, other-account records unusable. | Live-service run. |
| Sync records | Built | Desktop file in the main process and a separate IndexedDB database on web; records hold only the five sync fields. | A desktop app-harness run. |
| Desktop sign-in | Built, **not proven against Discord** | Loopback listener, PKCE, `safeStorage` vault with no plaintext fallback, and an allow-listed request bridge, all tested with fakes. | Real Discord OAuth on a staging service; security review. |
| Web sign-in | Built, **not proven against Discord** | Cookie plus CSRF client tested with fakes; a Playwright journey drives the UI against a mock service. | Real OAuth; exact-origin CORS and cookie behavior on the live origin. |
| Account, cloud library, named-link, export and delete screens | Built | Component tests; delete and export retry after a fresh Discord sign-in. Playwright (web, mock service) and Electron (real app) journeys pass. | Owner copy review; the public profile page (a service route; the app does not render it yet). |
| Guest privacy | Built | A browser or desktop install that never signed in sends no account request. Playwright asserts no request to the service when Settings opens; the desktop bridge answers `401` itself. | Live-service run. |
| Named-link import and data-version warning | Built | Named-link URLs import without a sync record; imports and cloud downloads name the saved game data version; a removed link says it was removed by its owner. Unit tests. | Live-service run. |
| 50-character build names | Built | The save inputs stop at 50; the upload flow asks before shortening an older longer name. | |
| Anonymous composition statistics (app side) | Built | Extractor and reporter tests: canonical IDs only, no user text, opt-out stops all network calls, reports only after a changed successful calculation. | The service counters and the separate `analytics` database. Curated mechanic-flag list and Hero Memory base and revival choices need owner input. |
| Account service metrics | Not started | | Service side. |
| Privacy notice | Not started | The Privacy settings section carries plain-language copy for the owner to review. | The owner writes the notice from a template. No legal sign-off is claimed. |
| Service: accounts, sessions, cloud builds, named links, analytics, export and delete | Not started | A service worker has a paired branch and proved that its validator accepts schema v2 codes without codec edits. | Everything in steps 8–11 on the service. |

Open limits of the app side:

- A local build linked under one account that is uploaded by another account on the same device replaces the first account's link record for that build. The cloud builds are untouched.
- The semantic hash is computed on the client from the decoded code, so a hash mismatch between app and service would show as a false "Local changes" status. The shared vectors guard against this.

Decisions and findings during implementation:

- **Security fix (bug-310):** the old server answered admin routes on the non-proxied API host and trusted a client-supplied Cloudflare identity header. Fixed on the old server, then carried into the Traefik labels: no `/admin` on the API host, `Cf-Access-*` headers stripped, admin host reachable only from Cloudflare's IP ranges. Log review showed no misuse. Still open: validate the signed Access token in the app (see [Security and data-integrity rules](#security-and-data-integrity-rules)).
- **Cloudflare SSL mode is Full, not strict.** The admin host has no publicly trusted origin certificate because Access blocks the HTTP-01 challenge. Next: install a Cloudflare Origin Certificate, then switch to Full (strict).
- **Branch model (code-share):** `prod` is exactly what runs; Dokploy deploys only `prod`, with autodeploy off. Work happens on `dev`; a release merges `dev` into `prod`, then Deploy.
- **Backup interval** stays at 15 minutes for now; the owner considers hourly acceptable and may revisit.
- **Integer Unix-second timestamps** are kept in PostgreSQL; a switch to `timestamptz` would be its own migration.
- **Release safety lessons:** copy live SQLite with the backup API, never `cp`; an import that opens SQLite immutable must refuse an unmerged `-wal`; compare migrated rows by key, never by position, because SQLite and PostgreSQL collate text differently (bug-311).
- **Follow-ups:** `offsite-backup` waits for `migrate` (committed on `dev` as `1e7e197`, not yet released); add an explicit column allowlist to `ReportStore.insert`; re-check PostgreSQL's 256 MB limit before accounts launch.

## Purpose

Add optional accounts to TLI Builder without changing the offline-first use of the desktop or web app. An account adds cloud copies of builds, a small public profile, and ownership of future reports or in-game test submissions.

The hosted service must protect user builds against a VPS failure. It must also collect a small set of product statistics without building profiles of players.

## Product decisions

| Area | Decision |
| --- | --- |
| Sign-in | Discord OAuth is the first sign-in method. Sign-in is optional. An account has no recovery path without the same Discord account at launch. |
| Guest use | A guest can calculate, import, export, create an anonymous share link, and view public builds. No account is required. |
| Cloud library | An account can store at most 20 cloud-synced builds. |
| Public profile | An account can display at most 10 cloud builds on its profile. The 10 builds are part of the 20-cloud-build limit. |
| Named links | A cloud build can have a stable named link such as `/u/<handle>/<slug>`. A named link can be unlisted or visible on the profile. The owner updates its selected revision explicitly. |
| Existing share links | Existing random `/b/<id>` links remain anonymous and immutable. They do not gain an owner, become mutable, or disappear when an account is deleted. |
| Sync | Upload, download, create a named link, and update a named link are explicit actions. The app does not silently overwrite a local, cloud, or linked build. |
| Anonymous build statistics | The app reports aggregate build composition by default. The user can disable this in Privacy settings. The stream has no account, Discord, installation, cookie, or device identifier. |
| Account analytics | The service records the account activity needed for cloud storage, quotas, security, and coarse service metrics. It does not join this data with anonymous build-composition statistics. |

## User experience

### Guest builds

Local desktop saves and web IndexedDB saves remain the source of truth for a guest. A guest can use every calculation feature and can create the existing anonymous share links. A network outage does not block local work.

### Account builds

When a signed-in user selects **Upload to cloud**, the service creates or updates a cloud build. The cloud library is private by default. A private cloud build has no public URL and only its signed-in owner can read it. The app shows the last uploaded revision and warns before replacing a divergent local or cloud revision.

The first release stores the current cloud revision and revisions referenced by a live named link. It does not retain an unbounded revision history. The service can remove an old revision when it is neither current nor referenced by a named link.

### Local sync records

The app must know which cloud build, and which revision of it, each local build came from. It keeps this in a separate local **sync record**, not in the build itself:

```text
sync_record
  local_build_id     the local build's id
  account_user_id    the internal user ID that owns the cloud build
  cloud_build_id     the cloud build
  base_revision_id   the cloud revision this local copy was last uploaded as or downloaded from
  base_semantic_hash the semantic hash of that revision
```

The desktop app stores sync records next to its local build saves. The web app stores them in a separate IndexedDB object store. Keeping sync state outside the `Build` object means it can never enter a `tli1_` share code, an export, or the semantic hash, and it needs no change to the frozen build-code path.

Sync records follow these rules:

- **Upload or download** creates or updates the record with the new `base_revision_id` and hash.
- **Duplicate** creates a local build with no sync record. A copy is a new build until the user uploads it.
- **Import** from a share code, a named link, or a file creates a build with no sync record.
- **Local delete** removes the sync record. The cloud build remains until the user deletes it.
- **Sign-out or account switch** hides records that belong to another `account_user_id`. The app never uploads a local build to an account that did not create its sync record.
- **Change detection:** the app compares the local build's semantic hash with `base_semantic_hash` to detect *unsynced local changes*. It compares `base_revision_id` with the cloud build's current revision to detect *newer cloud revision*. When both are true, the build has diverged.

### Sync status and the conflict screen

Sync status is passive. Opening, editing, and saving a build locally never shows a sync prompt, even when a newer cloud revision exists. The app shows status only as a small indicator in the build library and the build header, such as *Not uploaded*, *Local changes*, *Newer version in cloud*, or *Diverged*. The app does not check sync status in the background while the user works on a build; it reads cloud revision IDs when the build library opens and when the user starts a sync action.

The conflict screen appears only when the user starts an explicit sync action on a diverged build: **Upload to cloud**, **Download from cloud**, or **Update shared link**. It shows the local and cloud versions side by side with the build name, saved date, hero, and main skill, and offers three choices:

- **Keep both** (the highlighted default) saves the cloud revision as a new local build with no sync record attached. The original local build keeps its changes and its sync record, and the action stops.
- **Keep local** uploads the local build as the new cloud revision.
- **Keep cloud** replaces the local build with the cloud revision.

**Keep local** and **Keep cloud** each require a second confirmation that names what will be replaced. A later release can add a per-section difference list to this screen.

The service calculates a `semantic_build_hash` from decoded build content after removing technical persistence fields such as `id`, `createdAt`, and `updatedAt`. A name and notes remain part of the hash. Uploading a linked build whose semantic content matches its cloud build's current revision creates no new revision.

The service never links a local build to a cloud build on its own. When a local build without a sync record matches the semantic hash of a build already in the account library, the service creates nothing and returns the matching cloud build's ID and display name. The app then asks the user to choose:

- **Link to *<name>*** creates a sync record that points at the existing cloud build. No slot is used.
- **Upload as a new build** repeats the upload with an explicit `allow_duplicate` flag. The service creates a separate cloud build, which uses a slot.
- **Cancel** changes nothing.

This prevents a silent link that a later upload could turn into an overwrite of the original cloud build. For example, a user duplicates a build locally, uploads the identical copy, edits the copy, and uploads again. With a silent link, the second upload would replace the original.

### Public names and handles

Every account has a public name made of a **name** and a four-digit **tag**, displayed as `Tyra#4472`. Two people who both choose "Tyra" become `Tyra#4472` and `Tyra#0918`. The name does not need to be unique; the name and tag together do.

- **Name:** 2–24 characters from `a–z`, `A–Z`, `0–9`, `_`, and `.`. The name keeps its letter case for display, but uniqueness and URLs ignore case, so `Tyra#4472` and `tyra#4472` are the same handle. The service rejects reserved names such as `admin`, `api`, `support`, `tli`, `tlibuilder`, `settings`, `login`, and `help`.
- **Tag:** a random number from `0001` to `9999`, assigned by the service and never chosen by the user. When all tags for a name are in use, the service asks the user to choose a different name.
- **URL form:** `/u/<name>-<tag>/<slug>`, for example `/u/tyra-4472/fire-mage`, all lowercase. A name cannot contain `-`, so the final `-NNNN` is always the tag. The URL avoids `#`, because a browser treats everything after `#` as a page fragment and never sends it to the server.

At sign-up, the service suggests the Discord username as the name and shows the resulting public name before the account is created. The user can change the name at that point. The public name is visible to anyone who opens a named link or profile, so the sign-up screen states that it is public and that it does not need to match the Discord username.

**Renaming.** The user can change the name later. The service keeps the existing tag when `<new name>#<tag>` is free and otherwise assigns a new tag. Every previous handle permanently redirects to the current one and can never be claimed by another account, so a link posted anywhere never shows a different person's builds. Additional sign-in providers do not change this scheme; a handle belongs to the TLI Builder account, not to Discord.

### Named links and profile visibility

The owner can create a named link for a cloud build. The link has the form `/u/<name>-<tag>/<slug>`. The owner can enter a slug or let the service generate one. A slug uses 1–48 characters from `a–z`, `0–9`, and `-`, with no leading or trailing `-`. The link slug and the build's display name are separate values. Renaming a slug leaves a permanent redirect from the old slug.

A named link is unlisted by default. An unlisted link works for anyone who has the URL, but it does not appear on the owner's profile. The owner can show the link on their profile. The service rejects that change when the profile already displays 10 builds. There is no pinned state in the first release.

The named URL points to the build revision that the owner selected. The owner uses **Update shared link** in TLI Builder to select a newer local or cloud revision and confirm the update. The service then moves the existing named URL to that revision. A normal local or cloud save never changes a named URL. Existing anonymous short links continue to return their original immutable content.

Profile and named-link pages allow direct access but are not indexed by search engines. The first release has no public profile directory, site search, or sitemap.

### Deleting a cloud build

Deleting a cloud build that has a named link deletes both in one confirmed action. The confirmation names the link that will stop working, for example "`/u/tyra-4472/fire-mage` will stop working for anyone who has it." The service keeps a content-free record of the removed handle and slug. A visitor to the removed link sees "This build was removed by its owner" instead of a generic not-found page, and the slug cannot be reused for a different build. Deleting the account keeps the same content-free records for its handles, which keeps them unclaimable.

### Builds saved under older game data

Each revision records the data version it was saved under. When the app opens a cloud build, a named link, or an imported build that was saved under a different data version, it opens the build with the current data and shows a warning that names the saved version and says that some items, talents, or effects may have changed. Missing items follow the importer's existing unknown-item behavior. The first release does not load older datasets. A later versioned-data release can replace this behavior.

## Deployment platform

Run the hosted service in containers on the 4 GB Hetzner server. Use either self-hosted Dokploy or self-hosted Coolify. Both provide application deployment, Docker Compose, database, TLS, log, and resource-management functions without a platform license fee.

Keep the TLI service definition, environment-variable names, health checks, resource limits, and backup job in a versioned Docker Compose file in the service repository. The deployment panel manages that definition. The Compose file remains the recovery path if the panel is removed or replaced.

Do not select a platform from a feature list alone. Test the current anonymous service, PostgreSQL, the backup job, and the panel's own services together on the 4 GB server. Record steady-state memory, disk use, restart behavior, and a restore result. Select the platform that meets the resource budget and leaves the clearest operational path for the owner.

The selected panel manages the public reverse proxy and TLS certificates. Do not run a second unmanaged Caddy or Traefik proxy on the same HTTP and HTTPS ports.

## Service and database design

Move the hosted share and report service from SQLite to PostgreSQL before accepting account-backed cloud builds. SQLite remains appropriate for the current anonymous share service, but the new service needs transactions across accounts, quotas, cloud builds, and named links.

Run one small PostgreSQL instance on the 4 GB RAM and 20 TB traffic Hetzner server. Move classwork to the 2 GB server, subject to a live resource check before the move. The hosted app, the selected deployment panel and reverse proxy, PostgreSQL, backup jobs, and restore checks share the 4 GB server.

Use two separate PostgreSQL databases on the one PostgreSQL instance, each with its own service roles. PostgreSQL cannot run a query across two databases, so the anonymous statistics cannot be joined with account data even by mistake. Inside `core`, use one schema per area:

```text
core
  accounts       users, Discord identities, sessions, cloud builds, revisions
  sharing        anonymous share codes, previews, named public links
  reports        private diagnostic reports and report notes

analytics
  usage          daily entity, relation, and mechanic counters only
```

The analytics writer connects only to the `analytics` database and has no role in `core`. The account service has no role in `analytics`. Back up `core` on the schedule in [Backup and recovery](#backup-and-recovery). Back up `analytics` once a day with a 35-day retention; losing a day of aggregate counters is acceptable.

Use versioned database migrations. Do not continue the current pattern of startup-time schema changes for the new service.

Use a bounded connection pool. Do not open an unbounded database connection for every request.

### Core records

The exact schema belongs in the implementation design. It must include these concepts:

- `users`: an internal user ID, display settings, account state, and timestamps.
- `identities`: a provider-neutral identity record with `user_id`, `provider`, and a unique `provider_subject`. Discord is the first provider. Do not treat a mutable display name as identity.
- `sessions`: hashed, revocable TLI Builder sessions. Do not keep Discord access tokens longer than the sign-in flow requires.
- `cloud_builds`: an account-owned build with its current revision, display name, semantic hash, and updated timestamp. Enforce the 20-build limit in the transaction that creates a build.
- `build_revisions`: the encoded build content, immutable revision ID, schema version, season, data digest, app version, and revision metadata.
- `handles`: every name-and-tag pair an account has used, with a pointer to the current one. Old rows redirect and are never reassigned.
- `named_links`: an owner, a unique handle-and-slug pair, profile visibility, and the selected revision. Enforce the 10-visible-link limit in the transaction that changes profile visibility. Old slugs and removed links keep content-free rows for redirects and the "removed by its owner" page.
- `shared_builds`: the existing anonymous build-code records. Preserve their IDs and immutable behavior.
- `reports`: the existing private report lifecycle and retention rules.

The frozen `tli1_` build-code format remains unchanged. The hosted service stores and returns it. It does not run the game engine or make a remote calculation authoritative.

## Discord sign-in

Use Discord OAuth for identity only. Request only the `identify` scope. Do not request `email`, `guilds`, or any other scope.

### The hosted service is the only Discord client

Register one Discord application in the Discord Developer Portal. The hosted service is a *confidential client*: it holds the Discord client secret in its server environment and is the only component that talks to Discord. The desktop app and the web app never receive the Discord client secret, a Discord authorization code, or a Discord access token. A desktop binary cannot keep a secret, because anyone can unpack it.

Register exactly one redirect URI with Discord: `https://api.tlibuilder.com/auth/discord/callback`. The desktop and web flows differ only in what happens after that callback.

### Web sign-in

1. The user selects **Continue with Discord**. The browser navigates to `/auth/discord/start?client=web`.
2. The service generates a random `state` value, stores it in a short-lived signed cookie, and redirects to Discord's authorization page.
3. Discord redirects back to the callback with a `code` and the `state`. The service rejects the request when `state` does not match.
4. The service exchanges the `code` and the client secret for a Discord access token, reads the Discord user ID, and discards the token.
5. The service finds or creates the TLI Builder user through `identities`, creates a session, sets the session cookie, and redirects to the web app.

### Desktop sign-in (system browser and loopback)

The desktop flow follows RFC 8252. It adds PKCE on the connection between the desktop app and the hosted service, because the final hand-off travels through the local machine.

1. The desktop app starts a temporary HTTP listener on `127.0.0.1` on a random free port. It generates a random `code_verifier` and computes `code_challenge = BASE64URL(SHA256(code_verifier))`.
2. The app opens the system browser at `/auth/discord/start?client=desktop&port=<port>&code_challenge=<challenge>`. It does not use an embedded Electron window, because the user cannot verify the address of an embedded window.
3. Steps 2–4 of the web flow run in the browser.
4. Instead of setting a cookie, the service creates a one-time `login_code`, stores it with the `code_challenge` and the user ID, and redirects the browser to `http://127.0.0.1:<port>/callback?login_code=<code>`. The `login_code` expires after 60 seconds and works once.
5. The desktop listener receives the `login_code`, shows a "You can close this tab" page, and stops listening.
6. The app sends the `login_code` and the original `code_verifier` to `/auth/desktop/exchange`. The service checks that the verifier hashes to the stored challenge, then returns a session token. Another program that intercepts the `login_code` cannot exchange it without the verifier.
7. The app stores the session token with Electron `safeStorage` and sends it as a bearer token. The desktop app does not use cookies.

The service accepts only loopback ports in the unprivileged range and only the `127.0.0.1` host for desktop redirects. This work belongs to the platform lane (`src/main/**`, `src/preload/**`) and the share-service lane. It requires a security review.

Account export and account deletion require a fresh Discord reauthentication within 10 minutes. Account deletion revokes every TLI Builder session.

### Sessions

| Setting | Value |
| --- | --- |
| Idle expiry | 30 days without use |
| Absolute expiry | 90 days after sign-in |
| Token rotation | every 24 hours of use; the previous token stops working after a short grace period |

The same values apply to web and desktop sessions. The service stores only a hash of each session token. Account settings include **Sign out everywhere**, which revokes every session for the account. Account export and deletion require a fresh Discord sign-in regardless of session age.

## Security and data-integrity rules

- The service derives the TLI Builder user from a verified session. A client-supplied user ID never grants access.
- Every private build, link-management, export, and deletion query scopes by the authenticated owner. Tests must prove that one account cannot read or change another account's private resources.
- Cloud writes include the immutable `base_revision_id` that the client edited. The service changes the current revision only when that ID is still current. A stale write returns `409 Conflict`. A user-confirmed overwrite still uses this conditional write.
- The service accepts at most 100 KiB of encoded `tli1_` code and at most 1 MiB after decompression. It validates the prefix, Base64, zlib stream, UTF-8 JSON, top-level object, and schema marker before storage. It does not run remote calculations.
- The service sets request, title, handle, slug, and report-field limits before storing account data. Handle and slug rules are in [Public names and handles](#public-names-and-handles). A build name is at most 50 characters. Notes have no separate limit; the build-code size limit below bounds them.
- The app's build-name field accepts at most 50 characters. A local build saved before this limit keeps its longer name and keeps working offline. When the user uploads it or creates a named link for it, the app asks for a shorter name, pre-filled with the first 50 characters. It never shortens a name without confirmation.
- A direct account-linked URL is mutable only through the owner's explicit update action. An anonymous `/b/<id>` URL never changes.
- Public titles, handles, slugs, and future public text render as text, never as HTML.
- A minimal operator tombstone can disable a public link for abuse, illegal content, or accidental disclosure. Tombstoning does not replace or edit the stored anonymous code.
- The service applies short-lived per-IP limits to anonymous requests, per-account limits to signed-in writes, and a global emergency limit. It does not retain an IP address as an analytics identifier.
- The service may derive a country code from an IP address for coarse account metrics, but it stores no raw IP address for that purpose.
- Cookie-authenticated web endpoints use exact allowed origins, credentialed CORS only for those origins, CSRF protection, and secure HTTP-only cookies. Anonymous share and analytics requests never carry account cookies.
- The reverse proxy limits accepted hosts, sends HSTS, a Content Security Policy, `frame-ancestors 'none'`, a Referrer-Policy, and `X-Content-Type-Options: nosniff`.
- The hosted service does not trust a client-supplied Cloudflare identity header for operator access. The admin host is separately protected, client identity headers are stripped at the proxy, and the app validates the signed Cloudflare Access token and audience.
- The deployment panel is a privileged control plane. Restrict its administrator access, disable public registration, use two-factor authentication where available, and keep a Compose-based recovery path that does not depend on restoring the panel first.
- Keep an inventory for the Discord secret, session and CSRF secrets, database credentials, R2 backup credential, backup decryption key, Cloudflare credentials, and deployment-panel credentials. The inventory records storage, consumers, rotation, compromise response, and disaster-recovery dependency.
- Anonymous build-composition requests send no account session cookie. The analytics service writes aggregate counters directly. It does not store a raw event queue or table.

## Backup and recovery

Cloud builds are user data. Do not accept accounts until backups and restore tests meet this section.

### Backup policy

1. Create a custom-format logical PostgreSQL `pg_dump` backup at least every 15 minutes.
2. Compress, client-side encrypt, checksum, and upload each backup to a private Cloudflare R2 bucket.
3. Keep every 15-minute backup for 48 hours. Then keep one backup per hour for 48 hours, one per day for 35 days, and one per month for 6 months.
4. Keep database data, backup staging files, PostgreSQL WAL, and system logs within explicit disk budgets.
5. Alert on a failed backup, encryption failure, upload failure, checksum mismatch, low disk space, a failed restore test, or an old latest verified offsite backup.

Cloudflare R2 is the offsite backup destination. Use it for backup objects, not for the live relational database. R2 encryption at rest does not replace client-side backup encryption. Keep recovery keys outside the VPS and outside the routine R2 credentials.

Encrypt backups with [`age`](https://age-encryption.org/). The VPS holds only the `age` public key, so it can encrypt new backups but cannot decrypt any backup. An attacker who controls the VPS cannot read past backups. The owner keeps the private key in 1Password only; there is no separate printed or removable-media copy (owner decision, 2026-10-04). The key's survival therefore depends on access to the owner's 1Password account, so the owner keeps the 1Password Emergency Kit available. Every restore test decrypts a backup with the key retrieved from 1Password.

Use R2 Bucket Locks for the backup prefixes. Give the VPS a bucket-scoped credential for backup objects only. Keep bucket-lock configuration, recovery credentials, and the backup decryption key outside the VPS. Use unique backup object names so a locked object is never overwritten.

A Bucket Lock blocks deletion until its retention period ends, so one lock rule over every backup would prevent the 15-minute backups from expiring after 48 hours. Give each retention tier its own prefix, lock rule, and lifecycle rule:

| Prefix | Written | Lock period | Lifecycle deletion |
| --- | --- | --- | --- |
| `15m/` | every backup | 48 hours | after 48 hours |
| `hourly/` | the first backup of each hour | 96 hours | after 96 hours |
| `daily/` | the first backup of each UTC day | 35 days | after 35 days |
| `monthly/` | the first backup of each UTC month | 6 months | after 6 months |

The backup job uploads each backup to every tier that it qualifies for. A backup that starts a new month is uploaded four times. Each lock period equals its lifecycle period, so no object outlives its tier and no object can be deleted early.

### Restore testing

Run a monthly restore into an isolated PostgreSQL instance. The check must verify:

- backup decryption and checksum;
- database restore success;
- migration version;
- account and build counts;
- a sample of cloud-build decodes;
- named-link lookup; and
- report retention data.

The launch recovery objective is a maximum of 15 minutes of accepted cloud-save loss and four hours to restore hosted account functions after a complete VPS failure. Revisit PostgreSQL point-in-time recovery only if that recovery point is not sufficient.

### Deletion

Account deletion removes the account, sessions, cloud builds, named links, and identifiable account activity from production. Backups retain deleted data until the applicable snapshot expires, which is at most 6 months under the retention policy. The privacy notice must state that retention period.

Anonymous shares remain after account deletion because they deliberately store no owner. Account-linked named links are removed with their cloud build or account. The content-free handle and slug records described in [Deleting a cloud build](#deleting-a-cloud-build) remain so that old links never resolve to another account.

## Logging and disk limits

Logs must help diagnose outages, abusive use, and backup failures without becoming a second database of user content.

Keep logs in systemd journald. Do not add unbounded application log files. Configure the production server with a bounded journal and verify the setting after deployment.

Containers do not log to journald by default. Docker's default `json-file` driver writes an unbounded file per container, and the journald cap does not apply to it. Set `"log-driver": "journald"` in `/etc/docker/daemon.json` so the application, PostgreSQL, the reverse proxy, and the deployment panel's own containers all write to the bounded journal. If a panel overrides the driver for its own services, set `max-size` and `max-file` on those services instead. Verify the active driver on every running container after deployment.

At launch, use these limits:

- cap journald at 256 MiB;
- retain normal operational logs for 14 to 30 days;
- retain compact security and audit records for at most 90 days;
- alert when disk use reaches 70 percent; and
- treat 85 percent disk use as urgent.

Log only the endpoint class, status code, latency, deployment revision, backup result, database result, rate-limit result, and non-sensitive error code. Do not log request bodies, build codes, report descriptions, report snapshots, session tokens, authorization headers, email addresses, Discord IDs, raw IP addresses, or full share URLs.

Configure the selected reverse proxy and PostgreSQL with bounded retention. Do not log full SQL statements or bound parameter values because they can include private build data. Monitor PostgreSQL data size, WAL size, backup staging size, journald size, and R2 upload status.

Reserve disk headroom on the 40 GB server. Initial operating budgets are:

| Storage category | Budget |
| --- | ---: |
| PostgreSQL data and indexes | 8 GiB |
| PostgreSQL WAL and temporary work | 4 GiB |
| Local backup staging | 4 GiB |
| Operating system and packages | 5 GiB |
| Container images, build cache, and panel volumes | 6 GiB |
| Journald and reverse-proxy logs | 0.25 GiB |
| Free headroom | at least 12 GiB |

Container images and build cache grow with every deployment. Build application images in CI, or schedule `docker image prune` and `docker builder prune` with an age filter so the host keeps only the current and previous images. Include the panel's own database and cache volumes in this category.

Review the budgets after observing real account and backup usage. Do not store screenshots, videos, or other large evidence attachments on this server in the first account release.

## Cost controls

The launch plan adds no required monthly service subscription. It uses the existing Hetzner VPS, the existing domain, self-hosted Dokploy or Coolify, Docker, PostgreSQL, Discord OAuth, the in-service analytics tables, and Cloudflare Web Analytics.

Cloudflare R2 is the only planned usage-priced service. Use Standard storage. Its current free allowance is 10 GB-month of storage, one million Class A operations, and ten million Class B operations each month. Backups that remain inside that allowance cost nothing. If the retained backup set exceeds it, approve the cost before changing the retention policy or adding user-uploaded files.

Do not enable a managed Dokploy or Coolify control plane, Cloudflare Workers Paid, Argo, paid rate limiting, paid WAF features, Cloudflare Observability ingestion, or another paid hosted analytics product without a recorded owner decision.

The owner has account-wide $0 budgets with **Stop usage** enabled for GitHub Actions, Codespaces, Packages, Git LFS, and AI Credit SKUs. Keep these limits. Private-repository CI can use the included GitHub Pro allowance, but paid overage must stop instead of billing. Do not rely on the current two-year GitHub Pro promotion when setting the safety limit.

Account launch does not require email. If a later release adds email login, verification, account recovery, or notifications, select and budget a transactional email provider first. Other future costs that need an explicit decision include a formal legal review and desktop code-signing certificates.

## Anonymous build-composition statistics

The purpose of these statistics is to decide which build systems need support, verification, and maintenance. The service measures reported build setups, not people, characters, or accounts.

The app reports a normalized composition only after a successful calculation and only when that composition changes during the current app session. The report contains canonical catalog IDs and a data version. It does not contain the build code or any user-generated text.

Count these entities:

- hero traits;
- active skills;
- supports, including active skill to support pairs;
- legendary items and equipped slots;
- Pact Spirits;
- Hero Memories and their relevant base or revival choices;
- Core Talents;
- Grafts, Slates, Ethereal Prisms, and other named build systems;
- crafted base types;
- curated mechanic flags such as Spell Burst, Tangle, Shadow Strike, reservation, minion, damage-over-time, trigger, and channeling; and
- canonical unsupported entities or modifier families.

Do not collect custom modifier text, notes, folders, exact rare-item rolls, full crafted-item combinations, condition values, share URLs, account IDs, Discord IDs, cookies, device identifiers, or a complete build combination.

Store aggregate tables only:

```text
daily_entity_usage
  date, data_version, entity_type, entity_id, count

daily_relation_usage
  date, data_version, skill_id, support_id, count

daily_mechanic_usage
  date, data_version, mechanic_id, count
```

The Privacy settings screen must explain the collection in plain language and allow the user to turn it off. Do not describe a persistent identifier or a hashed account ID as anonymous.

## Account service metrics

Keep account service metrics separate from anonymous build-composition statistics. These metrics answer operational questions about the hosted service:

- registered accounts;
- new accounts by period;
- daily and monthly active signed-in accounts;
- coarse country and platform category;
- cloud-build, named-link, and share counts; and
- unusual account-level activity for abuse protection.

An account activity record is personal data. Keep it only as long as it supports account service, security, quota enforcement, and aggregate reporting. Do not use it to infer gameplay choices. Do not join it with the anonymous statistics database.

Guest use does not create a TLI Builder account record. Network infrastructure can still process transient connection data for delivery and security. State that distinction plainly in the privacy notice.

The owner writes the privacy notice from a reputable template before launch. The first release has no paid legal review; the owner accepts that risk (owner decision, 2026-10-03). Anonymous build-composition reporting stays on by default, with a plain-language explanation and an off switch in Privacy settings. Revisit a paid review if the service grows substantially or adds email, payments, or other personal data.

The privacy notice must state:

- what an account stores: the Discord user ID, the public name and tag, cloud builds and named links, session records, and coarse country and platform metrics;
- why each item is stored, and that sign-in requests no email address or Discord server list;
- how long each item is kept, including the 6-month backup tail after deletion;
- that anonymous shares have no owner and remain after account deletion;
- what the anonymous build-composition statistics contain, that they cannot identify a person, and how to turn them off;
- that guest use creates no account record, and that network infrastructure still processes connection data for delivery and security; and
- how to export or delete an account.

## Migration plan

Steps 1–7 are complete; see [Progress](#progress).

1. Inspect the live 2 GB and 4 GB servers. Record memory use, disk use, service processes, reverse-proxy configuration, journal limits, existing backup jobs, and DNS settings.
2. Test self-hosted Dokploy and self-hosted Coolify against the resource budget on the 4 GB server. Select one after checking a deployment, restart, backup, and restore.
3. Move the hosted service to the 4 GB and 20 TB server. Keep the old server intact through a rollback window.
4. Provision PostgreSQL, service roles, a connection pool, versioned migrations, R2 backup credentials, and the operator-access boundary on the 4 GB server.
5. Implement encrypted R2 backup, Bucket Locks, retention, backup-age alerts, and an isolated restore test. Prove a restore before accepting account data.
6. Define and migrate the current anonymous share and report records. Preserve share IDs and validate row counts and build-code hashes.
7. Ship the PostgreSQL-backed anonymous service. Keep the SQLite files read-only until the rollback window and a successful restore test have passed.
8. Add Discord OAuth, account sessions, the 20-build cloud library, named links, and the 10-build visible-profile limit.
9. Add explicit upload, download, create-link, profile-visibility, and update-shared-link flows. Test divergent local and cloud revisions before release.
10. Add aggregate anonymous build-composition counters and account service metrics. Verify that the two data paths cannot join through an identifier.
11. Publish the privacy notice and support account export and deletion before opening sign-up.

## Launch checks

Do not open account registration until all checks pass:

- The service works as a guest without sign-in.
- The service rejects a 21st cloud build and an 11th public profile build in concurrent requests.
- A local build is not overwritten without user confirmation.
- Existing anonymous share links import correctly after migration.
- A named public build updates only after explicit confirmation.
- An unlisted named link works but does not appear on the profile.
- A user cannot access another user's private builds, named links, account export, or account deletion route.
- A stale cloud write returns a conflict and does not replace a newer revision.
- Opening, editing, and saving a build with a newer cloud revision shows only a status indicator; the conflict screen appears only after an explicit upload, download, or update-shared-link action.
- Two accounts with the same name receive different tags, a renamed handle redirects to the current one, and a previous handle cannot be claimed by another account.
- A deleted cloud build's named link shows "removed by its owner," and its slug cannot be reused.
- A build saved under a different data version opens with a warning that names the saved version.
- The service rejects a build name longer than 50 characters, and uploading an older local build with a longer name asks the user to shorten it.
- **Sign out everywhere** revokes every session, and an expired or rotated-out token is rejected.
- An unchanged semantic upload of a linked build does not create a new cloud revision.
- An unlinked upload that matches an existing cloud build creates nothing until the user chooses **Link** or **Upload as a new build**, and **Upload as a new build** counts against the 20-build limit.
- R2 receives encrypted snapshots on schedule.
- The VPS cannot decrypt a backup, and the `age` private key from 1Password decrypts one.
- An isolated restore passes the documented checks.
- The latest verified offsite backup stays inside the alert threshold.
- A replacement VPS can restore hosted account functions inside the four-hour recovery target.
- The selected self-hosted deployment panel, PostgreSQL, API, and backup job remain inside the 4 GB resource budget under normal load.
- Disk, journal, WAL, and backup staging alerts work.
- Every running container uses the journald log driver or a bounded `json-file` configuration.
- Old 15-minute, hourly, and daily backups expire on schedule, and a locked backup cannot be deleted early.
- A duplicated, imported, or other-account local build has no sync record and cannot upload over an existing cloud build.
- An intercepted desktop `login_code` cannot be exchanged without the matching `code_verifier`.
- GitHub paid-product budgets remain at $0 with **Stop usage** enabled.
- Privacy settings disable anonymous build-composition reporting.
- Anonymous aggregate rows contain no account, Discord, installation, or persistent device identifier.
- The published privacy notice covers every item listed in [Account service metrics](#account-service-metrics).
- Account deletion and export work as documented.
- Account deletion and export require a fresh Discord reauthentication.
- Public profile and named-link pages are direct-link-only and send a no-index directive.

## Open decisions

None. Every decision in this plan is recorded in its section.

## References

- Current hosted-service design: `tlibuilder-code-share/README.md`, `db.py`, `reports_db.py`, and `deployment/OPERATIONS.md`.
- [Cloudflare R2 overview](https://developers.cloudflare.com/r2/how-r2-works/), [durability](https://developers.cloudflare.com/r2/reference/durability/), and [object lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).
- [Cloudflare R2 Bucket Locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/) and [R2 access tokens](https://developers.cloudflare.com/r2/api/tokens/).
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/) and [Cloudflare Web Analytics](https://developers.cloudflare.com/web-analytics/about/).
- [Dokploy self-hosted and managed comparison](https://docs.dokploy.com/docs/core/differences) and [Coolify pricing](https://www.coolify.io/pricing).
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) and [included GitHub product usage](https://docs.github.com/en/enterprise-cloud@latest/billing/reference/product-usage-included).
- [PostgreSQL backup and restore](https://www.postgresql.org/docs/current/backup.html), [continuous archiving](https://www.postgresql.org/docs/current/continuous-archiving.html), and [server logging](https://www.postgresql.org/docs/current/runtime-config-logging.html).
- [OAuth 2.0 for Native Apps](https://www.rfc-editor.org/info/rfc8252) and [Discord OAuth2](https://docs.discord.com/developers/topics/oauth2).
- [ICO guidance on anonymisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/introduction-to-anonymisation/), [pseudonymisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/pseudonymisation/), and [data minimisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/data-minimisation/).
