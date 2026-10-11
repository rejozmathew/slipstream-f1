import type { StoryEvent, StorySnapshot } from "./protocol";

export type RowCause = "pass" | "passed" | "start" | "pit" | "promoted" | "out" | "class" | "improve" | "best" | "pushed" | "deleted" | "penalty" | "neutral";
export type RowCue = { cause: RowCause; label: string; eventId: string; kind: string; availableAt: string; data: Record<string, unknown>; count: number };
export type TowerPosture = "desktop" | "phone" | "tv";

/** Server-authored evidence is the only source of cause colour and labels. */
export function freshRowCues(story: StorySnapshot | undefined, previousSequence: number, trackStatus: string | undefined, speed: number): Map<string, RowCue> {
  const cues = new Map<string, RowCue>();
  if (!story || speed >= 30 || story.sequence < previousSequence) return cues;
  const cutoff = story.asOf ? Date.parse(story.asOf) : null;
  const put = (event: StoryEvent, cause: RowCause, label: string, numbers = event.driverNumbers) => numbers.forEach((number) => {
    const prior = cues.get(number);
    cues.set(number, { cause, label, eventId: event.id, kind: event.kind, availableAt: event.availableAt, data: event.data,
      count: prior?.cause === cause && ["pass", "passed"].includes(cause) ? prior.count + 1 : 1 });
  });
  for (const event of story.events) {
    if (event.availableSequence <= previousSequence || event.availableSequence > story.sequence || (cutoff != null && Date.parse(event.availableAt) > cutoff)) continue;
    if (event.kind === "PASS" && event.state === "confirmed" && event.cause === "ON_TRACK" && trackStatus === "GREEN") {
      if (event.driverNumbers[0]) put(event, "pass", "PASS", [event.driverNumbers[0]]);
      if (event.driverNumbers[1]) put(event, "passed", "PASSED", [event.driverNumbers[1]]);
    } else if (["PIT_IN", "PIT_EXIT"].includes(event.kind) && event.cause === "PIT") put(event, "pit", event.kind === "PIT_IN" ? "PIT IN" : "PIT EXIT");
    else if (event.kind === "ORDER_CHANGE" && event.state === "confirmed" && event.cause === "PIT") put(event, "pit", "PIT-RELATED CHANGE");
    else if (event.kind === "ORDER_CHANGE" && event.state === "confirmed" && event.cause === "CLASSIFICATION") put(event, "class", "CLASSIFIED");
    else if (event.kind === "ORDER_CHANGE" && event.state === "confirmed" && event.cause === "STOPPED") {
      if (event.driverNumbers[0]) put(event, "promoted", "ORDER CHANGE", [event.driverNumbers[0]]);
      if (event.driverNumbers[1]) put(event, "out", "SOURCE STOPPAGE", [event.driverNumbers[1]]);
    } else if (event.kind === "STOPPED") put(event, "out", "STOPPED");
    else if (event.kind === "RETIRED_INDICATED") put(event, "out", "RETIRED · REPORTED");
    else if (event.kind === "CLASSIFICATION") put(event, "class", "CLASSIFIED");
    else if (event.kind === "LAP_DELETED") put(event, "deleted", "LAP DELETED");
    else if (event.kind === "PENALTY") put(event, "penalty", "PENALTY NOTICE");
    else if (event.kind === "LAP_IMPROVEMENT" && event.state === "confirmed") put(event, event.data.sessionBest === true ? "best" : "improve", event.data.sessionBest === true ? "SESSION BEST" : "PERSONAL BEST");
  }
  return cues;
}

export function towerMotionScale(posture: TowerPosture, speed: number) {
  return (posture === "tv" ? 1.35 : posture === "phone" ? .85 : 1) * (speed >= 5 ? .6 : 1);
}

/** Durations, travel curves and stacking order match the approved shared tower. */
export function rowMotionTiming(cause: RowCause | undefined, distance: number, posture: TowerPosture, speed: number) {
  const d = Math.max(1, distance);
  const profiles: Record<RowCause, [number, string, number]> = {
    pass: [Math.min(1150, 520 + 70 * (d - 1)), "cubic-bezier(.45,.05,.2,1)", 6],
    passed: [Math.min(1150, 520 + 70 * (d - 1)), "cubic-bezier(.45,.05,.2,1)", 2],
    start: [Math.min(700, 360 + 40 * d), "cubic-bezier(.3,.6,.3,1)", 4],
    pit: [Math.min(1700, 820 + 80 * d), "cubic-bezier(.6,0,.3,1)", 1],
    promoted: [680, "cubic-bezier(.4,0,.2,1)", 3],
    out: [Math.min(1800, 1050 + 50 * d), "cubic-bezier(.55,0,.45,1)", 1],
    class: [950, "cubic-bezier(.65,0,.35,1)", 5],
    improve: [Math.min(1200, 560 + 60 * d), "cubic-bezier(.3,.9,.25,1)", 6],
    best: [Math.min(1200, 560 + 60 * d), "cubic-bezier(.3,.9,.25,1)", 6],
    pushed: [600, "cubic-bezier(.4,0,.2,1)", 2],
    deleted: [Math.min(1400, 900 + 40 * d), "cubic-bezier(.6,0,.4,1)", 2],
    penalty: [700, "cubic-bezier(.4,0,.2,1)", 3],
    neutral: [700, "cubic-bezier(.4,0,.2,1)", 3],
  };
  const [duration, easing, zIndex] = profiles[cause ?? "neutral"];
  return { duration: duration * towerMotionScale(posture, speed), easing, zIndex };
}

/** Read the visual remainder of an in-flight FLIP before retargeting its row. */
export function translationY(transform: string) {
  const matrix = transform.match(/^matrix\(([^)]+)\)$/)?.[1].split(",").map(Number);
  if (matrix?.length === 6) return Number.isFinite(matrix[5]) ? matrix[5] : 0;
  const matrix3d = transform.match(/^matrix3d\(([^)]+)\)$/)?.[1].split(",").map(Number);
  return matrix3d?.length === 16 && Number.isFinite(matrix3d[13]) ? matrix3d[13] : 0;
}
