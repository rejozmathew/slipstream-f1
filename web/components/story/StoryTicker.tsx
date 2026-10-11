import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { StoryEvent } from "../../domain/protocol";
import type { StoryProps } from "./StoryFeed";
import { availableStoryEvents, describeStory, storyStamp, storyTeamStyle } from "./presentation";
import "./story.css";

export function StoryTicker({ story, sessionKey, generation = 0, recordingVersion, drivers = {}, session, visible = true, count = 4, onInspect, brand }: StoryProps & { count?: number; onInspect?: (event: StoryEvent) => void; brand?: ReactNode }) {
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const previous = useRef<{ sequence: number; generation: number; session?: string | null; version?: string | null; visible: boolean } | null>(null);
  const identity = sessionKey ?? session?.key ?? story?.events[0]?.sessionKey;
  const events = useMemo(() => availableStoryEvents(story).filter(event => event.priority >= 2 && event.kind !== "BATTLE").slice(-count).reverse(), [story, count]);
  useEffect(() => {
    const reset = () => { previous.current = null; setFresh(new Set()); };
    document.addEventListener("visibilitychange", reset);
    return () => document.removeEventListener("visibilitychange", reset);
  }, []);
  useLayoutEffect(() => {
    const last = previous.current;
    const sequence = story?.sequence ?? 0;
    const silent = !last || !visible || !last.visible || document.visibilityState === "hidden" || last.generation !== generation || last.session !== identity || last.version !== recordingVersion || sequence < last.sequence;
    setFresh(new Set(silent ? [] : events.filter(event => event.availableSequence > last.sequence).map(event => event.id)));
    previous.current = { sequence, generation, session: identity, version: recordingVersion, visible };
  }, [events, story?.sequence, generation, identity, recordingVersion, visible]);
  return <div className="story-ticker ticker" aria-label="Recent session highlights">{brand}<span className="tk-lbl">LAST</span><ol className="tk-list">{events.map((event, index) => {
    const description = describeStory(event, drivers, session);
    const content = <><span className="tk-time mono">{storyStamp(event, session)}</span><span className="tk-tag">{description.tag}{event.state === "provisional" ? " · PROVISIONAL" : ""}</span><b>{description.title}</b><em>{description.detail}</em></>;
    return <li key={event.id} className={`tk-item tone-${description.tone}${index === 0 ? " is-latest" : ""}${fresh.has(event.id) ? " is-new" : ""}`} style={storyTeamStyle(drivers[event.driverNumbers[0]])}>{onInspect ? <button className="tk-inspect" type="button" onClick={() => onInspect(event)} aria-label={`Inspect ${description.title}`}>{content}</button> : content}</li>;
  })}</ol></div>;
}
