import type { StoryEvent } from "../../domain/protocol";
import { storyKind } from "./presentation";

const RANK: Record<string, number> = { WINNER: 5, POLE: 5, SESSION_END: 4, ELIMINATED: 4, FLAG: 3, LEAD_CHANGE: 3, STOPPED: 2, PHASE: 2 };

export function takeoverEligible(event: StoryEvent, speed: number) {
  if (event.priority < 3) return false;
  const kind = storyKind(event);
  const flag = String(event.data.flag ?? event.cause ?? "");
  if (kind === "LEAD_CHANGE" && !["ON_TRACK", "START"].includes(event.cause ?? "")) return false;
  if (kind === "FLAG" && !["VSC", "SAFETY_CAR", "RED_FLAG", "RED", "CHEQUERED"].includes(flag)) return false;
  return speed < 20 || ["WINNER", "POLE"].includes(kind) || (kind === "FLAG" && ["RED", "RED_FLAG"].includes(flag));
}

export type ActiveMoment = { event: StoryEvent; at: number; hold: number; minHold: number };

/** Prototype takeovers: bounded explanations, a readable minimum hold, and no fast-replay backlog. */
export class StoryMomentQueue {
  current: ActiveMoment | null = null;
  pending: StoryEvent[] = [];
  speed = 1;

  clear() { this.current = null; this.pending = []; }

  offer(events: StoryEvent[], speed: number, now: number) {
    this.speed = speed;
    for (const event of events) {
      if (!takeoverEligible(event, speed)) continue;
      const kind = storyKind(event);
      this.pending = this.pending.filter(item => storyKind(item) !== kind && item.id !== event.supersedes);
      if (this.current && (this.current.event.id === event.supersedes
        || (storyKind(this.current.event) === kind && !["WINNER", "POLE", "ELIMINATED"].includes(kind)))) this.current = null;
      this.pending.push(event);
    }
    if (speed >= 5 && this.pending.length > 1) {
      this.pending = [this.pending.reduce((best, event) => (RANK[storyKind(event)] ?? 0) >= (RANK[storyKind(best)] ?? 0) ? event : best)];
    }
    if (this.pending.length > 3) this.pending = this.pending.slice(-3);
    this.advance(now);
  }

  advance(now: number) {
    if (this.current && now - this.current.at < this.current.minHold) return;
    if (!this.pending.length) {
      if (this.current && now - this.current.at >= this.current.hold) this.current = null;
      return;
    }
    const event = this.pending.shift()!;
    const kind = storyKind(event);
    const scale = this.speed >= 5 ? .6 : 1;
    const hold = (["WINNER", "POLE", "ELIMINATED"].includes(kind) ? 9000 : kind === "FLAG" ? 4200 : 5600) * scale;
    this.current = { event, at: now, hold, minHold: 2600 * scale };
  }

  nextDeadline() {
    return this.current ? this.current.at + (this.pending.length ? this.current.minHold : this.current.hold) : null;
  }
}
