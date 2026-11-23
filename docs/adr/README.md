# Architecture decision records

One file per decision, never rewritten once accepted: a new record supersedes an old one, and the old
one's status names its successor. A record added in a pull request is `Proposed` until it merges, then
`Accepted, YYYY-MM-DD`. The practice itself is [ADR-0001](0001-record-architecture-decisions.md).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-one-process-one-miner.md) | One process runs the miner and the API, for one Twitch account | Accepted (retroactive) |
| [0003](0003-port-the-twitch-protocol-from-twitchdropsminer.md) | Port the Twitch protocol from TwitchDropsMiner and keep the sources beside it | Accepted (retroactive) |
| [0004](0004-tv-code-sign-in-and-public-catalogue.md) | Sign in with Twitch's TV device code, and discover campaigns from a public catalogue | Accepted (retroactive) |
| [0005](0005-sqlite-on-the-event-loop.md) | Keep everything in one SQLite file, used synchronously on the event loop | Accepted (retroactive) |
| [0006](0006-pure-planner.md) | The planner is a pure function | Accepted (retroactive) |
| [0007](0007-one-page-password-and-lan-hardening.md) | One page password, hashed session tokens, and a Host check instead of user accounts | Accepted (retroactive) |
| [0008](0008-live-updates-as-refetch-signals.md) | Live updates are server-sent "something changed" signals | Accepted (retroactive) |
| [0009](0009-api-types-generated-from-openapi.md) | The page's API types are generated from the OpenAPI schema, and both are checked | Accepted (retroactive) |
| [0010](0010-notifications-sent-from-memory.md) | Decide notifications in memory and send them straight away | Accepted (retroactive) |
| [0011](0011-restart-instead-of-repair.md) | When mining is stuck, exit and let Docker restart it; copy the database before an upgrade | Accepted (retroactive) |
| [0012](0012-simulated-playback-for-watch-credit.md) | Earn watch time by simulating HLS playback | Accepted (retroactive) |
| [0013](0013-release-through-ghcr-and-community-applications.md) | Publish to GitHub's registry from tags; list through Community Applications | Accepted (retroactive) |
| [0014](0014-generate-reference-tables-in-the-docs.md) | Generate the docs' reference tables from the code | Proposed |
| [0015](0015-relative-urls-for-subfolder-installs.md) | Relative URLs, so Dropwatch works in a subfolder without a base-path setting | Proposed |
