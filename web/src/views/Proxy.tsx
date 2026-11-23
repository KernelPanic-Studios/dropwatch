import { useEffect, useState } from "react";
import { api, type ProxyInfo } from "../api/client";
import { useApp } from "../store";
import { Icon } from "../ui/Icons";

/** Settings › Proxy (issue #5). Read-only: both settings are the container's variables, read at start.
 * Says whether the request came through a proxy and whether Dropwatch trusts it, and fills the example
 * configs in docs/guides/reverse-proxy.md with this server's own name, folder and address. */
export function ProxySettings() {
  const { sayError } = useApp();
  const [info, setInfo] = useState<ProxyInfo | null | undefined>(undefined);  // null: couldn't read it
  const [kind, setKind] = useState<ProxyKind>("nginx");
  useEffect(() => { api.get<ProxyInfo>("/proxy").then(setInfo).catch(() => setInfo(null)); }, []);
  if (info === undefined) return null;
  if (info === null) return <div className="opt"><div className="d">Couldn't read the proxy settings from the miner.</div></div>;

  const via = info.proxy_trusted !== null;
  const folder = pageFolder(location.pathname);
  const name = info.host_is_local ? "" : hostOnly(info.host);
  const target: SnippetTarget = {
    name: name || PLACEHOLDER,
    folder,
    // opened directly by address: that's where the proxy should point
    upstream: !via && info.host_is_local && !folder ? withPort(info.host) : "SERVER_IP:5800",
  };
  const snippet = proxySnippet(kind, target);
  async function copy() {
    try { await navigator.clipboard.writeText(snippet); } catch (e) { sayError(e, "Couldn't copy"); }
  }

  return (
    <>
      <div className="opt"><div>
        <div>{via ? "Opened through a reverse proxy" : "Opened directly, without a proxy"}</div>
        <div className="d">{info.scheme}://{info.host}{folder}
          {info.prefix && info.prefix !== folder.replace(/\/$/, "") ? ` · the proxy says its folder is ${info.prefix}` : ""}</div>
      </div></div>
      {via && (info.proxy_trusted ? (
        <div className="opt"><div className="add-note ok"><Icon name="check" />
          <span>The proxy is trusted, so Dropwatch sees each visitor's own address (yours is <span className="tt">{info.client}</span>).</span></div></div>
      ) : (
        <div className="opt"><div>
          <div className="add-note warn"><Icon name="alert" /><span>The proxy at <span className="tt">{info.client}</span> isn't trusted.</span></div>
          <div className="d">Every visitor looks like the proxy, so five wrong passwords through it lock everyone out for 15 minutes.
            Set <span className="tt">FORWARDED_ALLOW_IPS={info.client}</span> on the container and restart.</div>
        </div></div>
      ))}
      <div className="opt"><div>
        <div>Public names <span className="tt d">DROPWATCH_HOSTS</span></div>
        <div className="d">{info.hosts.length ? `${info.hosts.join(", ")}.` : "None listed."} IP addresses and local names like tower or tower.local always work.</div>
      </div></div>
      <div className="opt"><div>
        <div>Trusted proxies <span className="tt d">FORWARDED_ALLOW_IPS</span></div>
        <div className="d">{info.trusted.length ? info.trusted.join(", ") : "None set. Only a proxy on the same machine (127.0.0.1) is trusted."}</div>
      </div></div>
      <div className="opt"><div className="d">Both are the container's settings, read when it starts. Change them in the container
        (on Unraid: Edit, then Show more settings) and restart. You can always open Dropwatch by its IP address to check them.</div></div>
      <div className="sub">Example config</div>
      <div className="opt proxy-ex">
        <div className="seg" role="group" aria-label="Reverse proxy">
          {KINDS.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}>{label}</button>
          ))}
        </div>
        <button className="btn" type="button" onClick={() => void copy()}><Icon name="copy" />Copy</button>
        <pre className="snippet" aria-label={`${KINDS.find(([k]) => k === kind)![1]} example`}><code>{snippet}</code></pre>
        <div className="d">
          {folder ? `For a subfolder at ${folder}. A subdomain is safer: in a subfolder, every other app on this name shares Dropwatch's origin. ` : "For a subdomain. "}
          {placeholders(target, snippet).length ? `Replace ${placeholders(target, snippet).join(" and ")} with your own.` : "Filled in with this server's name and address."}
          {" "}More in the <a className="link" href="https://github.com/KernelPanic-Studios/dropwatch/blob/main/docs/guides/reverse-proxy.md" target="_blank" rel="noreferrer">reverse proxy guide</a>.
        </div>
      </div>
    </>
  );
}

export type ProxyKind = "nginx" | "npm" | "caddy" | "traefik";
const KINDS: [ProxyKind, string][] = [["nginx", "nginx / SWAG"], ["npm", "Nginx Proxy Manager"], ["caddy", "Caddy"], ["traefik", "Traefik"]];
export type SnippetTarget = { name: string; folder: string; upstream: string };

/** The folder the page is served from: "" at the root, "/dropwatch/" in a subfolder. */
export function pageFolder(pathname: string): string {
  const dir = pathname.slice(0, pathname.lastIndexOf("/") + 1);
  return dir === "/" ? "" : dir;
}
const PLACEHOLDER = "dropwatch.example.com";
const placeholders = (t: SnippetTarget, snippet: string) =>
  [snippet.includes("example.com") && (t.folder ? "example.com" : PLACEHOLDER), t.upstream.startsWith("SERVER_IP") && "SERVER_IP"]
    .filter((x): x is string => !!x);
const hostOnly = (host: string) => (host.startsWith("[") ? host.slice(0, host.indexOf("]") + 1) : host.split(":")[0]!);
const withPort = (host: string) => (/:\d+$/.test(host) ? host : `${host}:80`);

const NGINX_HEADERS = `proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_http_version 1.1;
proxy_buffering off;           # live updates
proxy_read_timeout 1h;`;
const indent = (text: string, n: number) => text.split("\n").map((l) => " ".repeat(n) + l).join("\n");

/** One proxy's config for this server, as in docs/guides/reverse-proxy.md. In a subfolder the proxy strips
 * the folder (Dropwatch's links are relative) and sends the bare folder on to the one with a slash. */
export function proxySnippet(kind: ProxyKind, { name, folder, upstream }: SnippetTarget): string {
  const f = folder.replace(/\/$/, "");  // "/dropwatch"
  const site = folder && name === PLACEHOLDER ? "example.com" : name;  // a folder sits on a site's own name
  if (kind === "nginx") {
    const loc = folder
      ? `location = ${f} { return 301 ${f}/; }\nlocation ${f}/ {\n    proxy_pass http://${upstream}/;   # the slash strips ${f}\n${indent(NGINX_HEADERS, 4)}\n}`
      : `location / {\n    proxy_pass http://${upstream};\n${indent(NGINX_HEADERS, 4)}\n}`;
    return `server {\n    listen 443 ssl;\n    server_name ${site};\n\n${indent(loc, 4)}\n}`;
  }
  if (kind === "npm") {
    if (!folder) {
      return `# Proxy Host: domain ${name}, scheme http, forward to ${upstream.replace(":", " port ")}\n`
        + `# SSL: request a certificate, Force SSL on. Websockets Support: off.\n# Advanced tab:\nproxy_buffering off;\nproxy_read_timeout 1h;`;
    }
    return `# Proxy Host for ${site} (it can already serve something else at /).\n# Advanced tab:\n`
      + `location = ${f} { return 301 ${f}/; }\nlocation ${f}/ {\n    proxy_pass http://${upstream}/;\n${indent(NGINX_HEADERS, 4)}\n}`;
  }
  if (kind === "caddy") {
    return folder
      ? `${site} {\n    redir ${f} ${f}/\n    handle_path ${f}/* {\n        reverse_proxy ${upstream} {\n            flush_interval -1\n        }\n    }\n}`
      : `${name} {\n    reverse_proxy ${upstream} {\n        flush_interval -1\n    }\n}`;
  }
  const lines = [
    "traefik.enable=true",
    `traefik.http.routers.dropwatch.rule=Host(\`${site}\`)${folder ? ` && PathPrefix(\`${f}\`)` : ""}`,
    "traefik.http.routers.dropwatch.entrypoints=websecure",
    "traefik.http.routers.dropwatch.tls.certresolver=le",
    ...(folder ? [`traefik.http.middlewares.dropwatch-strip.stripprefix.prefixes=${f}`,
      "traefik.http.routers.dropwatch.middlewares=dropwatch-strip"] : []),
    "traefik.http.services.dropwatch.loadbalancer.server.port=5800",  // the container's own port
  ];
  return lines.join("\n");
}
