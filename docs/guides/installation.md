# Installation

Dropwatch runs as one container with one volume. One container is one miner for one Twitch account. Never
run two against the same account (two containers, or a container and a PC copy): they fight over watch
progress.

## Unraid

1. Go to **Apps**, search for **Dropwatch** (by KernelPanic Studios), and click **Install**.
2. Check **Data** (default `/mnt/user/appdata/dropwatch`) and **Web UI Port** (default `5800`), then
   **Apply**. The template already sets `--restart unless-stopped` and a log size cap.
3. Open the WebUI and follow [twitch-sign-in.md](twitch-sign-in.md).

Without Community Applications, add the template once from the Unraid terminal, then pick **dropwatch** in
**Docker › Add Container › Template**:

```
wget -O /boot/config/plugins/dockerMan/templates-user/my-dropwatch.xml https://raw.githubusercontent.com/KernelPanic-Studios/dropwatch/main/unraid/dropwatch.xml
```

## Docker

```
docker run -d --name dropwatch --restart unless-stopped \
  -p 5800:5800 -v /path/to/dropwatch:/data \
  -e TZ=America/New_York \
  --log-opt max-size=10m --log-opt max-file=3 \
  ghcr.io/kernelpanic-studios/dropwatch:latest
```

- **`--restart unless-stopped` is required.** When mining crashes or stops ticking, Dropwatch exits on
  purpose so Docker starts a fresh one ([ADR-0011](../adr/0011-restart-instead-of-repair.md)). Without a
  restart policy it stays stopped.
- The image is built for `linux/amd64` only.
- Keep the container port 5800. The image's health check calls `127.0.0.1:5800`; publish a different
  host port instead (`-p 8080:5800`).

To build the image yourself, the build needs the commit it was built from:

```
docker build --build-arg DROPWATCH_COMMIT=main@$(git rev-parse --short HEAD) -t dropwatch:latest .
```

## On a PC

For development or a quick try (Python 3.12 and Node 24, see [../development.md](../development.md)):

```
uv sync
cd web && npm ci && npm run build && cd ..
uv run dropwatch serve          # http://localhost:5810
```

It listens on `127.0.0.1:5810` by default (`--host`, `--port`). Data goes to `./data` unless
`DROPWATCH_DATA` is set. There is no watchdog on a PC: nothing would restart it.

## First run

Open `http://<server>:5800`, for example `http://192.0.2.10:5800` or `http://tower:5800`. Choose a page
password, then connect Twitch with a one-time code. Both steps are in
[twitch-sign-in.md](twitch-sign-in.md). Mining starts as soon as Twitch is connected.

## Behind a reverse proxy

Dropwatch answers only to IP addresses, `localhost`, bare names such as `tower`, and private suffixes
(`.local`, `.lan`, `.home`, `.home.arpa`, `.internal`, `.localdomain`, `.localhost`). Any other name gets
`400 Dropwatch doesn't answer to the name '...' unless it's listed`. This stops a web page elsewhere from
reaching it through DNS rebinding.

For a public name such as `dropwatch.example.com`:

1. Set `DROPWATCH_HOSTS=dropwatch.example.com` (comma-separated for several).
2. Set `FORWARDED_ALLOW_IPS` to the proxy's address, for example `192.0.2.20`. Without it every visitor
   looks like the proxy, and five wrong passwords through the proxy lock everyone out for 15 minutes.
3. Let the proxy pass server-sent events through unbuffered for `/api/events` (Dropwatch sends
   `X-Accel-Buffering: no`, which nginx honours). A buffering proxy delays live updates.
4. Restart the container.

[reverse-proxy.md](reverse-proxy.md) has ready-to-paste configs for SWAG and nginx, Nginx Proxy Manager,
Caddy and Traefik, on a subdomain or in a subfolder. **Settings › Proxy** shows what Dropwatch sees from
the proxy and fills the examples in for you.

## Variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `TZ` | container | `UTC` | The server's time zone: log times and the weekly summary's default zone |
| `PUID` / `PGID` | container | `99` / `100` | The user and group the miner runs as; `/data` is chowned to them on start |
| `DROPWATCH_HOSTS` | container | empty | Public names to answer to; `*` turns the check off |
| `FORWARDED_ALLOW_IPS` | container | uvicorn's `127.0.0.1,::1` when unset | The reverse proxy's address |

The full list is in [configuration.md](configuration.md#environment-variables).

## Known limitations

- One Twitch account per container, and nothing detects a second miner on the same account.
- `linux/amd64` images only.
- The page is plain HTTP; HTTPS comes from a reverse proxy.
