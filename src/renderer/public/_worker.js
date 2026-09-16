// Cloudflare Pages advanced-mode Worker for the main tlibuilder.com app.
//
// Its only job beyond plain static-asset serving: for a share-link path (/b/<id>), inject real
// Open Graph / Twitter meta tags into the served HTML *before* any JavaScript runs, so Discord/
// Twitter/etc.'s link-preview crawlers (which do not execute JS) see a real title/description/
// image instead of an empty SPA shell. The actual interactive page (gear/skills/hero-trait, with
// real tooltips) is rendered client-side by view.html's own React app (src/renderer/src/view/
// ViewApp.tsx) exactly as it would be without this worker — this only touches the <head> of the
// initial HTML response.
//
// The share service (api.tlibuilder.com) still never renders or decodes anything — this worker
// only reads the small, already-validated `preview` JSON it stores (see that service's
// PreviewPayload) and echoes a few of its fields into meta tags, HTML-escaped here as
// defense-in-depth alongside that service's own input-side validation.

const SHARE_BASE = 'https://api.tlibuilder.com';

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function round(n) {
  return Math.round(Number(n) || 0).toLocaleString('en-US');
}

function buildMetaHtml(id, preview, pageUrl) {
  const title = `${preview.hero} — ${preview.trait}, Lv ${preview.level} | TLI Builder`;
  const sign = preview.movement_speed >= 0 ? '+' : '';
  const description =
    `Life ${round(preview.max_life)} · Mana ${round(preview.max_mana)} · ES ${round(preview.max_energy_shield)} · ` +
    `DPS ${round(preview.total_dps)} · Res ${Math.round(preview.fire_resist)}/${Math.round(preview.cold_resist)}/` +
    `${Math.round(preview.lightning_resist)}/${Math.round(preview.erosion_resist)}% · ` +
    `Move Speed ${sign}${Math.round(preview.movement_speed)}%`;

  const t = escapeHtml(title);
  const d = escapeHtml(description);
  const u = escapeHtml(pageUrl);
  // icon_url is optional (see the share service's PreviewPayload) — a hero-trait record not yet
  // rehosted to the CDN has none. Omit the image tags entirely rather than emitting a broken
  // og:image pointing at the literal string "null"/"undefined".
  const img = preview.icon_url ? escapeHtml(preview.icon_url) : null;

  return `
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="TLI Builder">
    <meta property="og:title" content="${t}">
    <meta property="og:description" content="${d}">
    <meta property="og:url" content="${u}">
    ${img ? `<meta property="og:image" content="${img}">` : ''}
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="${t}">
    <meta name="twitter:description" content="${d}">
    ${img ? `<meta name="twitter:image" content="${img}">` : ''}
  `;
}

class HeadInjector {
  constructor(html) {
    this.html = html;
  }
  element(el) {
    el.append(this.html, { html: true });
  }
}

async function handleShareLink(request, env, id) {
  // Request the clean path, NOT /view.html directly — Cloudflare Pages' default clean-URL asset
  // handling 308-redirects a direct .html request to the extensionless path instead of serving it,
  // so fetching '/view.html' here returned a redirect response (no <head> to rewrite, and no
  // meta tags ever reached a real visitor) rather than the page. '/view' resolves straight to
  // view.html's content with no redirect. Confirmed via a local `wrangler pages dev` run.
  const assetUrl = new URL('/view', request.url);
  const assetResponse = await env.ASSETS.fetch(new Request(assetUrl, request));

  // No preview (unknown id, older client that couldn't compute one, or the share service being
  // briefly unreachable) — serve the plain page. The client-side app still renders normally; it
  // just won't get a rich embed. Never treat this as an error at the worker level.
  const preview = await fetch(`${SHARE_BASE}/b/${encodeURIComponent(id)}/preview`)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  if (!preview) return assetResponse;

  const metaHtml = buildMetaHtml(id, preview, request.url);
  const rewriter = new HTMLRewriter().on('head', new HeadInjector(metaHtml));
  return rewriter.transform(assetResponse);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/b\/([A-Za-z0-9_-]+)\/?$/);
    if (match && request.method === 'GET') {
      return handleShareLink(request, env, match[1]);
    }
    return env.ASSETS.fetch(request);
  },
};
