# ADR-0015: Relative URLs, so Dropwatch works in a subfolder without a base-path setting

**Status:** Proposed

## Context

Issue #5 asked for reverse-proxy setups in a subfolder (`example.com/dropwatch/`) as well as on a
subdomain. Every URL the page used started at the site root (`/api/...`, `/assets/...`, `/favicon.ico`,
the manifest's `start_url` and icons, `/api/img/...` from `images.py`), so behind a subfolder the browser
asked the proxy for `example.com/api/...`, which belongs to something else.

Two ways to fix it:

1. **Relative URLs, and the proxy strips the folder.** The build uses `base: "./"`, the page asks for
   `api/...`, and the proxy maps `/dropwatch/` to the container's `/`. No new setting.
2. **A `DROPWATCH_BASE_PATH` variable.** The server mounts everything under the prefix and writes
   `<base href>` into `index.html`. Works with proxies that pass the folder through, at the cost of a new
   variable, a templated page and tests at both the root and a prefix.

## Decision

Option 1. The page already routes by hash (`#settings/proxy`), so the document's own path is the only
base it needs. The same image works at the root and under any folder, and every common proxy (nginx and
SWAG, Nginx Proxy Manager's Advanced tab, Caddy's `handle_path`, Traefik's `stripPrefix`) can strip a
folder. `index.html` adds the trailing slash when it's missing (`/dropwatch` would otherwise resolve
`api/...` against the root).

## Consequences

- The proxy must strip the folder. A proxy that passes `/dropwatch/api/state` through unchanged gets the
  page instead of the API; the guide's examples all strip.
- Deep paths such as `/foo/bar` were never used by the page but used to load it; now they get a trailing
  slash and relative links that point under `/foo/bar/`, so they no longer work. The root and hash links
  are unaffected.
- The session cookie keeps `Path=/`, so in a subfolder it is sent to the whole site. A subfolder also
  shares an origin with every other app on that name, which can then call Dropwatch's API with the
  visitor's cookie: the guide recommends a subdomain and says why.
- Option 2 stays possible later, on top of this, if someone needs a proxy that can't strip.

## Evidence

`web/vite.config.ts`, `web/index.html`, `web/public/manifest.webmanifest`, `web/src/api/client.ts`,
`web/src/api/live.ts`, `src/dropwatch/images.py`, `docs/guides/reverse-proxy.md`. Checked end to end
behind nginx 1.24 at `/dropwatch/` and on a subdomain: setup, sign-in, the API, the event stream and
the assets all load, with no failed requests.
