/** Live updates from the miner (spec §11): any SSE event re-fetches the state (debounced), and a
 * stream that stays broken for 15 s means "Can't reach the miner". The page is the only place that
 * can know the miner is gone, because the miner can't report its own absence (spec §9). */
export const EVENT_KINDS = ["state", "refreshed", "claimed", "switched", "needs_you", "signin", "progress"] as const;
export type EventKind = (typeof EVENT_KINDS)[number];

export interface LiveOptions {
  onRefetch: () => void;
  onConnection: (live: boolean) => void;
  onEvent?: (kind: EventKind, data: unknown) => void;
  /** The browser gave up on the stream (it does on a 401, without saying so): check the page session. */
  onClosed?: () => void;
  debounceMs?: number;
  lostAfterMs?: number;
  retryMs?: number;
  open?: (url: string) => EventSource;
}

export function connectLive(o: LiveOptions): () => void {
  const debounceMs = o.debounceMs ?? 500;
  const lostAfterMs = o.lostAfterMs ?? 15_000;
  const retryMs = o.retryMs ?? 5_000;
  const open = o.open ?? ((url: string) => new EventSource(url));
  let es: EventSource | null = null;
  let refetchTimer: ReturnType<typeof setTimeout> | undefined;
  let lostTimer: ReturnType<typeof setTimeout> | undefined;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let lost = false;
  let hadError = false;
  let stopped = false;

  const refetchSoon = () => {
    clearTimeout(refetchTimer);
    refetchTimer = setTimeout(o.onRefetch, debounceMs);
  };

  const connect = () => {
    if (stopped) return;
    es = open("api/events");  // relative: see api/client.ts
    es.onopen = () => {
      clearTimeout(lostTimer);
      lostTimer = undefined;
      if (lost) {
        lost = false;
        o.onConnection(true);
      }
      if (hadError) {
        hadError = false;
        refetchSoon(); // catch up on whatever happened while we were cut off (even a short blip)
      }
    };
    es.onerror = () => {
      hadError = true;
      if (lostTimer === undefined && !lost) {
        lostTimer = setTimeout(() => {
          lostTimer = undefined;
          lost = true;
          o.onConnection(false);
        }, lostAfterMs);
      }
      if (es && es.readyState === 2 /* CLOSED: the browser gave up (e.g. a 401) */) {
        es = null;
        o.onClosed?.();
        clearTimeout(retryTimer);
        retryTimer = setTimeout(connect, retryMs);
      }
    };
    for (const kind of EVENT_KINDS) {
      es.addEventListener(kind, (e) => {
        let data: unknown = null;
        try {
          data = JSON.parse((e as MessageEvent).data);
        } catch {
          /* keep null */
        }
        o.onEvent?.(kind, data);
        refetchSoon();
      });
    }
  };

  connect();
  return () => {
    stopped = true;
    clearTimeout(refetchTimer);
    clearTimeout(lostTimer);
    clearTimeout(retryTimer);
    es?.close();
  };
}
