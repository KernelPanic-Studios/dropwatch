"""Run the mining loop as a startable/stoppable service (API sign-in starts it, sign-out stops it)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .events import EventBus
from .runner import POINTS_SLOTS, Runner, State

log = logging.getLogger("dropwatch.service")


@dataclass
class Parts:
    runner: Runner
    pubsub: object
    close: Callable[[], Awaitable[None]]


def build_parts(store, session, emit) -> Parts:
    from .twitch.catalog import Catalog
    from .twitch.client import TwitchClient
    from .twitch.gql import Gql
    from .twitch.pubsub import PubSub
    from .twitch.transport import AiohttpTransport
    from .twitch.watch import Watcher

    transport = AiohttpTransport()
    catalog_transport = AiohttpTransport()  # its own cookie jar: nothing of Twitch's goes to the catalogue
    catalog = Catalog(catalog_transport, store.path.parent / "catalog.json")
    pubsub = PubSub(lambda: session.access_token)
    gql = Gql(transport, lambda: session)
    runner = Runner(TwitchClient(gql, session.user_id, catalog=catalog),
                    Watcher(transport, lambda: session, gql), pubsub, store,
                    user_id=session.user_id, emit=emit,
                    # Channel points: up to two streams watched alongside drops, each with its own playback
                    points_watchers=[Watcher(transport, lambda: session, gql) for _ in range(POINTS_SLOTS)])

    async def close() -> None:
        await pubsub.close()
        await transport.close()
        await catalog_transport.close()
    return Parts(runner, pubsub, close)


class MinerService:
    """One miner at most: start/stop are serialized, and the loop tears itself down when it ends."""

    def __init__(self, store, bus: EventBus, build=build_parts):
        self.crashed: str | None = None  # set when the mining loop died on an error
        self._store, self._bus, self._build = store, bus, build
        self._parts: Parts | None = None
        self._tasks: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task | None = None

    @property
    def runner(self) -> Runner | None:
        return self._parts.runner if self._parts else None

    @property
    def running(self) -> bool:
        return self._parts is not None

    def _emit(self, kind: str, data: dict) -> None:
        log.info("%s %s", kind, data)
        self._bus.publish(kind, data)

    async def start(self) -> bool:
        async with self._lock:
            if self._parts is not None:
                return True
            session = self._store.get_session()
            if session is None:
                return False
            parts = self._build(self._store, session, self._emit)
            self._parts = parts
            self.crashed = None
            loop = asyncio.create_task(self._loop(parts))
            loop.add_done_callback(self._loop_ended)
            self._tasks = [loop, asyncio.create_task(self._events(parts))]
            return True

    async def _loop(self, parts: Parts) -> None:
        r = parts.runner
        while True:
            delay = await r.safe_tick()  # the first tick refreshes; safe_tick never raises
            if r.state == State.SIGNED_OUT:
                break
            await asyncio.sleep(delay)
        self._store.clear_session()  # the token is dead: never retry it
        self._bus.publish("signin", {"status": "expired",
                                     "message": "Twitch session expired. Sign in again."})

    def _loop_ended(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return  # stop() did this
        if (exc := task.exception()) is not None:
            log.error("Mining loop crashed; mining stopped", exc_info=exc)
            self.crashed = type(exc).__name__  # the Docker health check fails, so the container restarts
            self._bus.publish("state", {"state": "idle", "error": type(exc).__name__})
        self._reaper = asyncio.get_running_loop().create_task(self.stop())

    async def _events(self, parts: Parts) -> None:
        pubsub = parts.pubsub
        if not hasattr(pubsub, "events"):
            return
        async for ev in pubsub.events():
            await parts.runner.safe_handle(ev)

    async def stop(self) -> None:
        async with self._lock:
            # take ownership before the first await, so an overlapping start() can't be undone
            parts, tasks = self._parts, self._tasks
            self._parts, self._tasks = None, []
            me = asyncio.current_task()
            for t in tasks:
                if t is not me:
                    t.cancel()
            for t in tasks:
                if t is not me:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await t
            if parts is not None:
                await parts.close()

    async def wait_stopped(self) -> None:
        """Until the mining loop ends (session expired or crash), then make sure it is torn down."""
        loop = self._tasks[0] if self._tasks else None
        if loop is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await loop
        await self.stop()
