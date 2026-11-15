# Signing in: the page password and Twitch

Dropwatch has two separate sign-ins: a **page password** that protects the dashboard, and a **Twitch
session** that the miner uses. Neither is the other.

## The page password

On the first visit Dropwatch asks you to **Protect this page**: choose a password of at least 8
characters and type it twice. Anyone who can open the address on your network needs it. A browser stays
signed in for 30 days.

- **Wrong password** five times from one address within 15 minutes locks that address for the rest of
  the 15 minutes. The page currently says "Couldn't reach the miner. Try again." while locked (finding F2
  in [the architecture findings](../architecture/README.md#findings)); wait and try again.
- **Settings › Account & security › Signed-in browsers** lists them ("Chrome on Windows", ...). Sign out
  one, or **Sign out everywhere else**. **Sign out of this page** signs out the browser you are using; mining carries on.
- **Forgot the password:** there is no reset screen. Stop the container and remove the
  `page_password_hash` row from the `settings` table of `drops.db` with any SQLite tool; the next visit
  asks for a new one. Twitch stays signed in.

## Connecting Twitch

1. **Connect your Twitch account › Get a sign-in code.** Dropwatch shows an 8-letter code, a link to
   `twitch.tv/activate` and a QR code for your phone. The code lasts about 30 minutes.
2. Open the link on any device, enter the code, sign in to Twitch as usual and click **Authorize**.
3. The page says **Connected**. Mining starts at once, and campaigns appear on Overview within a minute.

Use the account that should earn the drops. Dropwatch signs in as Twitch's own TV app, because that is the
sign-in Twitch still allows for this; it accepts the token only if Twitch issued it for the TV app.

What can go wrong:

| Shown | Meaning |
|---|---|
| That code expired | 30 minutes passed. Get a new one. |
| Sign-in didn't finish, with Twitch's reason | Twitch refused the code, or issued a token for another app. Nothing was saved. |
| Twitch wouldn't start a sign-in (...) | Twitch did not hand out a code; try again later. |

## When Twitch ends the session

If Twitch rejects the session (HTTP 401), Dropwatch stops mining, deletes the saved session and never
retries it. Overview shows **Twitch signed you out** with **Get a sign-in code**, and the "Twitch sign-in
stopped working" notification goes out if it is on. Drop progress is kept by Twitch, so mining continues
where it stopped after you sign in again.

To sign out on purpose: **Settings › Account & security › Twitch › Sign out**, then confirm. Mining stops
until you sign in again with a new code.

## Campaigns Twitch hides from the TV sign-in

The TV sign-in cannot list drop campaigns, so Dropwatch reads them from a public catalogue run by a third
party, hourly, and sends it nothing about your account. Your own Twitch inventory is merged over it, so
your progress and links always come from Twitch. If the catalogue is down, Overview says **Can't reach the
campaign list since ...** (or **The campaign list hasn't updated since ...** after 6 hours without
changes). Campaigns you have already started keep mining; new ones are not found until it is back.

## On a PC

`dropwatch signin` does the same code sign-in from a terminal. `dropwatch signin --browser` is an older
fallback that signs in through a Chrome or Edge window (install with the `browser` extra; set
`DROPWATCH_BROWSER` to the browser's path if it is not found). The Docker image cannot run it.

## Variables

| Variable | Default | Notes |
|---|---|---|
| `DROPWATCH_BROWSER` | Chrome or Edge in their usual Windows folders | PC only, for `signin --browser` |

## Known limitations

- One Twitch account per install.
- No password reset in the page.
- Account links for campaigns that have not started yet are unknown until Twitch lists them; see
  [mining.md](mining.md#needs-you).
