"""Settings › Backup: lists, pins, settings and notification channels in one JSON file, and back again
(approved mockup docs/design/pre-docker-mockup.html, 2026-10-10). Twitch sign-in, the page password and
History are not in it: they belong to the install, not to the person's choices."""
from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError

from .api.models import ListsIn, Pins, PointsChannelsIn, SettingsIn
from .notify import CHANNELS
from .store import SETTINGS
from .version import VERSION

FORMAT = 1
MAX_VALUE = 500  # same cap as the channel editor


class BadBackup(ValueError):
    pass


def make_backup(store, now: datetime, *, secrets: bool) -> dict:
    p = store.get_prefs()
    channels = {}
    for kind, values in store.get_channels().items():
        spec = CHANNELS.get(kind)
        if spec is None:
            continue
        secret = {f.key for f in spec.fields if f.secret}
        channels[kind] = {k: v for k, v in values.items() if v and (secrets or k not in secret)}
    return {
        "dropwatch_backup": FORMAT, "version": VERSION, "made_at": now.isoformat(),
        "lists": {"priority": list(p.priority), "never": sorted(p.never), "favourites": list(p.favourites)},
        "pins": store.get_pins(),
        "points_channels": list(store.get_points_channels()),
        "settings": store.get_settings(),
        "notify_channels": channels,
    }


def restore_backup(store, data: object) -> list[str]:
    """Checks the whole file first, then replaces. Returns what a newer Dropwatch wrote that this one
    skipped."""
    if not isinstance(data, dict) or data.get("dropwatch_backup") != FORMAT:
        raise BadBackup("That isn't a Dropwatch backup, or it's from a newer version.")
    skipped: list[str] = []
    try:
        # only the list fields this version knows, as with settings: a newer backup may carry more
        raw_lists = data.get("lists") or {}
        if not isinstance(raw_lists, dict):
            raise BadBackup("The backup's lists aren't readable.")
        lists = ListsIn.model_validate({k: v for k, v in raw_lists.items() if k in ListsIn.model_fields})
        pins = Pins.model_validate({"pins": data.get("pins") or []})
        # backups from before the Channel points page have none: the list here is left as it is
        points = (PointsChannelsIn.model_validate({"channels": data["points_channels"] or []})
                  if "points_channels" in data else None)
        raw = data.get("settings") or {}
        if not isinstance(raw, dict):
            raise BadBackup("The backup's settings aren't readable.")
        skipped += [f"setting {k}" for k in raw if k not in SETTINGS]
        settings = SettingsIn.model_validate({k: v for k, v in raw.items() if k in SETTINGS})
    except ValidationError as e:
        raise BadBackup(f"The backup has a value Dropwatch can't use: {e.errors()[0]['msg']}.") from e
    if clash := set(lists.priority) & set(lists.never):
        raise BadBackup(f"In both Priority and Never: {', '.join(sorted(clash))}")

    current = store.get_channels()
    chans = data.get("notify_channels") or {}
    if not isinstance(chans, dict):
        raise BadBackup("The backup's notification channels aren't readable.")
    channels: dict[str, dict[str, str]] = {}
    for kind, values in chans.items():
        spec = CHANNELS.get(kind)
        if spec is None or not isinstance(values, dict):
            skipped.append(f"channel {kind}")
            continue
        keep = {}
        for f in spec.fields:
            v = values.get(f.key)
            if v is None and f.secret:  # saved without secrets: keep the one already set here
                v = current.get(kind, {}).get(f.key)
            if v is None:
                continue
            if not isinstance(v, str) or len(v) > MAX_VALUE:
                raise BadBackup(f"The backup's {spec.name} {f.label.split(' (')[0]} isn't usable.")
            keep[f.key] = v.strip()
        skipped += [f"{kind} field {k}" for k in values if k not in {f.key for f in spec.fields}]
        channels[kind] = keep

    store.set_lists(lists.priority, set(lists.never), lists.favourites)
    store.set_pins(pins.pins)
    if points is not None:
        store.set_points_channels(points.channels)
    store.put_settings(settings.model_dump(exclude_none=True))
    store.set_channels(channels)
    return skipped
