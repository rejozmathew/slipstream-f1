import { useEffect, useRef, useState } from "react";
import type { StoryEvent } from "../../domain/protocol";
import { storyStamp, type StoryProps } from "./StoryFeed";

export function StoryMoments({ story, sessionKey, generation = 0, playing = true, speed = 1, reducedMotion = false }: StoryProps & { playing?: boolean; speed?: number; reducedMotion?: boolean }) {
  const [moment, setMoment] = useState<StoryEvent | null>(null);
  const previous = useRef<{ sequence: number; generation: number; session?: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const session = sessionKey ?? story?.events[0]?.sessionKey;
  useEffect(() => {
    const last = previous.current;
    const sequence = story?.sequence ?? 0;
    previous.current = { sequence, generation, session };
    if (!last || last.generation !== generation || last.session !== session || sequence < last.sequence || !playing) {
      if (timer.current) clearTimeout(timer.current);
      setMoment(null);
      return;
    }
    const candidates = (story?.events ?? []).filter(event => event.availableSequence > last.sequence && event.priority >= 3
      && (speed < 20 || ["RESULT", "RESULT_CORRECTION"].includes(event.kind) || (event.kind === "FLAG" && ["RED", "RED_FLAG"].includes(String(event.data.flag)))));
    // Coalesce rapid playback into its newest important fact, never queue old news.
    const next = candidates.at(-1);
    if (next) {
      if (timer.current) clearTimeout(timer.current);
      setMoment(next);
      timer.current = setTimeout(() => setMoment(null), speed >= 5 ? 2200 : 5000);
    }
  }, [story, generation, playing, speed, session]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  if (!moment) return null;
  return <aside className={`story-moment${reducedMotion ? " story-moment--still" : ""}`} role="status" aria-live="polite">
    <span className="story-moment-kicker">{storyStamp(moment)} · {moment.kind.replaceAll("_", " ")}{moment.state === "provisional" ? " · PROVISIONAL" : ""}</span>
    <strong>{moment.title}</strong><p>{moment.detail}</p><button type="button" onClick={() => setMoment(null)} aria-label="Dismiss moment">×</button>
  </aside>;
}
