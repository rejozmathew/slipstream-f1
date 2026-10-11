import { useEffect, useRef, useState, type CSSProperties } from "react";

import { driverLifecycle } from "../../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, QualifyingIntelligence, RaceState } from "../../domain/protocol";
import { CompoundBadge } from "../shared/CompoundBadge";
import { Panel } from "../shared/Panel";
import { availableStoryEvents, describeStory, storyStamp, storyTeamStyle } from "../story/presentation";

import "./nonrace.css";

type TimedProps = {
  state: RaceState;
  analytics?: AnalyticsSnapshot | null;
  onSelectDriver?: (driverNumber: string) => void;
  followedDriverNumber?: string | null;
};
type TimedRow = { driver: Driver; best: string | null; gap: number | null; onTrack: boolean; cutState: string };

const seconds = (time: string | null | undefined) => {
  if (!time || !/^\d+:\d{2}\.\d{3}$/.test(time)) return null;
  const [minutes, remainder] = time.split(":").map(Number);
  return minutes * 60 + remainder;
};
const delta = (value: number) => `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(3)}`;

export function timedSessionRows(state: RaceState, analytics?: AnalyticsSnapshot | null): TimedRow[] {
  const qualifying = state.session.layout_family === "qualifying";
  const intelligence = analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null;
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  return drivers.map(driver => {
    const q = qualifying ? intelligence?.drivers[driver.number] : null;
    const lifecycle = driverLifecycle(driver);
    // Segment timing is authoritative. Earlier-segment bests cannot fill a blank.
    const best = qualifying ? q?.scopeBest ?? null : driver.best_lap;
    const sourceDelta = driver.best_lap_delta_to_leader;
    const gap = qualifying ? q?.benchmarkDelta ?? null : driver.position === 1 && best ? 0 : sourceDelta != null && /^\+?\d+(?:\.\d+)?$/.test(sourceDelta) ? Number(sourceDelta) : null;
    const eliminated = qualifying && (q?.cutState === "ELIMINATED" || driver.qualifying_eliminated === true);
    return { driver, best, gap, cutState: q?.cutState ?? "UNKNOWN", onTrack: !eliminated && !lifecycle.terminal && !lifecycle.stopped && !lifecycle.retiredIndicated && !lifecycle.inPit && (q?.activity ?? driver.activity) === "ON_TRACK" };
  });
}

function activeRows(rows: TimedRow[]) {
  return rows.filter(row => {
    const lifecycle = driverLifecycle(row.driver);
    return row.cutState !== "ELIMINATED" && row.driver.qualifying_eliminated !== true && (!lifecycle.terminal || lifecycle.status === "FINISHED") && !lifecycle.stopped && !lifecycle.retiredIndicated;
  });
}

type LabelItem = { key: string; x: number; priority: number; focus: boolean; label: string };
type LabelPlacement = { show: boolean; count: number; lane: number; shift: number };
/** Pack the reference's marker clusters and label lanes at the rendered width. */
export function packSpreadLabels(items: LabelItem[], width: number, tv = false, scale = 1) {
  const font = (tv ? 17 : 11) * scale, dot = (tv ? 18 : 12) * scale;
  const groups: Array<{ x: number; members: LabelItem[] }> = [];
  for (const item of [...items].sort((a, b) => a.x - b.x)) {
    const group = groups.at(-1);
    if (group && item.x - group.x < dot * .75) group.members.push(item);
    else groups.push({ x: item.x, members: [item] });
  }
  const packed = groups.map(group => ({ ...group, lead: [...group.members].sort((a, b) => Number(b.focus) - Number(a.focus) || a.priority - b.priority)[0] }));
  const result = new Map<string, LabelPlacement>();
  const lanes: Array<Array<[number, number]>> = Array.from({ length: tv ? 4 : 3 }, () => []);
  for (const group of packed.sort((a, b) => Number(b.lead.focus) - Number(a.lead.focus) || a.lead.priority - b.lead.priority)) {
    for (const item of group.members) result.set(item.key, { show: item === group.lead, count: item === group.lead ? group.members.length : 0, lane: -1, shift: 0 });
    const labelWidth = font * .7 * (group.lead.label.length + 1) + (group.members.length > 1 ? font * 1.2 : 0);
    const initial = group.lead.x - labelWidth / 2;
    const left = Math.max(0, Math.min(width - labelWidth, initial)), right = left + labelWidth;
    const lane = lanes.findIndex(intervals => intervals.every(([a, b]) => right + font * .4 <= a || left - font * .4 >= b));
    if (lane >= 0) { lanes[lane].push([left, right]); Object.assign(result.get(group.lead.key)!, { lane, shift: left - initial }); }
  }
  return result;
}

export function BestLapSpread({ state, analytics, onSelectDriver, followedDriverNumber, tv = false }: TimedProps & { tv?: boolean }) {
  const plot = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: tv ? 900 : 600, scale: 1 });
  useEffect(() => {
    if (!plot.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const node = plot.current;
      if (node) setDimensions({ width: node.clientWidth || 600, scale: parseFloat(getComputedStyle(node).fontSize) || 1 });
    });
    observer.observe(plot.current);
    return () => observer.disconnect();
  }, []);
  const qualifying = state.session.layout_family === "qualifying";
  const intelligence = analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null;
  const rows = activeRows(timedSessionRows(state, analytics));
  const timed = rows.filter(row => row.gap != null && row.gap >= 0);
  const spread = Math.max(0, ...timed.map(row => row.gap!));
  const span = [.5, 1, 1.5, 2, 3, 4, 6, 10].find(value => value >= spread * 1.04) ?? Math.ceil(spread * 1.04 / 5) * 5;
  const tick = span <= 1 ? .25 : span <= 2 ? .5 : span <= 4 ? 1 : span <= 10 ? 2 : span / 5;
  const ticks = Array.from({ length: Math.floor(span / tick) + 1 }, (_, index) => index * tick);
  const placements = packSpreadLabels(timed.map((row, index) => ({ key: row.driver.number, x: row.gap! / span * dimensions.width, priority: index, focus: row.driver.number === followedDriverNumber, label: row.driver.code ?? row.driver.number })), dimensions.width, tv, dimensions.scale);
  const cutoff = qualifying && intelligence?.cutLine.status === "AVAILABLE" ? rows.find(row => row.driver.number === intelligence.cutLine.cutoff?.driverNumber) : null;
  const cutX = cutoff?.gap != null ? cutoff.gap / span * 100 : null;
  const phase = intelligence?.phase !== "UNKNOWN" ? intelligence?.phase : null;
  return <div className={`nonrace-spread${tv ? " nonrace-spread-tv" : ""}`}>
    <header className="nr-spread-heading"><b>{qualifying ? `${phase ? `${phase} ` : ""}SPREAD` : "BEST-LAP SPREAD"}</b><span>{qualifying ? "best lap in this segment" : "best lap this session"} · gap to P1{qualifying && intelligence?.cutLine.advancePosition ? ` · top ${intelligence.cutLine.advancePosition} go through` : ""}</span></header>
    <div className="nr-spread-plot" ref={plot} aria-label="Best lap gap to session benchmark">
      {cutX != null && <><div className="nr-spread-drop" style={{ left: `${cutX}%` }} /><div className="nr-spread-cut" style={{ left: `${cutX}%` }}><span>CUT · P{intelligence?.cutLine.advancePosition}</span></div></>}
      <div className="nr-spread-axis">{ticks.map(value => <span key={value} style={{ left: `${value / span * 100}%` }}><em>{value === 0 ? "P1" : `+${value.toFixed(value < 1 ? 2 : 1)}`}</em></span>)}</div>
      <div className="nr-spread-cars">{timed.map(row => {
        const placement = placements.get(row.driver.number)!;
        if (!placement.show) return null;
        return <button type="button" key={row.driver.number} className={`nr-spread-car${row.onTrack ? " is-ontrack" : ""}${row.cutState === "BELOW_CUT" ? " is-drop" : ""}${row.driver.number === followedDriverNumber ? " is-focus" : ""}${placement.lane < 0 ? " no-label" : ""}`} style={{ ...storyTeamStyle(row.driver), left: `${row.gap! / span * 100}%`, "--lane": Math.max(0, placement.lane), "--shift": `${placement.shift}px` } as CSSProperties} aria-label={`${row.driver.code ?? row.driver.number}, ${delta(row.gap!)}${placement.count > 1 ? `, ${placement.count} cars here` : ""}`} onClick={() => onSelectDriver?.(row.driver.number)}><i /><s /><b>{row.driver.code ?? row.driver.number}{placement.count > 1 && <em>{placement.count}</em>}</b></button>;
      })}</div>
    </div>
    <div className="nr-spread-none">{rows.some(row => row.best == null) && <><b>NO TIME YET</b>{rows.filter(row => row.best == null).map(row => <button key={row.driver.number} style={storyTeamStyle(row.driver)} onClick={() => onSelectDriver?.(row.driver.number)}>{row.driver.code ?? row.driver.number}</button>)}</>}</div>
  </div>;
}

export function OnTrackNow({ state, analytics, onSelectDriver, maximum = 12 }: TimedProps & { maximum?: number }) {
  const rows = timedSessionRows(state, analytics).filter(row => row.onTrack);
  const qualifying = state.session.layout_family === "qualifying";
  return <section className="nr-ontrack"><header className="nr-list-heading"><span>ON TRACK NOW · {qualifying ? "BEST THIS SEGMENT" : "SESSION BEST"}</span><b>{rows.length}</b></header><ol className="nr-ontrack-list">{rows.slice(0, maximum).map(row => <li key={row.driver.number}><button style={storyTeamStyle(row.driver)} onClick={() => onSelectDriver?.(row.driver.number)}><span className="nr-position">P{row.driver.position ?? "—"}</span><i className="nr-team" /><b>{row.driver.code ?? row.driver.number}</b><span className="nr-tyre"><CompoundBadge compound={row.driver.compound} compact /><em>{row.driver.tyre_age ?? "—"}</em></span><span className="nr-best">{row.best ?? "no time"}</span>{row.cutState === "BELOW_CUT" && analytics?.qualifying?.settlement !== "SOURCE_COMPLETE" && <small>AT RISK</small>}</button></li>)}</ol>{!rows.length && <p className="nr-empty">No cars currently reported on track</p>}</section>;
}

export function AroundCut({ state, analytics, onSelectDriver, tv = false, phone = false }: TimedProps & { tv?: boolean; phone?: boolean }) {
  const intelligence = analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null;
  const rows = activeRows(timedSessionRows(state, analytics));
  const advance = intelligence?.cutLine.advancePosition;
  const cutoff = intelligence?.cutLine.status === "AVAILABLE" ? intelligence.cutLine.cutoff : null;
  const cutoffBest = cutoff ? intelligence?.drivers[cutoff.driverNumber]?.scopeBest : null;
  const cutoffGap = cutoff ? intelligence?.drivers[cutoff.driverNumber]?.benchmarkDelta : null;
  const cutoffSeconds = seconds(cutoffBest);
  const selected = advance ? rows.slice(Math.max(0, advance - (tv ? 2 : 3)), advance + (tv ? 4 : 3)) : rows.slice(0, phone ? 10 : 6);
  const poleSegment = intelligence && ["Q3", "SQ3"].includes(intelligence.phase);
  return <section className="nr-cut"><header className="nr-list-heading"><span>{advance ? `${phone ? "" : "AROUND THE CUT · "}TOP ${advance} GO THROUGH` : poleSegment ? "FIGHT FOR POLE" : "SEGMENT TIMES"}</span>{advance && <b>{cutoffBest ?? "—"}</b>}</header><ol className="nr-zone-list">{selected.map(row => {
    const lap = seconds(row.best);
    const difference = advance ? row.gap != null && cutoffGap != null ? row.gap - cutoffGap : lap != null && cutoffSeconds != null ? lap - cutoffSeconds : null : row.gap;
    return <li key={row.driver.number}><button className={`${row.onTrack ? "is-ontrack " : ""}${row.cutState === "BELOW_CUT" ? "is-risk" : row.cutState === "ADVANCING" ? "is-safe" : "is-top"}`} style={storyTeamStyle(row.driver)} onClick={() => onSelectDriver?.(row.driver.number)}><span>P{row.driver.position ?? "—"}</span><i className="nr-team" /><b>{row.driver.code ?? row.driver.number}</b><span>{row.best ?? "NO TIME"}</span><em>{difference == null ? "" : advance && row.driver.number === cutoff?.driverNumber ? "SETS CUT" : !advance && difference === 0 ? (poleSegment ? "PROVISIONAL P1" : "P1 TIME") : delta(difference)}</em></button></li>;
  })}</ol>{!selected.length && <p className="nr-empty">Segment timing unavailable at this moment</p>}</section>;
}

export function SessionLog({ state, analytics, maximum = 7 }: TimedProps & { maximum?: number }) {
  const events = availableStoryEvents(analytics?.story).filter(event => ["SESSION_BEST", "FLAG", "STOPPED"].includes(event.kind) || ["LAP_IMPROVEMENT", "IMPROVEMENT"].includes(event.kind) && (event.data.sessionBest === true || typeof event.data.position === "number" && event.data.position <= 10)).slice(-maximum).reverse();
  return <section className="nr-session-log"><header className="nr-list-heading"><span>SESSION LOG</span></header><ol className="nr-zone-log">{events.map(event => {
    const description = describeStory(event, state.drivers, state.session);
    return <li key={event.id} className={`nr-tone-${description.tone}`}><time>{storyStamp(event, state.session)}</time><i /><b>{description.tag}</b><span title={description.title}>{description.title}</span></li>;
  })}</ol>{!events.length && <p className="nr-empty">Quiet so far</p>}</section>;
}

export function TimedSessionSummary({ intelligence, state }: { intelligence?: QualifyingIntelligence | null; state?: RaceState }) {
  const practice = state?.session.layout_family === "practice";
  const phaseKnown = intelligence?.phase && intelligence.phase !== "UNKNOWN";
  const fastest = practice ? timedSessionRows(state).find(row => row.gap === 0 && row.best) : null;
  const cells = practice ? [["REMAINING", state.session.session_clock ?? "—"], ["FASTEST", fastest ? `${fastest.driver.code ?? fastest.driver.number} ${fastest.best}` : "—"], ["ON TRACK", String(timedSessionRows(state).filter(row => row.onTrack).length)]] : [
    ["SEGMENT", phaseKnown ? intelligence.phase : "—"],
    ["TIME LEFT", phaseKnown ? intelligence.sessionClock ?? "—" : "—"],
    ["FASTEST", intelligence?.benchmark ? `${intelligence.benchmark.code ?? intelligence.benchmark.driverNumber} ${intelligence.benchmark.lapTime}` : "—"],
    ["ADVANCE", phaseKnown && intelligence.cutLine.advancePosition ? `TOP ${intelligence.cutLine.advancePosition}` : phaseKnown && ["Q3", "SQ3"].includes(intelligence.phase) ? "POLE SHOOTOUT" : "—"],
  ];
  return <div className="nr-session-summary"><div className="qualifying-session-grid">{cells.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>{intelligence?.settlement === "SETTLING" && <p className="qualifying-evidence-note">{intelligence.phase} FLAG · LAPS FINISHING</p>}{intelligence?.settlement === "SOURCE_COMPLETE" && <p className="qualifying-evidence-note">CLASSIFICATION · PROVISIONAL</p>}{intelligence?.phase === "UNKNOWN" && <p className="qualifying-evidence-note">SEGMENT TIMING WAS NOT RECORDED FOR THIS REPLAY</p>}</div>;
}

export function TimedSessionPanel(props: TimedProps) {
  const qualifying = props.state.session.layout_family === "qualifying";
  return <Panel eyebrow={qualifying ? "THIS SEGMENT" : "THIS SESSION"} title={qualifying ? "Cut line" : "Best-lap spread"} className="nr-spread-panel"><div className="nr-panel-body"><BestLapSpread {...props} /><div className="nr-feature-columns">{qualifying ? <AroundCut {...props} /> : <SessionLog {...props} />}<OnTrackNow {...props} /></div></div></Panel>;
}

export function NonRaceTVFeature(props: TimedProps) {
  return <div className="nonrace-tv-feature"><div className="nr-tv-ladder"><BestLapSpread {...props} tv /></div><div className="nr-feature-columns"><OnTrackNow {...props} maximum={9} />{props.state.session.layout_family === "qualifying" ? <AroundCut {...props} tv /> : <SessionLog {...props} />}</div></div>;
}
