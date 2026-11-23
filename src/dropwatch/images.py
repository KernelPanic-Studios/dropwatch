"""Copies of the images History shows (2026-10-10): Twitch's box art and reward links can stop working once a
campaign ends, and History keeps a year. Files are named by a hash of their URL, so the API can only ever
serve what it downloaded. Only https://static-cdn.jtvnw.net (default port, no userinfo, no redirects) is
fetched: a stored URL can't make Dropwatch reach anywhere else."""
from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger("dropwatch.images")

HOST = "static-cdn.jtvnw.net"
MAX_BYTES = 3 * 1024 * 1024
RETRY_AFTER = timedelta(days=1)  # a link that failed (often gone for good) is tried again a day later
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".webp": "image/webp"}
NAME = re.compile(r"[0-9a-f]{24}\.(png|jpg|jpeg|gif|webp)")
Get = Callable[[str], Awaitable[tuple[int, str, bytes]]]  # url -> (status, content type, body)


def box_art_144(url: str) -> str:
    """The size the page shows box art at (web/src/ui/format.ts boxArt)."""
    if not url:
        return ""
    if "{width}x{height}" in url:
        return url.replace("{width}x{height}", "144x192")
    if re.search(r"-\d+x\d+\.\w+$", url):
        return re.sub(r"-\d+x\d+(\.\w+)$", r"-144x192\1", url)
    return re.sub(r"(\.\w+)$", r"-144x192\1", url)


class ImageCache:
    def __init__(self, folder: Path, get: Get | None = None, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._dir, self._get, self._clock = folder, get, clock
        self._failed: dict[str, datetime] = {}  # url -> when it last failed

    @staticmethod
    def _name(url: str) -> str | None:
        parts = urlsplit(url)
        ext = os.path.splitext(parts.path)[1].lower()
        if (parts.scheme != "https" or parts.hostname != HOST or parts.netloc != HOST
                or ext not in TYPES):  # netloc == host: no userinfo, no port
            return None
        return hashlib.sha256(url.encode()).hexdigest()[:24] + ext

    def file(self, name: str) -> Path | None:
        """The kept file for a served name, or None. The full-match name keeps the path inside the folder."""
        if not NAME.fullmatch(name):
            return None
        path = self._dir / name
        return path if path.is_file() else None

    def local_url(self, url: str) -> str | None:
        name = self._name(url) if url else None
        return f"api/img/{name}" if name and (self._dir / name).is_file() else None

    async def ensure(self, urls: Iterable[str], get: Get | None = None) -> int:
        """Download the ones not kept yet; returns how many were added. A failure is logged and left alone
        for RETRY_AFTER."""
        get = get or self._get
        now = self._clock()
        added = 0
        for url in dict.fromkeys(urls):
            name = self._name(url) if url else None
            if name is None or (self._dir / name).is_file():
                continue
            if (failed := self._failed.get(url)) is not None and now - failed < RETRY_AFTER:
                continue
            try:
                status, ctype, body = await get(url)
            except Exception as exc:  # noqa: BLE001 - one bad image must not stop the rest
                log.info("Image not kept (%s): %s", type(exc).__name__, name)
                self._failed[url] = now
                continue
            if status != 200 or not ctype.startswith("image/") or len(body) > MAX_BYTES:
                log.info("Image not kept (HTTP %s, %s, %d bytes): %s", status, ctype, len(body), name)
                self._failed[url] = now
                continue
            self._failed.pop(url, None)
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp = self._dir / (name + ".part")
            tmp.write_bytes(body)
            tmp.replace(self._dir / name)
            added += 1
        return added


def aiohttp_get(session) -> Get:
    """One GET, no redirects (a redirect could leave Twitch's host), read to the end or just past the cap."""
    import aiohttp

    async def get(url: str) -> tuple[int, str, bytes]:
        async with session.get(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            body = bytearray()
            async for chunk in resp.content.iter_chunked(65536):  # read(n) returns only what has arrived
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            return resp.status, resp.headers.get("Content-Type", ""), bytes(body)
    return get
