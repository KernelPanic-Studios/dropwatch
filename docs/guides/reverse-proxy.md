# Reverse proxy

How to open Dropwatch through a reverse proxy such as SWAG, Nginx Proxy Manager, Caddy or Traefik, so it
gets HTTPS and a name like `dropwatch.example.com`. You don't need any of this to use Dropwatch on your
home network: IP addresses and local names like `tower` or `tower.local` always work.

**Settings › Proxy** in the app shows what Dropwatch sees from the proxy, warns when something is missing,
and fills these examples in with your own address.

## What every setup needs

1. **The public name in `DROPWATCH_HOSTS`.** Dropwatch refuses names it doesn't know, so a web page
   elsewhere can't reach it through DNS rebinding. Set `DROPWATCH_HOSTS=dropwatch.example.com`
   (comma-separated for several). Without it the page says
   `Dropwatch doesn't answer to the name '...' unless it's listed`.
2. **The proxy's address in `FORWARDED_ALLOW_IPS`.** For example `172.18.0.5`, or the Docker network
   `172.18.0.0/16` when the proxy is another container. Without it every visitor looks like the proxy,
   and five wrong passwords through the proxy lock everyone out for 15 minutes.
3. **No buffering on `/api/events`.** Live updates are server-sent events. Dropwatch sends
   `X-Accel-Buffering: no`, which nginx honours; the examples below turn buffering off anyway. Keep the
   read timeout long (an hour is plenty: Dropwatch sends a keepalive every 15 seconds).
4. **Restart the container** after changing either variable. On Unraid both are under **Show more
   settings** in the container's template.

The examples use `SERVER_IP:5800`: your server's address and Dropwatch's Web UI port. If the proxy runs
in Docker on the same custom network as Dropwatch, use the container name instead (`dropwatch:5800`).
WebSockets aren't used, so no upgrade headers are needed.

## Subdomain (recommended)

`https://dropwatch.example.com/`

### nginx and SWAG

For SWAG, save this as `/config/nginx/proxy-confs/dropwatch.subdomain.conf` and restart SWAG.

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name dropwatch.*;

    include /config/nginx/ssl.conf;   # SWAG only: plain nginx uses its own ssl_certificate lines

    location / {
        proxy_pass http://SERVER_IP:5800;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_buffering off;           # live updates
        proxy_read_timeout 1h;
    }
}
```

### Nginx Proxy Manager

1. **Hosts › Proxy Hosts › Add Proxy Host.** Domain `dropwatch.example.com`, scheme `http`, forward
   host `SERVER_IP`, port `5800`. Leave **Websockets Support** off.
2. **SSL:** request a certificate and turn on **Force SSL**.
3. **Advanced**, in the custom configuration box:

   ```nginx
   proxy_buffering off;
   proxy_read_timeout 1h;
   ```

### Caddy

```caddy
dropwatch.example.com {
    reverse_proxy SERVER_IP:5800 {
        flush_interval -1
    }
}
```

Caddy sets `X-Forwarded-For` and `X-Forwarded-Proto` by itself.

### Traefik

Labels on the Dropwatch container (Traefik v2 or v3, with a `websecure` entry point and a certificate
resolver called `le`):

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.dropwatch.rule=Host(`dropwatch.example.com`)
  - traefik.http.routers.dropwatch.entrypoints=websecure
  - traefik.http.routers.dropwatch.tls.certresolver=le
  - traefik.http.services.dropwatch.loadbalancer.server.port=5800
```

Traefik streams server-sent events without extra settings.

## Subfolder

`https://example.com/dropwatch/`

The proxy has to **strip the folder**: Dropwatch's own links are relative, so it expects requests at `/`.
The examples below also send `/dropwatch` on to `/dropwatch/` (the page does this too, as a fallback).
Set `DROPWATCH_HOSTS` to the site's name, here `example.com`.

**A subdomain is the safer choice.** In a subfolder, Dropwatch shares its origin with every other app on
`example.com`, so a page from any of them can call Dropwatch's API with your session. Use a subfolder only
when you trust everything else served on that name.

### nginx and SWAG

For SWAG, save the `location` blocks as `/config/nginx/proxy-confs/dropwatch.subfolder.conf`.

```nginx
location = /dropwatch { return 301 /dropwatch/; }
location /dropwatch/ {
    proxy_pass http://SERVER_IP:5800/;   # the trailing slash strips /dropwatch
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_read_timeout 1h;
}
```

### Nginx Proxy Manager

Open the proxy host for `example.com` and paste the same two `location` blocks into its **Advanced** tab.
Use the Advanced tab rather than **Custom Locations**, so that the folder is stripped exactly as above.

### Caddy

```caddy
example.com {
    redir /dropwatch /dropwatch/
    handle_path /dropwatch/* {
        reverse_proxy SERVER_IP:5800 {
            flush_interval -1
        }
    }
}
```

### Traefik

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.dropwatch.rule=Host(`example.com`) && PathPrefix(`/dropwatch`)
  - traefik.http.routers.dropwatch.entrypoints=websecure
  - traefik.http.routers.dropwatch.tls.certresolver=le
  - traefik.http.middlewares.dropwatch-strip.stripprefix.prefixes=/dropwatch
  - traefik.http.routers.dropwatch.middlewares=dropwatch-strip
  - traefik.http.services.dropwatch.loadbalancer.server.port=5800
```

## Checking it

Open **Settings › Proxy** through the proxy. It should say **Opened through a reverse proxy** and
**The proxy is trusted**. If it says the proxy isn't trusted, set `FORWARDED_ALLOW_IPS` to the address it
shows and restart. The section also has these examples filled in with your own name and folder.

The nginx subdomain and subfolder examples were checked end to end against nginx 1.24. The others follow
each proxy's documented options.
