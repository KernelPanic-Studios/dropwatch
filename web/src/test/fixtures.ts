import type { Campaign, State } from "../api/client";

const inDays = (d: number) => new Date(Date.now() + d * 86_400_000).toISOString();
const reward = (name: string) => ({ name, image_url: `https://img.example/${encodeURIComponent(name)}.png` });

export function campaign(over: Partial<Campaign> & { id: string }): Campaign {
  return {
    name: "Frights & Delights", game: "Palia", box_art_url: "https://static-cdn.jtvnw.net/ttv-boxart/1.jpg",
    ends_at: inDays(3), linked: true, maybe_unlinked: false, link_url: "https://link.example", allowed_channels: [],
    minutes_needed: 338, verdict: "plenty", pinned: false, ends_before_turn: false, new: false,
    drops: [
      { id: "d1", name: "a", required_minutes: 60, current_minutes: 22, claimed: false, starts_at: inDays(-1), ends_at: inDays(3), rewards: [reward("10× Ectoplasm")] },
      { id: "d2", name: "b", required_minutes: 180, current_minutes: 22, claimed: false, starts_at: inDays(-1), ends_at: inDays(3), rewards: [reward("Fancypod Prize Bag")] },
      { id: "d3", name: "c", required_minutes: 360, current_minutes: 22, claimed: false, starts_at: inDays(-1), ends_at: inDays(3), rewards: [reward("Palcat Glasses")] },
    ],
    ...over,
  };
}

export function state(over: Partial<State> = {}): State {
  const now = campaign({ id: "c1" });
  return {
    state: "mining", signed_in: true, login: "kernelpanicattack", paused_until: null, last_refresh: new Date().toISOString(),
    current: {
      campaign: now, channel: { login: "example_streamer", viewers: 1200, favourite: true },
      reason: "most urgent", channel_reason: "favourite", also_credited: [],
      channels: [{ login: "other_streamer", viewers: 300, favourite: false }],
    },
    needs_you: [campaign({ id: "n1", name: "Extended Operations", game: "007 First Light", linked: false })],
    up_next: [campaign({ id: "u1", name: "Crimson Eye 2026", game: "Phasmophobia", minutes_needed: 111 })],
    done: [], catalog: null, last_switch: null, next_check_at: null, never: [], needs_ignored: [], first_in_line: [], build: "",
    priority_only: false, outside: [], points_watching: [],
    ...over,
  };
}
