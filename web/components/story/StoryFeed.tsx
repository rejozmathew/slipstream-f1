import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { StoryEvent, StorySnapshot } from "../../domain/protocol";
import { slipstreamApi } from "../../api/client";
import "./story.css";

export type StoryProps = {
  sessionKey?: string | null;
  story?: StorySnapshot | null;
  mode: "live" | "replay";
  generation?: number;
  driverNumber?: string | null;
  onReplay?: (event: StoryEvent) => void;
  compact?: boolean;
  recordingVersion?: string | null;
};

export function storyStamp(event: StoryEvent) {
  return event.lap != null ? `L${event.lap}` : [event.phase, event.occurredAt.slice(11, 19)].filter(Boolean).join(" · ");
}

export function StoryFeed(props: StoryProps) {
  return <StoryFeedContent key={`${props.sessionKey ?? props.story?.events[0]?.sessionKey ?? "empty"}:${props.generation ?? 0}:${props.recordingVersion ?? ""}`} {...props} />;
}

function StoryFeedContent({ story, sessionKey, mode, generation = 0, driverNumber, onReplay, compact = false, recordingVersion }: StoryProps) {
  const [filter, setFilter] = useState<"all" | "highlights" | "following">("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [unseen, setUnseen] = useState(0);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [older, setOlder] = useState<StoryEvent[]>([]);
  const [previousWindow, setPreviousWindow] = useState(story);
  const [hasMore, setHasMore] = useState(!!story?.hasMore);
  const [offset, setOffset] = useState(story?.events.length ?? 0);
  const [pageTotal, setPageTotal] = useState(story?.total ?? 0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const previous = useRef<{ ids: Set<string>; generation: number; height: number; sequence: number; session: string | undefined } | null>(null);
  const request = useRef(0);
  const session = sessionKey ?? story?.events[0]?.sessionKey;
  // Keep every page the viewer has seen when the compact server window rolls
  // forward. Navigation remounts this component, bounding retention by visit.
  if (previousWindow !== story) {
    setPreviousWindow(story);
    setOlder(value => [...new Map([...value, ...(previousWindow?.events ?? [])].map(event => [event.id, event])).values()]);
  }
  const available = useMemo(() => {
    const all = [...older, ...(story?.events ?? [])].filter(event => event.availableSequence <= (story?.sequence ?? 0)
      && (!story?.asOf || Date.parse(event.availableAt) <= Date.parse(story.asOf)));
    const superseded = new Set(all.map(event => event.supersedes).filter(Boolean));
    return [...new Map(all.map(event => [event.id, event])).values()]
      .filter(event => !superseded.has(event.id));
  }, [older, story]);
  const events = useMemo(() => available
      .filter(event => filter === "all" || (filter === "highlights" ? event.priority >= 2 : !!driverNumber && event.driverNumbers.includes(driverNumber)))
      .sort((a, b) => Date.parse(b.availableAt) - Date.parse(a.availableAt) || b.availableSequence - a.availableSequence),
    [available, filter, driverNumber]);
  const historyMissing = (story?.total ?? available.length) > available.length;

  // Navigation remounts this component and invalidates pending history reads.
  useEffect(() => () => { request.current += 1; }, []);

  useLayoutEffect(() => {
    const node = scroller.current;
    const last = previous.current;
    const ids = new Set(events.map(event => event.id));
    const silent = !last || last.generation !== generation || last.session !== session || (story?.sequence ?? 0) < last.sequence;
    const added = silent ? [] : (story?.events ?? []).filter(event => !last.ids.has(event.id) && event.availableSequence > last.sequence);
    setFresh(new Set(added.map(event => event.id)));
    if (silent) setUnseen(0);
    else if (node && node.scrollTop > 8 && added.length) {
      node.scrollTop += Math.max(0, node.scrollHeight - last.height);
      setUnseen(value => value + added.length);
    }
    previous.current = { ids, generation, height: node?.scrollHeight ?? 0, sequence: story?.sequence ?? 0, session };
  }, [events, generation, story?.sequence, story?.events, session]);

  async function loadEarlier() {
    if (!story || !session || loading) return;
    const token = ++request.current;
    setLoading(true);
    setError(null);
    try {
      const adjustedOffset = older.length && hasMore ? Math.max(0, offset + (story.total ?? pageTotal) - pageTotal) : story.events.length;
      const page = await slipstreamApi.story(session, story.sequence, adjustedOffset, recordingVersion);
      if (request.current !== token) return;
      setOlder(value => [...value, ...page.events]);
      setOffset(page.nextOffset ?? offset + page.events.length);
      setPageTotal(page.total ?? story.total ?? 0);
      setHasMore(!!page.hasMore);
    } catch (failure) {
      if (request.current === token) setError(failure instanceof Error ? failure.message : "Earlier activity is unavailable.");
    } finally {
      if (request.current === token) setLoading(false);
    }
  }

  return <section className={`story-feed${compact ? " story-feed--compact" : ""}`} aria-label="Session activity">
    <header className="story-feed-heading"><span>THE STORY SO FAR</span><div className="story-filters" aria-label="Activity filter">
      {(["all", "highlights", "following"] as const).map(value => <button type="button" key={value} aria-pressed={filter === value} disabled={value === "following" && !driverNumber} onClick={() => setFilter(value)}>{value === "all" ? "Everything" : value === "following" ? "Following" : "Highlights"}</button>)}
    </div></header>
    <div className="story-scroll" ref={scroller} onScroll={() => { if ((scroller.current?.scrollTop ?? 0) < 8) setUnseen(0); }}>
      {unseen > 0 && <button type="button" className="story-new" onClick={() => { scroller.current?.scrollTo({ top: 0, behavior: "instant" }); setUnseen(0); }}>{unseen} new ↑</button>}
      <ol className="story-list">{events.map(event => <li key={event.id} className={`story-item story-kind-${event.kind.toLowerCase()}${fresh.has(event.id) ? " story-is-new" : ""}`}>
        <button type="button" className="story-inspect" aria-expanded={openId === event.id} onClick={() => setOpenId(openId === event.id ? null : event.id)}>
          <span className="story-time">{storyStamp(event)}</span><span className="story-body"><span className="story-tag">{event.kind.replaceAll("_", " ")}{event.state === "provisional" && <i> · PROVISIONAL</i>}</span><strong>{event.title}</strong>{event.detail && <span className="story-detail">{event.detail}</span>}</span><span className="story-expand" aria-hidden="true">{openId === event.id ? "−" : "+"}</span>
        </button>
        {openId === event.id && <div className="story-facts">
          <dl><div><dt>Happened</dt><dd>{event.occurredAt.slice(11, 19)} UTC</dd></div><div><dt>Known</dt><dd>{event.availableAt.slice(11, 19)} UTC</dd></div><div><dt>Status</dt><dd>{event.state}</dd></div>{event.cause && <div><dt>Context</dt><dd>{event.cause.replaceAll("_", " ").toLowerCase()}</dd></div>}</dl>
          {mode === "replay" && onReplay ? <button className="story-replay" type="button" onClick={() => onReplay(event)}>Replay this moment ▸</button> : <p className="story-live-note">Live activity becomes replayable when the recording is available.</p>}
        </div>}
      </li>)}</ol>
      {!events.length && <p className="story-empty">{filter === "following" ? "No activity for your followed driver yet." : "The story starts here. Moments appear as they become known."}</p>}
      {historyMissing && mode === "replay" && <button className="story-earlier" type="button" disabled={loading} onClick={loadEarlier}>{loading ? "Loading…" : "Load earlier activity"}</button>}
      {error && <p role="status" className="story-empty">{error}</p>}
    </div>
  </section>;
}
