# Guides

For people who run Dropwatch. Read against `main` at `687d794` (2026-11-15). Screen names are the page's
own, in bold; menus are written **Settings › Backup**.

## Setting up

- [installation.md](installation.md): Unraid, plain Docker, a PC, and putting it behind a reverse proxy.
- [reverse-proxy.md](reverse-proxy.md): example configs for SWAG, nginx, Nginx Proxy Manager, Caddy and
  Traefik, on a subdomain or in a subfolder.
- [twitch-sign-in.md](twitch-sign-in.md): the page password, the Twitch code, and what happens when Twitch
  ends the session.
- [configuration.md](configuration.md): every screen in Settings, every setting with its default, and
  every environment variable.
- [mining.md](mining.md): how Dropwatch picks what to mine, Priority, Never, favourites, pins, Needs you,
  and channel points.
- [storage-and-backups.md](storage-and-backups.md): where every file lives, what a backup carries, and
  restoring.
- [updating.md](updating.md): tags, pinning a version, the copy made before an upgrade, and rolling back.

## Integrations

- [notifications.md](notifications.md): Discord, Telegram, ntfy, Slack, Pushover, Gotify and webhooks,
  what each alert means, and how to connect each service.

## For developers

- [../architecture.md](../architecture.md): the codebase map.
- [../architecture/README.md](../architecture/README.md): diagrams, findings and the reference
  architecture.
- [../development.md](../development.md): running it locally, tests, releasing.
