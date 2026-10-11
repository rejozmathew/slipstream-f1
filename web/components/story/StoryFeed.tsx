import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { StoryEvent, StorySnapshot } from "../../domain/protocol";
import { slipstreamApi } from "../../api/client";
import { availableStoryEvents, describeStory, storyDriverCode, storyLocalTime, storyStamp, storyTeamStyle, type StoryDrivers, type StoryPosture, type StorySession } from "./presentation";
import "./story.css";

export { storyStamp } from "./presentation";
export type StoryFilter = "all" | "highlights" | "following";
export type StoryProps = {
  sessionKey?: string | null;
  story?: StorySnapshot | null;
  mode: "live" | "replay";
  generation?: number;
  driverNumber?: string | null;
  onReplay?: (event: StoryEvent) => void;
  compact?: boolean;
  recordingVersion?: string | null;
  drivers?: StoryDrivers;
  session?: StorySession;
  posture?: StoryPosture;
  visible?: boolean;
};

type FeedProps = StoryProps & { header?: boolean; filter?: StoryFilter; onFilterChange?: (filter: StoryFilter) => void; allowFollowing?: boolean };

export function StoryFeed(props: FeedProps) {
  return <StoryFeedContent key={`${props.sessionKey ?? props.story?.events[0]?.sessionKey ?? "empty"}:${props.generation ?? 0}:${props.recordingVersion ?? ""}`} {...props} />;
}

function StoryFeedContent({ story, sessionKey, mode, generation = 0, driverNumber, onReplay, compact = false, recordingVersion, drivers = {}, session: sessionState, posture = "desktop", visible = true, header = true, filter: controlledFilter, onFilterChange, allowFollowing = false }: FeedProps) {
  const [internalFilter, setInternalFilter] = useState<StoryFilter>("highlights");
  const filter = controlledFilter ?? internalFilter;
  const [expanded, setExpanded] = useState(false);
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
  const previous = useRef<{ ids: Set<string>; generation: number; height: number; sequence: number; session: string | null | undefined; filter: StoryFilter } | null>(null);
  const onScreen = useRef(true);
  const request = useRef(0);
  const session = sessionKey ?? story?.events[0]?.sessionKey;
  // Keep every page the viewer has seen when the compact server window rolls
  // forward. Navigation remounts this component, bounding retention by visit.
  if (previousWindow !== story) {
    setPreviousWindow(story);
    setOlder(value => [...new Map([...value, ...(previousWindow?.events ?? [])].map(event => [event.id, event])).values()]);
  }
  const available = useMemo(() => {
    return availableStoryEvents(story, older);
  }, [older, story]);
  const events = useMemo(() => available
      .filter(event => filter === "all" || (filter === "highlights" ? event.priority >= 2 : !!driverNumber && event.driverNumbers.includes(driverNumber)))
      .sort((a, b) => Date.parse(b.availableAt) - Date.parse(a.availableAt) || b.availableSequence - a.availableSequence),
    [available, filter, driverNumber]);
  const historyMissing = (story?.total ?? available.length) > available.length;

  // Navigation remounts this component and invalidates pending history reads.
  useEffect(() => () => { request.current += 1; }, []);
  useEffect(() => {
    const reset = () => { previous.current = null; setFresh(new Set()); setUnseen(0); };
    const visibility = () => { onScreen.current = document.visibilityState !== "hidden"; reset(); };
    document.addEventListener("visibilitychange", visibility);
    const observer = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(entries => {
      const shown = entries[0]?.isIntersecting ?? true;
      if (shown !== onScreen.current) { onScreen.current = shown; reset(); }
    });
    if (scroller.current) observer?.observe(scroller.current);
    return () => { document.removeEventListener("visibilitychange", visibility); observer?.disconnect(); };
  }, []);

  useLayoutEffect(() => {
    const node = scroller.current;
    const last = previous.current;
    const ids = new Set(events.map(event => event.id));
    const silent = !last || !visible || !onScreen.current || last.filter !== filter || last.generation !== generation || last.session !== session || (story?.sequence ?? 0) < last.sequence;
    const added = silent ? [] : events.filter(event => !last.ids.has(event.id) && event.availableSequence > last.sequence);
    setFresh(new Set(added.map(event => event.id)));
    if (silent) setUnseen(0);
    else if (node && node.scrollTop > 8 && added.length) {
      node.scrollTop += Math.max(0, node.scrollHeight - last.height);
      setUnseen(value => value + added.length);
    }
    previous.current = { ids, generation, height: node?.scrollHeight ?? 0, sequence: story?.sequence ?? 0, session, filter };
  }, [events, generation, story?.sequence, story?.events, session, filter, visible]);

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

  return <section className={`story-feed story-feed--${posture}${compact ? " story-feed--compact" : ""}${expanded ? " is-expanded" : ""}`} aria-label="Session activity">
    {header && <header className="story-feed-heading"><div className="story-heading"><span>NEW · WHAT CHANGED</span><h2>Story</h2></div><div className="story-filters" aria-label="Activity filter">
      {(["highlights", "all", ...(allowFollowing ? ["following"] as const : [])] as StoryFilter[]).map(value => <button type="button" key={value} aria-pressed={filter === value} disabled={value === "following" && !driverNumber} onClick={() => { setInternalFilter(value); onFilterChange?.(value); }}>{value === "all" ? "EVERYTHING" : value === "following" ? "FOLLOWING" : "HIGHLIGHTS"}</button>)}
    </div></header>}
    <div className="story-scroll" ref={scroller} onScroll={() => { if ((scroller.current?.scrollTop ?? 0) < 8) setUnseen(0); }}>
      {unseen > 0 && <button type="button" className="story-new fd-newpill" onClick={() => { scroller.current?.scrollTo({ top: 0, behavior: "instant" }); setUnseen(0); }}>{unseen} new ↑</button>}
      <ol className="story-list fd-list">{events.map(event => {
        const description = describeStory(event, drivers, sessionState);
        const open = openId === event.id;
        const past = event.kind === "BATTLE" && sessionState?.lap != null && event.lap != null && event.lap < sessionState.lap - 1;
        const lag = Math.max(0, (Date.parse(event.availableAt) - Date.parse(event.occurredAt)) / 1000);
        return <li key={event.id} style={storyTeamStyle(drivers[event.driverNumbers[0]])} className={`story-item fd-item tone-${description.tone} story-kind-${event.kind.toLowerCase()}${event.priority >= 2 ? " is-hl" : ""}${fresh.has(event.id) ? " story-is-new is-new" : ""}${past ? " is-past" : ""}${open ? " is-open" : ""}`}>
          <button type="button" className="story-inspect" aria-expanded={open} onClick={() => setOpenId(open ? null : event.id)}>
            <span className="story-time fd-time mono">{storyStamp(event, sessionState)}</span>
            <span className="story-tag fd-tag">{description.tag}{past && <i className="fd-pastlbl">EARLIER</i>}{event.state === "provisional" && <i className="fd-prov">PROVISIONAL</i>}</span>
            <span className="story-body fd-text"><strong>{description.title}</strong>{description.detail && <em className="story-detail">{description.detail}</em>}</span>
          </button>
          {open && <div className="story-facts fd-more">
            <dl className="fd-facts"><div><dt>Happened</dt><dd className="mono">{storyLocalTime(event.occurredAt, sessionState)}</dd></div>{lag >= 1 && <div><dt>Known</dt><dd className="mono">{storyLocalTime(event.availableAt, sessionState)} · {Math.round(lag)} s later</dd></div>}<div><dt>Status</dt><dd>{event.state.toUpperCase()}</dd></div></dl>
            {!!event.driverNumbers.length && <div className="fd-who">{event.driverNumbers.slice(0, 6).map(number => <span key={number} className="fd-drv" style={storyTeamStyle(drivers[number])}><i />{storyDriverCode(number, drivers)}</span>)}</div>}
            {mode === "replay" && onReplay ? <button className="story-replay fd-act" type="button" onClick={() => onReplay(event)}>REPLAY FROM {storyStamp(event, sessionState) || "HERE"} ▸</button> : <p className="story-live-note fd-livenote">Live has no rewind. This moment becomes replayable once the session is recorded.</p>}
          </div>}
        </li>;
      })}</ol>
      {!events.length && <p className="story-empty fd-empty">{filter === "following" ? "No activity for your followed driver yet." : "Nothing yet — events appear here as they become known."}</p>}
      {historyMissing && mode === "replay" && <button className="story-earlier" type="button" disabled={loading} onClick={loadEarlier}>{loading ? "Loading…" : "Load earlier activity"}</button>}
      {error && <p role="status" className="story-empty">{error}</p>}
    </div>
    <button className="story-more" type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? "SHOW LESS" : "SHOW MORE"}</button>
  </section>;
}
