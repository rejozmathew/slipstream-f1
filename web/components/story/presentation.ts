import type { CSSProperties } from "react";
import type { Driver, RaceState, StoryEvent, StorySnapshot } from "../../domain/protocol";

export type StorySession = RaceState["session"];
export type StoryDrivers = Record<string, Driver>;
export type StoryPosture = "desktop" | "phone" | "tv";
export type StoryTone = "neutral" | "gain" | "loss" | "pit" | "out" | "purple" | "green" | "yellow" | "red" | "amber" | "accent" | "win" | "chequered";

export function availableStoryEvents(story?: StorySnapshot | null, history: StoryEvent[] = []) {
  const asOf = story?.asOf ? Date.parse(story.asOf) : Infinity;
  const all = [...history, ...(story?.events ?? [])].filter(event => event.availableSequence <= (story?.sequence ?? 0)
    && Date.parse(event.availableAt) <= asOf);
  const superseded = new Set(all.map(event => event.supersedes).filter(Boolean));
  return [...new Map(all.map(event => [event.id, event])).values()]
    .filter(event => !superseded.has(event.id))
    .sort((left, right) => Date.parse(left.availableAt) - Date.parse(right.availableAt)
      || left.availableSequence - right.availableSequence || left.id.localeCompare(right.id));
}

export function storyLocalTime(at: string, session?: StorySession) {
  const offset = session?.gmt_offset?.match(/^([+-]?)(\d{1,2}):(\d{2})(?::\d{2})?$/);
  const minutes = offset ? (Number(offset[2]) * 60 + Number(offset[3])) * (offset[1] === "-" ? -1 : 1) : 0;
  const time = Date.parse(at);
  return Number.isFinite(time) ? new Date(time + minutes * 60_000).toISOString().slice(11, 19) : "—";
}

export function storyStamp(event: StoryEvent, session?: StorySession) {
  if (event.lap != null) return `L${event.lap}`;
  // A historical session clock must come from the event. The current clock
  // cannot reconstruct stoppages or segment resets for an earlier moment.
  const clock = typeof event.data.sessionClock === "string" ? event.data.sessionClock
    : typeof event.data.clock === "string" ? event.data.clock : storyLocalTime(event.occurredAt, session);
  return [event.phase, clock].filter(Boolean).join(" ");
}

export function storyTeamStyle(driver?: Driver): CSSProperties {
  const colour = driver?.team_colour?.replace(/^#/, "");
  return colour && /^(?:[\da-f]{3}|[\da-f]{6}|[\da-f]{8})$/i.test(colour)
    ? { "--team": `#${colour}` } as CSSProperties : {};
}

export function storyDriverCode(number: string | undefined, drivers: StoryDrivers = {}) {
  return number ? drivers[number]?.code || number : "—";
}

export function storyDriverName(number: string | undefined, drivers: StoryDrivers = {}) {
  const parts = (number && drivers[number]?.name || "").trim().split(/\s+/).filter(Boolean);
  const titleCase = (value: string) => value.toLocaleLowerCase().replace(/(^|[\s-])\p{L}/gu, letter => letter.toLocaleUpperCase());
  return parts.length > 1 ? { first: titleCase(parts[0]), surname: titleCase(parts.slice(1).join(" ")) }
    : { first: "", surname: parts.length ? titleCase(parts[0]) : storyDriverCode(number, drivers) };
}

export function storyLapTime(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) return `${Math.floor(value / 60)}:${(value % 60).toFixed(3).padStart(6, "0")}`;
  return typeof value === "string" ? value : "";
}

export function storyKind(event: StoryEvent) {
  if (event.kind === "RESULT" || event.kind === "RESULT_CORRECTION") return "WINNER";
  if (event.kind === "PASS" && event.data.position === 1) return "LEAD_CHANGE";
  return event.kind;
}

/** The prototype's label/tone vocabulary, using only published event facts. */
export function describeStory(event: StoryEvent, drivers: StoryDrivers = {}, session?: StorySession) {
  const kind = storyKind(event);
  let tag = event.kind.replaceAll("_", " ");
  let tone: StoryTone = "neutral";
  let title = event.title;
  let detail = event.detail;
  const first = event.driverNumbers[0];
  const second = event.driverNumbers[1];
  const code = (number: string | undefined) => storyDriverCode(number, drivers);
  switch (kind) {
    case "PASS": tag = "PASS"; tone = "gain"; break;
    case "LEAD_CHANGE":
      tag = event.cause === "ON_TRACK" ? "NEW LEADER" : "LEAD";
      tone = event.cause === "PIT" ? "pit" : event.cause === "STOPPED" ? "out" : event.cause === "CLASSIFICATION" ? "amber" : "gain";
      if (event.cause === "ON_TRACK" && first && second && drivers[first] && drivers[second]) {
        title = `${storyDriverName(first, drivers).surname} passes ${storyDriverName(second, drivers).surname}`;
        detail = `on track for the lead${event.lap != null ? ` · lap ${event.lap}` : ""}`;
      }
      break;
    case "ORDER_CHANGE": tag = event.data.position === 1 ? "LEAD" : "ORDER"; tone = event.cause === "PIT" ? "pit" : event.cause === "CLASSIFICATION" ? "amber" : event.cause === "STOPPED" ? "out" : "neutral"; break;
    case "PIT_IN": tag = "PIT"; tone = "pit"; break;
    case "PIT_OUT": case "PIT_EXIT": tag = "OUT"; tone = "pit"; break;
    case "STOPPED": tag = "STOPPED"; tone = "out"; break;
    case "RETIRED_INDICATED": tag = "OUT"; tone = "out"; break;
    case "FASTEST_LAP": tag = "FASTEST"; tone = "purple"; break;
    case "SESSION_BEST": tag = "P1"; tone = "purple"; break;
    case "LAP_IMPROVEMENT": tag = event.data.sessionBest ? (session?.layout_family === "race" || event.lap != null ? "FASTEST" : "P1") : "IMPROVES"; tone = event.data.sessionBest ? "purple" : "green"; break;
    case "IMPROVEMENT": tag = "IMPROVES"; tone = "green"; break;
    case "SEGMENT_P1": tag = `${event.phase ?? ""} P1`.trim(); tone = "purple"; break;
    case "PROVISIONAL_POLE": tag = "PROVISIONAL POLE"; tone = "purple"; break;
    case "POLE": tag = "POLE POSITION"; tone = "purple"; break;
    case "INTO_DROP_ZONE": tag = "DROP ZONE"; tone = "loss"; break;
    case "OUT_OF_DROP_ZONE": tag = "SAFE"; tone = "gain"; break;
    case "ELIMINATED": tag = `OUT${event.data.phase || event.phase ? ` IN ${event.data.phase || event.phase}` : ""}`; tone = "loss"; break;
    case "PHASE": tag = event.phase ?? String(event.data.phase ?? "SEGMENT"); break;
    case "LAP_DELETED": tag = "DELETED"; tone = "amber"; break;
    case "PENALTY": tag = "PENALTY"; tone = "amber"; break;
    case "CLASSIFICATION": tag = "RESULT"; tone = "amber"; break;
    case "INVESTIGATION": tag = "STEWARDS"; break;
    case "OVERTAKE_MODE": tag = "OVERTAKE"; break;
    case "SECTOR_FLAG": tag = String(event.data.flag ?? "FLAG"); tone = "yellow"; break;
    case "RACE_CONTROL": case "NOTICE": tag = "NOTICE"; break;
    case "BATTLE": tag = "BATTLE"; tone = "accent"; break;
    case "FLAG": {
      const flag = String(event.data.flag ?? event.cause ?? "FLAG");
      tag = ({ GREEN: "GREEN", YELLOW: "YELLOW", VSC: "VSC", VSC_ENDING: "VSC ENDING", SAFETY_CAR: "SC", RED_FLAG: "RED FLAG", RED: "RED FLAG", CHEQUERED: "CHEQUERED" } as Record<string, string>)[flag] ?? flag.replaceAll("_", " ");
      tone = flag === "GREEN" ? "green" : ["RED", "RED_FLAG"].includes(flag) ? "red" : flag === "CHEQUERED" ? "chequered" : "yellow";
      if (flag === "VSC") { title = "Virtual Safety Car"; detail = "deployed"; }
      if (flag === "SAFETY_CAR") { title = "Safety Car"; detail = "deployed"; }
      if (flag === "VSC_ENDING") { title = "VSC ending"; detail = "racing resumes shortly"; }
      if (flag === "RED" || flag === "RED_FLAG") { title = "Session suspended"; detail = ""; }
      if (flag === "CHEQUERED") { title = /^(S?Q)[123]$/.test(event.phase ?? "") ? `${event.phase} ended` : "Chequered flag"; detail = ""; }
      if (flag === "GREEN") { title = "Track clear"; detail = ""; }
      break;
    }
    case "WINNER": tag = event.kind === "RESULT_CORRECTION" ? "RESULT UPDATED" : "WINNER"; tone = "win"; break;
    case "SESSION_END": tag = event.data.settled ? "SESSION COMPLETE" : /^(S?Q)[123]$/.test(event.phase ?? "") ? `${event.phase} ENDED` : "FLAG SHOWN"; break;
    default: break;
  }
  // A structured event's published text remains the fallback when identity
  // metadata is missing; never replace it with guessed sporting facts.
  return { kind, tag, tone, title, detail, firstCode: code(first) };
}
