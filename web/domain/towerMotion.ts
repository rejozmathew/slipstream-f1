import type { StoryEvent, StorySnapshot } from "./protocol";

export type RowCause = "pass" | "passed" | "pit" | "out" | "class" | "improve" | "best" | "deleted";
export type RowCue = { cause: RowCause; label: string; eventId: string };

/** Server-authored evidence is the only source of cause colour and labels. */
export function freshRowCues(story: StorySnapshot | undefined, previousSequence: number, trackStatus: string | undefined, speed: number): Map<string, RowCue> {
  const cues = new Map<string, RowCue>();
  if (!story || speed >= 30 || story.sequence < previousSequence) return cues;
  const cutoff = story.asOf ? Date.parse(story.asOf) : null;
  const put = (event: StoryEvent, cause: RowCause, label: string, numbers = event.driverNumbers) => numbers.forEach((number) => cues.set(number, { cause, label, eventId: event.id }));
  for (const event of story.events) {
    if (event.availableSequence <= previousSequence || event.availableSequence > story.sequence || (cutoff != null && Date.parse(event.availableAt) > cutoff)) continue;
    if (event.kind === "PASS" && event.state === "confirmed" && event.cause === "ON_TRACK" && trackStatus === "GREEN") {
      if (event.driverNumbers[0]) put(event, "pass", "PASS", [event.driverNumbers[0]]);
      if (event.driverNumbers[1]) put(event, "passed", "PASSED", [event.driverNumbers[1]]);
    } else if (["PIT_IN", "PIT_EXIT"].includes(event.kind) && event.cause === "PIT") put(event, "pit", event.kind === "PIT_IN" ? "PIT IN" : "PIT OUT");
    else if (event.kind === "STOPPED") put(event, "out", "STOPPED");
    else if (event.kind === "RETIRED_INDICATED") put(event, "out", "RETIRED · REPORTED");
    else if (event.kind === "CLASSIFICATION") put(event, "class", "CLASSIFIED");
    else if (event.kind === "LAP_DELETED") put(event, "deleted", "LAP DELETED");
    else if (event.kind === "LAP_IMPROVEMENT" && event.state === "confirmed") put(event, event.data.sessionBest === true ? "best" : "improve", event.data.sessionBest === true ? "SESSION BEST" : "PERSONAL BEST");
  }
  return cues;
}

export function rowMotionTiming(cause: RowCause | undefined, distance: number, posture: "desktop" | "phone" | "tv", speed: number) {
  const d = Math.max(1, distance);
  const profiles: Record<RowCause | "neutral", [number, string]> = {
    pass: [Math.min(1150, 520 + 70 * (d - 1)), "cubic-bezier(.45,.05,.2,1)"],
    passed: [Math.min(1150, 520 + 70 * (d - 1)), "cubic-bezier(.45,.05,.2,1)"],
    pit: [Math.min(1700, 820 + 80 * d), "cubic-bezier(.6,0,.3,1)"],
    out: [Math.min(1800, 1050 + 50 * d), "cubic-bezier(.55,0,.45,1)"],
    class: [950, "cubic-bezier(.65,0,.35,1)"],
    improve: [Math.min(1200, 560 + 60 * d), "cubic-bezier(.3,.9,.25,1)"],
    best: [Math.min(1200, 560 + 60 * d), "cubic-bezier(.3,.9,.25,1)"],
    deleted: [900 + 40 * d, "ease"], neutral: [700, "ease"],
  };
  const [duration, easing] = profiles[cause ?? "neutral"];
  return { duration: duration * (posture === "tv" ? 1.35 : posture === "phone" ? .85 : 1) * (speed >= 5 ? .6 : 1), easing };
}
