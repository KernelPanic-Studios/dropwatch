import type { components } from "./types";

type S = components["schemas"];
export type State = S["StateOut"];
export type Campaign = S["CampaignOut"];
export type Drop = S["DropOut"];
export type Reward = S["RewardOut"];
export type Channel = S["ChannelOut"];
export type Current = S["CurrentOut"];
export type Lists = S["ListsOut"];
export type Settings = S["SettingsOut"];
export type About = S["AboutOut"];
export type Activity = S["ActivityOut"];
export type Sessions = S["SessionsOut"];
export type ActivityEvent = S["ActivityEvent"];
export type SettingsIn = S["SettingsIn"];
export type History = S["HistoryOut"];
export type Claim = S["ClaimOut"];
export type Me = S["MeOut"];
export type SignIn = S["SignInStatus"];
export type Suggestions = S["SuggestionsOut"];
export type ChannelSuggestion = S["ChannelSuggestion"];
export type NotifyChannels = S["NotifyChannelsOut"];
export type NotifyChannel = S["NotifyChannelOut"];
export type NotifyTest = S["NotifyTestOut"];
export type PointsPage = S["PointsPageOut"];
export type PointsChannel = S["PointsChannelOut"];

/** An HTTP failure with the server's own message (FastAPI's `detail`) when it gave one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
/** Called once per 401 so the app can show its sign-in screen. */
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401 && path !== "/login") onUnauthorized();
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      if (typeof j?.detail === "string") msg = j.detail;
      else if (Array.isArray(j?.detail) && j.detail[0]?.msg) msg = j.detail[0].msg;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  if (r.status === 204 || r.headers.get("content-length") === "0") return undefined as T;
  const text = await r.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string) => call<T>("GET", path),
  post: <T = void>(path: string, body?: unknown) => call<T>("POST", path, body),
  put: <T>(path: string, body: unknown) => call<T>("PUT", path, body),
  del: <T = void>(path: string) => call<T>("DELETE", path),
};
