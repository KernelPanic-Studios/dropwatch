# Notifications

Dropwatch can tell you when mining needs attention, through any of seven services. Set them up in
**Settings › Notifications › Where they go**, then **Send test notification**.

## The alerts

Each failure alert is sent once when it starts and once when it clears. A "working again" message only
follows an alert that was actually sent.

| Alert | On by default | When |
|---|---|---|
| Twitch sign-in stops working | Yes | Twitch ended the session; mining stopped |
| Twitch can't be reached | Yes | Checks have been failing for 15 minutes (5 to 240) |
| Mining isn't earning | Yes | 30 minutes (10 to 240) of watching with no new minutes |
| A reward couldn't be claimed | Yes | Twitch turned down a finished drop; once per reward |
| Mining stopped on an error | Yes | Something inside Dropwatch failed |
| A campaign needs you | No | A campaign's game account isn't linked; new ones only, several in one message |
| A reward is claimed | No | Each claim; several within a minute arrive as one |
| Weekly summary | No | Rewards, channel points, missed campaigns and links needed, at a chosen day and hour |

The weekly summary uses the zone you pick, or the server's (`TZ`). If Dropwatch is off at that hour it is
sent up to 6 hours late; if every service fails it is retried every 10 minutes in that window.

Every message starts with "Dropwatch: ". Activity lists where each one went (service names only).

## Services

<!-- generated:notify-catalogue -->
| Service | Type key | Fields | Page |
|---|---|---|---|
| ntfy | `ntfy` | `topic` | [ntfy](#ntfy) |
| Telegram | `telegram` | `token` (secret), `chat_id` | [Telegram](#telegram) |
| Discord | `discord` | `webhook_url` (secret) | [Discord](#discord) |
| Slack | `slack` | `webhook_url` (secret) | [Slack](#slack) |
| Pushover | `pushover` | `token` (secret), `user` (secret) | [Pushover](#pushover) |
| Gotify | `gotify` | `server`, `token` (secret) | [Gotify](#gotify) |
| Webhook | `webhook` | `url` (secret) | [Webhook](#webhook) |
<!-- /generated:notify-catalogue -->

Secret fields are never shown again once saved: the page says they are set. A backup leaves them out
unless you ask for them. They are stored in `drops.db` (readable only by the miner's user).

### ntfy

<!-- generated:notify-fields ntfy -->
| Field | Label on the page | Secret |
|---|---|---|
| `topic` | ntfy topic (e.g. dropwatch-nick-7f3a) or full URL | no |

Subscribe to the same topic in the ntfy app (Android/iOS). Pick a long, hard-to-guess topic: anyone who knows it can read your alerts.
<!-- /generated:notify-fields -->

A bare topic goes to the public ntfy server; a full URL such as `https://ntfy.example.com/dropwatch-alerts`
goes to your own.

### Telegram

<!-- generated:notify-fields telegram -->
| Field | Label on the page | Secret |
|---|---|---|
| `token` | Telegram bot token (from @BotFather) | yes |
| `chat_id` | Telegram chat ID (e.g. 123456789) | no |

Message @BotFather to create a bot and copy its token, then DM the bot and read your chat ID from api.telegram.org/bot<token>/getUpdates. Keep the token private.
<!-- /generated:notify-fields -->

### Discord

<!-- generated:notify-fields discord -->
| Field | Label on the page | Secret |
|---|---|---|
| `webhook_url` | Discord webhook URL | yes |

In Discord: Channel Settings → Integrations → Webhooks → New Webhook → Copy URL. Anyone with the URL can post there, so keep it private.
<!-- /generated:notify-fields -->

### Slack

<!-- generated:notify-fields slack -->
| Field | Label on the page | Secret |
|---|---|---|
| `webhook_url` | Slack incoming webhook URL | yes |

In Slack: create an Incoming Webhook for a channel (api.slack.com/messaging/webhooks) and paste its URL. Keep it private.
<!-- /generated:notify-fields -->

### Pushover

<!-- generated:notify-fields pushover -->
| Field | Label on the page | Secret |
|---|---|---|
| `token` | Pushover application API token | yes |
| `user` | Pushover user key | yes |

Create an application at pushover.net for the API token; your user key is on your Pushover dashboard. Get the app on iOS/Android.
<!-- /generated:notify-fields -->

### Gotify

<!-- generated:notify-fields gotify -->
| Field | Label on the page | Secret |
|---|---|---|
| `server` | Gotify server URL (e.g. https://gotify.example.com) | no |
| `token` | Gotify app token | yes |

Self-hosted Gotify: your server URL plus an application token from the Gotify apps page.
<!-- /generated:notify-fields -->

### Webhook

<!-- generated:notify-fields webhook -->
| Field | Label on the page | Secret |
|---|---|---|
| `url` | Webhook URL (receives a JSON POST) | yes |

POSTs JSON {title, body, app} to any URL: wire it to Zapier, Make, IFTTT, n8n, Home Assistant, or your own endpoint.
<!-- /generated:notify-fields -->

The body is `{"title": "...", "body": "...", "app": "Dropwatch"}`.

## When a test fails

**Send test notification** reports each service: "Sent to Discord and ntfy." or "Failed: Telegram: HTTP
401." A failure names the service and the HTTP status or the kind of connection error, never the URL or
token. Common causes: a revoked webhook (HTTP 404), a wrong token (HTTP 401), or a self-hosted server the
container cannot reach (couldn't connect).

## Known limitations

- Alerts are decided in memory. An alert decided just before a restart is lost, and after a restart the
  matching "working again" message is not sent.
- Each send has a 10-second budget and is not retried, except the weekly summary.
- URL fields must start with `http://` or `https://`.
