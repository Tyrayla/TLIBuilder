---
name: deploy-web
description: Deploy TLI Builder's web build to Cloudflare Pages — either the app (tlibuilder.com, project "tlibuilder") or the reference-data CDN (tlibuilder-data.pages.dev, project "tlibuilder-data"). Use for a manual/local deploy (pre-release testing, or as a fallback if the deploy-web.yml / deploy-web-data.yml GitHub Actions workflows are down). Covers the fetch-data → build → wrangler deploy → verify sequence and its known gotchas. Publishes live — confirm with the owner before running the actual deploy step.
---

# deploy-web

Two independent Cloudflare Pages projects, both under account `7ca006edeffe5f31f4899364ecd94085`
("Tyrayla@gmail.com's Account"). Don't confuse them — wrong `--project-name`/output-dir pairing
silently deploys the wrong build to the wrong site:

| Project | Serves | Output dir | npm script | Auto-deploys via |
|---|---|---|---|---|
| `tlibuilder` | tlibuilder.com / www / tlibuilder.pages.dev — the app itself | `dist-web/` | `deploy:web` | `.github/workflows/deploy-web.yml` on push to `main` |
| `tlibuilder-data` | tlibuilder-data.pages.dev — season catalogs + engine-data.zip (a separate CDN the app's Pyodide worker reads from) | `web-data/` | `deploy:web:data` | Nothing automatic — `.github/workflows/deploy-web-data.yml` is `workflow_dispatch` only |

`tlibuilder-data` is deliberately **not** wired to any push trigger: a season data refresh happens
in the private `tli-data` repo, which this repo has no way to observe, and it's a genuinely
different event from an app-code release (docs/BACKLOG.md §7). Redeploy it by hand (or via
`gh workflow run deploy-web-data.yml`) whenever the fetched `data/` actually changed.

## Before running an actual deploy — ask first

This publishes live, immediately, to a real domain people use. Treat it like any other
hard-to-reverse, externally-visible action: **confirm with the owner before running the deploy
step** (the build steps before it are free to run/inspect). The one exception is when the ask
itself *is* "run the deploy" / "ship this to the web" — that's already the authorization.

## Automated path (normal case)

Pushing to `main` deploys the app automatically — nothing to do. `deploy-web.yml`: checks out,
sets up Python 3.12 + Node 20, `npm ci`, fetches private game data (`TLI_DATA_TOKEN`), runs
`npm run build:web`, deploys via `cloudflare/wrangler-action` (`CLOUDFLARE_API_TOKEN`), then
polls production with `scripts/verify-web-deploy.mjs` so the job fails loudly if the live site
never picks up the new build instead of reporting green on a silent no-op.

**One-time owner setup required for CI to authenticate** (not something an agent can do): create a
Cloudflare API token scoped to `Account > Cloudflare Pages > Edit` for this account, then add it
as the `CLOUDFLARE_API_TOKEN` secret in the GitHub repo's Settings → Secrets → Actions. Without
it, `deploy-web.yml`/`deploy-web-data.yml` fail at the wrangler-action step.

For the data CDN: trigger manually — `gh workflow run deploy-web-data.yml` or the Actions tab.

## Manual/local path (fallback, or pre-release testing)

```
npm run deploy:web          # app: fetch:data -> build:web -> wrangler pages deploy dist-web -> verify
npm run deploy:web:data     # data CDN: fetch:data -> build:web:data -> wrangler pages deploy web-data -> verify
```

Each collapses into one command:
1. `node scripts/fetch-data.mjs` — pulls the private `tli-data` repo's `data/` into the checkout.
   Needs `TLI_DATA_TOKEN`/`GH_TOKEN` env or local git credentials with access to the private repo.
2. The matching build step (`npm run build:web` or `build:web:data`).
3. `wrangler pages deploy <dir> --project-name=<project>`.
4. `node scripts/verify-web-deploy.mjs` — polls the live URL until it reflects the new build (see
   Gotcha 2 below) instead of trusting `wrangler`'s immediate "done" and finding out later it
   hadn't actually propagated.

`wrangler` is a devDependency (`npm ci` installs it) — no ad hoc `npm install wrangler` needed.
First local use needs `npx wrangler login` (opens a browser OAuth flow) unless
`CLOUDFLARE_API_TOKEN` is already set in the environment; check with `npx wrangler whoami`.

## Gotchas

1. **`python` on PATH is shell-dependent on Windows, not just machine-dependent.** `npm run
   build:web` shells out to `python` directly. It resolves fine from a normal PowerShell prompt,
   but running the same `npm run` command through a git-bash-style shell (e.g. an agent's Bash
   tool) can fail with `'python' is not recognized` even though a direct `python --version` in
   that same shell works — `npm run` on Windows spawns its own `cmd.exe` subshell to execute the
   script, which resolves PATH independently of the invoking shell (confirmed reproducing this
   2026-09-08: `python --version` succeeded via the Bash tool, but `npm run build:web` in the same
   session still failed to find `python`, and succeeded immediately when run from PowerShell
   instead). **If `npm run build:web`/`build:web:data` reports `python` not found, retry from
   PowerShell before concluding Python itself is missing.** GitHub Actions runners don't hit this
   at all — `actions/setup-python` puts `python` on PATH for every shell the job uses.
2. **Custom-domain propagation lags the `pages.dev` deployment by up to ~a minute.** `wrangler
   pages deployment list` shows a fresh deploy as Production immediately, but tlibuilder.com /
   tlibuilder-data.pages.dev's edge cache can keep serving the previous build for a short window
   after. Don't conclude a deploy failed from an immediate manual check — `verify-web-deploy.mjs`
   already retries for 90s by default; if it still times out, then check `wrangler pages
   deployment list` for a genuine failure.
3. **No `wrangler.toml` exists on purpose.** Both `--project-name` and the output directory are
   passed explicitly on every command (npm scripts, both workflows) rather than inferred from a
   root config that would ambiguously serve two different Pages projects from one repo.
