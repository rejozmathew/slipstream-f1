import { useEffect, useMemo, useRef, useState } from "react";
import type React from "react";

import { PaceDeltaChart } from "../components/analysis/PaceDeltaChart";
import { DriverPirelliContext, PirelliBaseline, PirelliNomination, RaceNow } from "../components/analysis/PublishedStrategy";
import { TrackMap } from "../components/analysis/TrackMap";
import { CompoundBadge, CompoundSequence, CompoundTransition } from "../components/shared/CompoundBadge";
import { RailTransition } from "../components/shared/RailTransition";
import { BrandMark } from "../components/shared/Brand";
import { SessionProgress } from "../components/shared/SessionProgress";
import { TimingTower } from "../components/timing/TimingTower";
import { completedLapGapTrend, currentPairGap } from "../domain/battle";
import { driverLifecycle } from "../domain/lifecycle";
import { actualStrategyCompounds, driverPirelliReferenceRows, driverPirelliStopWindowsText, driverStrategyRelationship, dryTyreRequirementText, NO_SPECIFIC_PIRELLI_STRATEGY } from "../domain/pirelliPresentation.mjs";
import type { AnalyticsSnapshot, Driver, PositionMode, ViewingMode, RaceState, SessionKind, ReplayCommand, StoryEvent } from "../domain/protocol";
import type { SessionLayout } from "../domain/sessionLayout";
import { nextAuthoredState } from "../domain/tvMode.mjs";
import type { TVPreferences, TVStatePreference } from "../hooks/useProductPreferences";

type TVState = TVStatePreference;
const stateSets: Record<Exclude<SessionLayout, "unsupported">, TVState[]> = {
  race: ["track", "battle", "strategy", "result", "driver", "tower"],
  qualifying: ["tower"],
  practice: ["tower"],
};
function hasRenderableCarPositions(drivers: Driver[], positionMode: PositionMode) {
  return positionMode !== "unavailable" && drivers.some((driver) => positionMode === "precise_xy" ? driver.x != null && driver.y != null : driver.track_position != null);
}

function statusTone(status?: string | null) {
  const value = status?.toLowerCase() ?? "unknown";
  if (value.includes("chequered") || value.includes("checkered")) return "chequered";
  if (value.includes("red")) return "red";
  if (value.includes("sc") || value.includes("safety") || value.includes("vsc")) return "safety";
  if (value.includes("yellow")) return "yellow";
  if (value.includes("green") || value.includes("clear")) return "green";
  return "unknown";
}

function DriverTV({ driver, analytics, state, positionMode, viewingMode }: {
  driver: Driver | null;
  analytics: AnalyticsSnapshot | null;
  state: RaceState;
  positionMode: PositionMode; viewingMode: ViewingMode;
}) {
  const model = driver ? analytics?.drivers[driver.number] : null;
  const samples = model?.pace.samples.slice(-22) ?? [];
  const latestPit = model?.pitEvents.at(-1) ?? null;
  if (!driver) return <div className="unknown-block"><strong>DRIVER · NOT AVAILABLE</strong><p>No classified driver is available at this cursor.</p></div>;
  const lifecycle = driverLifecycle(driver);
  return <div className="tv-driver-state">
    <header style={{ borderColor: `#${driver.team_colour ?? "77808f"}` }}><div><span>DRIVER</span><strong>#{driver.number}</strong></div><div><h2>{driver.name ?? driver.code ?? driver.number}</h2><p>{driver.team ?? "Team unavailable"}</p>{lifecycle.label && <span className="driver-status-badge terminal">{lifecycle.label}</span>}</div><b>P{driver.position ?? "—"}</b></header>
    <div className="tv-driver-zones">
      <section className="tv-driver-facts"><h3>DRIVER STATE</h3><div><span>AHEAD</span><strong>{model?.ahead?.code ?? "—"}</strong><small>{model?.ahead?.gapSeconds == null ? "—" : `${model.ahead.gapSeconds.toFixed(3)}s`}</small></div><div><span>BEHIND</span><strong>{model?.behind?.code ?? "—"}</strong><small>{model?.behind?.gapSeconds == null ? "—" : `${model.behind.gapSeconds.toFixed(3)}s`}</small></div><div><span>TYRE / AGE</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</strong></div><div><span>STINT / PITS</span><strong>{driver.stint_laps ?? "—"}L · {driver.pit_count}</strong></div><div><span>LAST / BEST</span><strong>{driver.last_lap ?? "—"} · {driver.best_lap ?? "—"}</strong></div>{latestPit && <div><span>LATEST PIT · L{latestPit.lap}</span><strong><CompoundTransition from={latestPit.previousCompound} to={latestPit.newCompound} compact /></strong><small>STOP {model?.pitEvents.length ?? driver.pit_count} · STATIONARY {latestPit.stopDuration == null ? "—" : `${latestPit.stopDuration.toFixed(1)}s`} · PIT LANE {latestPit.pitLaneDuration == null ? "—" : `${latestPit.pitLaneDuration.toFixed(1)}s`}</small></div>}<div className="tv-driver-read"><span>DRIVER READ</span><strong>{model?.read.headline ?? "Driver read not available yet."}</strong>{model?.read.facts.slice(0, 2).map((fact) => <small key={fact}>{fact}</small>)}</div></section>
      <div className="tv-driver-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} viewingMode={viewingMode} focusedDriverNumbers={[driver.number]} focusLabel={`${driver.code ?? driver.number} · FOCUS`} /></div>
      <div className="tv-driver-analysis"><section className="tv-driver-pace"><h3>PACE TREND</h3><PaceDeltaChart samples={samples} compact serverScale={model?.pace.scale} /></section><DriverPirelliContext analytics={analytics} driver={driver} compact /></div>
    </div>
  </div>;
}

function BattleCard({ driver, analytics }: { driver: Driver; analytics: AnalyticsSnapshot | null }) {
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  const baseline = analytics?.publishedStrategy?.baseline;
  const showPublished = baseline?.status === "PRESENT";
  const hasPublishedStrategy = showPublished && baseline.options.length > 0;
  const references = driverPirelliReferenceRows(baseline, published);
  const dryRule = dryTyreRequirementText(published);
  return <section className="tv-battle-card" style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as React.CSSProperties}><header><b>P{driver.position ?? "—"}</b><strong>{driver.code ?? driver.number}</strong><span>#{driver.number}</span></header><p>{driver.name ?? "Driver"} · {driver.team ?? "Team unavailable"}</p><div><span>TYRE / AGE · PIT VISITS</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`} · {driver.pit_count}</strong></div><div><span>ACTUAL TYRE STRATEGY</span><strong><CompoundSequence compounds={actualStrategyCompounds(published)} /></strong></div>{dryRule && <div><span>DRY RULE</span><strong>{dryRule}</strong></div>}{hasPublishedStrategy ? <><div><span>PIRELLI TYRE STRATEGY</span><strong className="strategy-pirelli-options">{references.map((reference) => <CompoundSequence key={reference.id} compounds={reference.compounds} ordered={reference.ordered} />)}</strong><small>{driverStrategyRelationship(baseline, published)}</small></div><div><span>PUBLISHED STOP WINDOW</span><strong>{driverPirelliStopWindowsText(baseline, published, false)}</strong></div></> : showPublished && <><div><span>PIRELLI TYRE STRATEGY</span><strong>{NO_SPECIFIC_PIRELLI_STRATEGY}</strong></div><PirelliNomination baseline={baseline} /></>}</section>;
}

function TVBattle({ drivers, analytics, mode, state, positionMode, viewingMode }: {
  drivers: readonly [Driver | undefined, Driver | undefined] | null;
  analytics: AnalyticsSnapshot | null;
  mode: string;
  state: RaceState;
  positionMode: PositionMode; viewingMode: ViewingMode;
}) {
  const left = drivers?.[0] ?? null;
  const right = drivers?.[1] ?? null;
  if (!left || !right) return <div className="unknown-block"><strong>BATTLE · NOT AVAILABLE</strong><p>No adjacent comparable pair is available.</p></div>;
  const gap = currentPairGap(analytics, left, right);
  const historyKey = `${left.number}:${right.number}`;
  const reverseKey = `${right.number}:${left.number}`;
  const history = analytics?.battle.histories?.[historyKey] ?? analytics?.battle.histories?.[reverseKey] ?? [];
  const trend = completedLapGapTrend(history);
  return <div className="tv-battle"><header><span>{mode.toUpperCase()} BATTLE</span><strong>{left.code ?? left.number} · {gap == null ? "—" : `${gap.toFixed(3)}s`} · {right.code ?? right.number}</strong></header><div className="tv-battle-grid"><BattleCard driver={left} analytics={analytics} /><div className="tv-battle-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} viewingMode={viewingMode} focusedDriverNumbers={[left.number, right.number]} focusLabel={`${left.code ?? left.number} ↔ ${right.code ?? right.number}`} /><div className="tv-battle-trend"><span>COMPLETED-LAP TREND</span><strong>{trend.label}</strong><small>{trend.delta == null ? `${trend.sampleCount} SAMPLES` : `${trend.delta > 0 ? "+" : ""}${trend.delta.toFixed(3)}s · ${trend.sampleCount} LAPS`}</small></div></div><BattleCard driver={right} analytics={analytics} /></div></div>;
}

export function TVModeView({ state, analytics, recommendedBattle, sessionLayout, sessionKind, replayAvailable, positionMode, viewingMode, sectorTimingAvailable, preferences, onPreferencesChange, onExit, exitLabel = "EXIT TV", controls, onCommand, canCommand, isPlaying = false, speed = 10, delaySeconds = 0, navigationGeneration = 0, ticker, moments, onReplayMoment, notice, livePhase, intervalsAvailable = false }: {
  state: RaceState; analytics: AnalyticsSnapshot | null; recommendedBattle: [string, string] | null;
  sessionLayout: SessionLayout; sessionKind: SessionKind; replayAvailable: boolean;
  positionMode: PositionMode; viewingMode: ViewingMode; sectorTimingAvailable: boolean; intervalsAvailable?: boolean;
  preferences: TVPreferences; onPreferencesChange: (value: TVPreferences) => void; onExit: () => void; exitLabel?: string;
  controls?: React.ReactNode; onCommand?: (command: ReplayCommand) => boolean; canCommand?: (command: ReplayCommand) => boolean;
  isPlaying?: boolean; speed?: number; delaySeconds?: number; navigationGeneration?: number; ticker?: React.ReactNode; moments?: React.ReactNode; onReplayMoment?: (event: StoryEvent) => void; notice?: string | null; livePhase?: string;
}) {
  const layout = sessionLayout;
  const root = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [viewport, setViewport] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));
  const [active, setActive] = useState<TVState>(state.circuit.path.length > 1 ? "track" : "tower");
  const [rotating, setRotating] = useState(false);
  const [selectedStoryId, setSelectedStoryId] = useState<string | null>(null);
  const [toolbarVisible, setToolbarVisible] = useState(true);
  const [editingControl, setEditingControl] = useState(false);
  const [panel, setPanel] = useState<"sync" | "settings" | "follow" | "features" | "activity" | null>(null);
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const selectedDriver = preferences.selectedDriverNumber ? drivers.find((driver) => driver.number === preferences.selectedDriverNumber) ?? null : drivers[0] ?? null;
  const battleDrivers = useMemo(() => drivers.filter((driver) => driverLifecycle(driver).battleEligible), [drivers]);
  const leaderPair = battleDrivers.length >= 2 ? [battleDrivers[0].number, battleDrivers[1].number] as [string, string] : null;
  const selectedPair = preferences.battleMode === "leader" ? leaderPair : preferences.battleMode === "pinned" ? preferences.pinnedBattle : recommendedBattle;
  const battle = selectedPair ? [battleDrivers.find((driver) => driver.number === selectedPair[0]), battleDrivers.find((driver) => driver.number === selectedPair[1])] as const : null;
  const hasTrack = state.circuit.path.length > 1;
  const qualifyingStates = useMemo<TVState[]>(() => hasTrack && hasRenderableCarPositions(drivers, positionMode) ? ["track", ...stateSets.qualifying] : stateSets.qualifying, [drivers, hasTrack, positionMode]);
  const featureStates = layout === "race" ? stateSets.race : layout === "qualifying" ? qualifyingStates : stateSets.practice;
  const resultState = analytics?.story?.result.state ?? "none";
  const selectedStory = analytics?.story?.events.find((event) => event.id === selectedStoryId);
  const available = (item: TVState) => item === "track" ? hasTrack : item === "battle" ? Boolean(battle?.[0] && battle?.[1]) : item === "driver" ? Boolean(selectedDriver) : item === "result" ? resultState !== "none" : true;
  const reason = (item: TVState) => item === "track" ? "Circuit shape is not available" : item === "battle" ? "No comparable driver pair at this moment" : item === "driver" ? "No classified driver at this moment" : item === "result" ? "The result is available after the flag" : "";
  const authoredStates = featureStates.filter((item) => item !== "tower" && available(item) && (layout !== "race" || preferences.includedRaceStates.includes(item)));
  const visibleState = featureStates.includes(active) ? active : "tower";
  const effectiveStatus = state.session.display_status ?? state.session.track_status;
  const qualifyingSettlement = layout === "qualifying" ? analytics?.qualifying.settlement : null;
  const governingStatus = effectiveStatus && effectiveStatus !== "UNKNOWN" ? effectiveStatus.replaceAll("_", " ") : null;
  const tone = statusTone(governingStatus);
  const k = Math.max(.5, Math.min(viewport.width / 1920, viewport.height / 1080)) * (preferences.textSize ?? 1);
  const tvStyle = { "--tv-scale": k, "--safe-x": `${preferences.safeArea ?? 0}vw`, "--safe-y": `${preferences.safeArea ?? 0}vh` } as React.CSSProperties;
  const labels: Record<TVState, string> = { track: "TRACK", battle: "BATTLE", strategy: "STRATEGY", driver: "FOLLOWING", result: "RESULT", tower: "TIMING" };
  const send = (command: ReplayCommand) => { if (!canCommand || canCommand(command)) onCommand?.(command); };
  const reveal = () => {
    setToolbarVisible(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => { if (!root.current?.querySelector(".tv-overlay") && !root.current?.querySelector(".tv-toolbar")?.contains(document.activeElement)) setToolbarVisible(false); }, 6000);
  };
  const openPanel = (next: typeof panel) => { returnFocus.current = document.activeElement as HTMLElement; setEditingControl(false); setPanel(next); setToolbarVisible(true); };
  const closePanel = () => { setEditingControl(false); setPanel(null); returnFocus.current?.focus(); };
  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", resize);
    hideTimer.current = setTimeout(() => { if (!root.current?.querySelector(".tv-overlay") && !root.current?.querySelector(".tv-toolbar")?.contains(document.activeElement)) setToolbarVisible(false); }, 6000);
    return () => { window.removeEventListener("resize", resize); if (hideTimer.current) clearTimeout(hideTimer.current); };
  }, []);
  useEffect(() => {
    if (!panel) return;
    root.current?.querySelector<HTMLElement>(".tv-overlay button, .tv-overlay input, .tv-overlay select")?.focus();
  }, [panel]);
  const rotationKey = authoredStates.join(",");
  useEffect(() => {
    if (!rotating || speed >= 20 || !rotationKey) return;
    const states = rotationKey.split(",") as TVState[];
    const timer = setInterval(() => setActive((current) => nextAuthoredState(states, current) ?? states[0]), Math.max(5, preferences.rotationIntervalSeconds) * 1000);
    return () => clearInterval(timer);
  }, [rotationKey, preferences.rotationIntervalSeconds, rotating, speed]);
  // Facts render directly from the current snapshot; a jump never replays an old alert.
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const editable = event.target instanceof HTMLElement && Boolean(event.target.closest("input, select, textarea, [contenteditable=true]"));
      if (event.key === "Escape" || event.key === "BrowserBack") { event.preventDefault(); event.stopPropagation(); if (editingControl) setEditingControl(false); else if (panel) closePanel(); else if (toolbarVisible) { setToolbarVisible(false); (document.activeElement as HTMLElement)?.blur(); } else onExit(); return; }
      if (editable && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); event.stopPropagation(); setEditingControl((value) => !value); return; }
      if (editable && editingControl && event.key !== "Tab") return;
      if (event.key === "Tab") setEditingControl(false);
      if (event.key === " " && event.target instanceof HTMLElement && event.target.closest("button, summary")) return;
      if (event.key === " " || event.key === "MediaPlayPause") { event.preventDefault(); send(isPlaying ? { type: "pause" } : viewingMode === "live" ? { type: "play", speed: 1 } : { type: "play", speed }); reveal(); return; }
      const direction = event.key === "ArrowLeft" || event.key === "MediaRewind" ? -1 : event.key === "ArrowRight" || event.key === "MediaFastForward" ? 1 : 0;
      if (direction && (!toolbarVisible || event.key.startsWith("Media"))) { event.preventDefault(); send(viewingMode === "live" ? { type: "delay", seconds: Math.max(0, Math.min(300, delaySeconds - direction * 5)) } : { type: "seek_relative", seconds: direction * 30 }); reveal(); return; }
      if (event.key.startsWith("Arrow")) {
        event.preventDefault(); event.stopPropagation(); reveal();
        const scope = root.current?.querySelector<HTMLElement>(panel ? ".tv-overlay" : ".tv-toolbar");
        const targets = [...(scope?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled)") ?? [])].filter((element) => element.getBoundingClientRect().width > 0);
        const current = document.activeElement as HTMLElement;
        if (!targets.includes(current)) { targets[0]?.focus(); return; }
        const from = current.getBoundingClientRect(); const x = from.left + from.width / 2; const y = from.top + from.height / 2;
        const horizontal = event.key === "ArrowLeft" || event.key === "ArrowRight";
        const sign = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
        const nearest = targets.filter((element) => element !== current).map((element) => { const box = element.getBoundingClientRect(); const dx = box.left + box.width / 2 - x; const dy = box.top + box.height / 2 - y; return { element, forward: (horizontal ? dx : dy) * sign, distance: Math.abs(horizontal ? dx : dy) + Math.abs(horizontal ? dy : dx) * 3 }; }).filter((item) => item.forward > 1).sort((a, b) => a.distance - b.distance)[0];
        nearest?.element.focus(); return;
      }
      if (event.key === "Tab" && panel) { const targets = [...(root.current?.querySelectorAll<HTMLElement>(".tv-overlay button:not(:disabled), .tv-overlay input:not(:disabled), .tv-overlay select:not(:disabled)") ?? [])]; const first = targets[0]; const last = targets.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } }
      reveal();
    };
    window.addEventListener("keydown", keydown, true);
    return () => window.removeEventListener("keydown", keydown, true);
  });
  const variant = layout === "qualifying" ? "qualifying" : layout === "practice" ? "practice" : "race";
  const tower = (compact = false) => <TimingTower tvScale={k} compact={compact} drivers={drivers} variant={variant} replayAvailable={replayAvailable} analytics={analytics} intervalsAvailable={intervalsAvailable} desktopRaceColumns sectorTimingAvailable={sectorTimingAvailable} />;
  return <div ref={root} style={tvStyle} className={`tv-mode-view tv-redesign${visibleState === "tower" ? " tv-timing-expanded" : ""}`} data-track-tone={tone} data-generation={navigationGeneration} data-editing-control={editingControl} onPointerMove={reveal} onPointerDownCapture={(event) => setEditingControl(event.target instanceof HTMLElement && Boolean(event.target.closest("input,select,textarea")))} onFocusCapture={(event) => { if (!(event.target instanceof HTMLElement) || !event.target.closest("input,select,textarea")) setEditingControl(false); }}>
    <header className="tv-session-rail"><RailTransition status={effectiveStatus} generation={navigationGeneration} /><div className={`tv-flag flag-${tone}`}>{governingStatus ?? "STATUS —"}</div><div className="tv-session-identity"><strong>{state.session.meeting_name ?? "Session unavailable"}</strong><small>{qualifyingSettlement === "SETTLING" ? `${analytics?.qualifying.phase} FLAG · LAPS FINISHING` : qualifyingSettlement === "SOURCE_COMPLETE" ? "QUALIFYING · PROVISIONAL" : state.session.name ?? sessionKind.replaceAll("_", " ")}</small></div><SessionProgress session={state.session} /><span className="tv-viewer-mode">{viewingMode === "live" ? delaySeconds ? `LIVE −${Math.floor(delaySeconds / 60)}:${String(Math.floor(delaySeconds % 60)).padStart(2, "0")}` : "LIVE" : `REPLAY ${speed}×`} · {isPlaying ? "PLAYING" : "PAUSED"}</span></header>
    {(notice || (viewingMode === "live" && ["STALE", "RECONNECTING"].includes(livePhase ?? ""))) && <div className="tv-live-notice" role="status">{notice ?? `${livePhase} · waiting for the timing feed`}</div>}
    {viewport.width < 900 && <div className="tv-small-window"><span>TV mode works best in a wider window.</span><button onClick={onExit}>OPEN STANDARD VIEW</button></div>}
    <div className="tv-composition">{visibleState !== "tower" && <aside className="tv-side-tower">{tower(true)}</aside>}<main className={`tv-stage tv-stage-${visibleState}`}>
      <header className="tv-feature-heading"><h1>{labels[visibleState]}</h1><div>{featureStates.map((item) => <button key={item} className={visibleState === item ? "active" : ""} disabled={!available(item)} title={available(item) ? labels[item] : reason(item)} onClick={() => { setActive(item); setRotating(false); }}>{labels[item]}</button>)}</div></header>
      <div className="tv-feature-content">{layout === "unsupported" ? <div className="unknown-block"><strong>Session layout unavailable</strong></div> : <>
      {visibleState === "tower" && <div className="tv-tower">{tower()}</div>}
      {visibleState === "track" && <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} focusedDriverNumbers={preferences.selectedDriverNumber ? [preferences.selectedDriverNumber] : []} />}
      {visibleState === "strategy" && layout === "race" && <div className="tv-strategy pirelli-tv-strategy"><PirelliBaseline baseline={analytics?.publishedStrategy?.baseline} fieldFacts={analytics?.publishedStrategy?.fieldFacts} /><RaceNow analytics={analytics} /></div>}
      {visibleState === "battle" && layout === "race" && <TVBattle drivers={battle} analytics={analytics} mode={preferences.battleMode} state={state} positionMode={positionMode} viewingMode={viewingMode} />}
      {visibleState === "result" && layout === "race" && <section className="tv-result">{resultState === "none" ? <div className="unknown-block"><strong>No result yet</strong><p>The result becomes available after the flag.</p></div> : <><header><span>{resultState === "final" ? "FINAL CLASSIFICATION" : "PROVISIONAL · ON THE ROAD"}</span><h2>{state.session.meeting_name ?? "Session result"}</h2></header><ol>{drivers.map((driver) => <li key={driver.number}><b>{driver.position ?? "—"}</b><span><strong>{driver.name ?? driver.code ?? driver.number}</strong><small>{driver.team ?? "—"}</small></span><em>{driverLifecycle(driver).label ?? "CLASSIFICATION PENDING"}</em></li>)}</ol></>}</section>}
      {visibleState === "driver" && layout === "race" && <DriverTV driver={selectedDriver} analytics={analytics} state={state} positionMode={positionMode} viewingMode={viewingMode} />}
      </>}</div>
    </main></div>
    {visibleState !== "tower" && <div className="tv-moments">{moments}</div>}
    <footer className="tv-ticker"><BrandMark /><span className="tv-ticker-label">AT THIS MOMENT</span><div className="tv-ticker-items">{analytics?.story?.events.length ? analytics.story.events.slice(-3).map((event) => <button key={event.id} onClick={() => { setSelectedStoryId(event.id); openPanel("activity"); }}><small>{event.lap == null ? event.kind.replaceAll("_", " ") : `L${event.lap} · ${event.kind.replaceAll("_", " ")}`}</small><strong>{event.title}</strong></button>) : <span>{state.race_control.at(-1)?.message ?? "Waiting for session activity."}</span>}</div><button onClick={reveal}>CONTROLS ↑</button></footer>
    {toolbarVisible && <div className="tv-toolbar" role="toolbar" aria-label="TV controls"><button onClick={onExit}>{exitLabel}</button><button aria-pressed={rotating} onClick={() => setRotating((value) => !value)}>AUTO {rotating ? "ON" : "OFF"}</button><button onClick={() => openPanel("features")}>FEATURES</button><button onClick={() => { setSelectedStoryId(null); openPanel("activity"); }}>ACTIVITY</button><button onClick={() => openPanel("follow")}>FOLLOW</button><button onClick={() => openPanel("sync")}>{viewingMode === "live" ? "LIVE DELAY" : "PLAYBACK / SYNC"}</button><button disabled={canCommand ? !canCommand(isPlaying ? { type: "pause" } : { type: "play", speed: 1 }) : !onCommand} onClick={() => send(isPlaying ? { type: "pause" } : viewingMode === "live" ? { type: "play", speed: 1 } : { type: "play", speed })}>{isPlaying ? "PAUSE" : "PLAY"}</button><button onClick={() => openPanel("settings")}>SETTINGS</button><button onClick={() => setToolbarVisible(false)} aria-label="Hide TV controls">×</button></div>}
    {panel && <div className="tv-overlay-backdrop"><section className="tv-overlay" role="dialog" aria-modal="true" aria-label={panel === "sync" ? "Playback and sync" : panel === "follow" ? "Follow a driver" : panel === "features" ? "TV features" : panel === "activity" ? "Session activity" : "TV settings"}><header><h2>{panel === "sync" ? "PLAYBACK / SYNC" : panel === "follow" ? "FOLLOW A DRIVER" : panel === "features" ? "FEATURES" : panel === "activity" ? "ACTIVITY" : "TV SETTINGS"}</h2><button onClick={closePanel} aria-label="Close TV panel">×</button></header>{editingControl && <p className="tv-control-edit-hint" role="status">EDITING · Arrows change the value. OK or Back finishes.</p>}{panel === "sync" ? controls : panel === "activity" ? <div className="tv-activity-panel">{selectedStory && <article className="tv-story-detail"><h3>{selectedStory.title}</h3><p>{selectedStory.detail}</p><dl><div><dt>HAPPENED</dt><dd>{selectedStory.occurredAt.slice(11, 19)} UTC</dd></div><div><dt>KNOWN</dt><dd>{selectedStory.availableAt.slice(11, 19)} UTC</dd></div><div><dt>STATE</dt><dd>{selectedStory.state.toUpperCase()}</dd></div></dl>{viewingMode === "replay" && onReplayMoment && <button onClick={() => { onReplayMoment(selectedStory); closePanel(); }}>REPLAY THIS MOMENT</button>}</article>}{ticker}</div> : panel === "features" ? <div className="tv-follow-list">{featureStates.map((item) => <button key={item} aria-pressed={visibleState === item} disabled={!available(item)} title={available(item) ? labels[item] : reason(item)} onClick={() => { setActive(item); setRotating(false); closePanel(); }}>{labels[item]}{available(item) ? "" : ` · ${reason(item)}`}</button>)}</div> : panel === "follow" ? <div className="tv-follow-list"><button onClick={() => onPreferencesChange({ ...preferences, selectedDriverNumber: null })}>AUTOMATIC · LEADER</button>{drivers.map((driver) => <button key={driver.number} aria-pressed={preferences.selectedDriverNumber === driver.number} onClick={() => onPreferencesChange({ ...preferences, selectedDriverNumber: driver.number })}>P{driver.position ?? "—"} · {driver.code ?? driver.number} · {driver.team ?? "—"}</button>)}</div> : <div className="tv-settings-fields"><label>TEXT SIZE<select value={preferences.textSize ?? 1} onChange={(event) => onPreferencesChange({ ...preferences, textSize: Number(event.target.value) })}><option value={.85}>85%</option><option value={1}>100%</option><option value={1.15}>115%</option><option value={1.3}>130%</option></select></label><label>SAFE AREA<select value={preferences.safeArea ?? 0} onChange={(event) => onPreferencesChange({ ...preferences, safeArea: Number(event.target.value) })}><option value={0}>OFF</option><option value={2.5}>2.5%</option><option value={5}>5%</option></select></label>{layout === "race" && <><label>BATTLE PAIR<select value={preferences.battleMode} onChange={(event) => onPreferencesChange({ ...preferences, battleMode: event.target.value as TVPreferences["battleMode"] })}><option value="recommended">RECOMMENDED</option><option value="leader">LEADER</option><option value="pinned">PINNED</option></select></label>{preferences.battleMode === "pinned" && <>{([0, 1] as const).map((index) => <label key={index}>DRIVER {index === 0 ? "A" : "B"}<select value={preferences.pinnedBattle[index]} onChange={(event) => onPreferencesChange({ ...preferences, pinnedBattle: index === 0 ? [event.target.value, preferences.pinnedBattle[1]] : [preferences.pinnedBattle[0], event.target.value] })}><option value="">SELECT DRIVER</option>{drivers.map((driver) => <option key={driver.number} value={driver.number}>{driver.code ?? driver.number} · {driver.team ?? "—"}</option>)}</select></label>)}</>}</>}<label>ROTATION SECONDS<input type="number" min="5" max="60" value={preferences.rotationIntervalSeconds} onChange={(event) => onPreferencesChange({ ...preferences, rotationIntervalSeconds: Math.max(5, Math.min(60, Number(event.target.value) || 12)) })} /></label></div>}</section></div>}
  </div>;
}
