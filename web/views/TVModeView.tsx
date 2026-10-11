import { useEffect, useMemo, useRef, useState } from "react";
import type React from "react";

import { TVResult } from "../components/analysis/TVResult";
import { RaceOrderRibbon } from "../components/analysis/RaceOrderRibbon";
import { TVFollowing } from "../components/analysis/TVFollowing";
import { NonRaceTVFeature } from "../components/analysis/NonRaceTVFeature";
import { TVStrategy } from "../components/analysis/TVStrategy";
import { BattleComposition } from "../components/battle/BattleComposition";
import { TrackMap } from "../components/analysis/TrackMap";
import { RailTransition } from "../components/shared/RailTransition";
import { StoryTicker } from "../components/story/StoryTicker";
import { BrandMark } from "../components/shared/Brand";
import { TVPlaybackPanel } from "../components/shell/TVPlaybackPanel";
import { formatLiveDelay } from "../domain/liveDelay.mjs";
import { utcOffsetLabel } from "../domain/format";
import { sessionStatusLabel } from "../domain/sessionStatus";
import { SessionProgress } from "../components/shared/SessionProgress";
import { TimingTower } from "../components/timing/TimingTower";
import { driverLifecycle } from "../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, PositionMode, ViewingMode, RaceState, SessionKind, ReplayCommand, StoryEvent } from "../domain/protocol";
import type { SessionLayout } from "../domain/sessionLayout";
import { nextAuthoredState } from "../domain/tvMode.mjs";
import type { TVPreferences, TVStatePreference } from "../hooks/useProductPreferences";

type TVState = TVStatePreference;
const stateSets: Record<Exclude<SessionLayout, "unsupported">, TVState[]> = {
  race: ["track", "battle", "strategy", "result", "driver", "tower"],
  qualifying: ["spread", "tower"],
  practice: ["spread", "tower"],
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

export function TVModeView({ state, analytics, recommendedBattle, sessionLayout, sessionKind, replayAvailable, positionMode, viewingMode, sectorTimingAvailable, preferences, onPreferencesChange, onExit, exitLabel = "EXIT TV", onCommand, canCommand, isPlaying = false, speed = 10, delaySeconds = 0, requestedDelaySeconds = delaySeconds, syncOffsetSeconds = 0, onSpeedChange, onSyncOffsetChange, hasReturnPoint, onReturn, navigationGeneration = 0, ticker, moments, onReplayMoment, notice, livePhase, intervalsAvailable = false }: {
  state: RaceState; analytics: AnalyticsSnapshot | null; recommendedBattle: [string, string] | null;
  sessionLayout: SessionLayout; sessionKind: SessionKind; replayAvailable: boolean;
  positionMode: PositionMode; viewingMode: ViewingMode; sectorTimingAvailable: boolean; intervalsAvailable?: boolean;
  preferences: TVPreferences; onPreferencesChange: (value: TVPreferences) => void; onExit: () => void; exitLabel?: string;
  controls?: React.ReactNode; onCommand?: (command: ReplayCommand) => boolean; canCommand?: (command: ReplayCommand) => boolean;
  requestedDelaySeconds?: number; syncOffsetSeconds?: number; onSpeedChange?: (speed: number) => boolean | void; onSyncOffsetChange?: (seconds: number) => boolean | void; hasReturnPoint?: boolean; onReturn?: () => boolean | void;
  isPlaying?: boolean; speed?: number; delaySeconds?: number; navigationGeneration?: number; ticker?: React.ReactNode; moments?: React.ReactNode; onReplayMoment?: (event: StoryEvent) => void; notice?: string | null; livePhase?: string;
}) {
  const layout = sessionLayout;
  const root = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [viewport, setViewport] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));
  const [active, setActive] = useState<TVState>(sessionLayout === "race" ? state.circuit.path.length > 1 ? "track" : "tower" : "spread");
  const [rotating, setRotating] = useState(true);
  const [selectedStoryId, setSelectedStoryId] = useState<string | null>(null);
  const [toolbarVisible, setToolbarVisible] = useState(false);
  const [editingControl, setEditingControl] = useState(false);
  const [panel, setPanel] = useState<"sync" | "settings" | "follow" | "features" | "activity" | null>(null);
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const selectedDriver = preferences.selectedDriverNumber ? drivers.find((driver) => driver.number === preferences.selectedDriverNumber) ?? null : null;
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
  const autoStatus = state.session.display_status ?? state.session.track_status;
  const visibleState = rotating && resultState !== "none" && authoredStates.includes("result") ? "result" : rotating && ["VSC", "VSC_ENDING", "SAFETY_CAR", "RED", "RED_FLAG"].includes(autoStatus ?? "") && authoredStates.includes("track") ? "track" : featureStates.includes(active) ? active : "tower";
  const effectiveStatus = state.session.display_status ?? state.session.track_status;
  const qualifyingSettlement = layout === "qualifying" ? analytics?.qualifying.settlement : null;
  const governingStatus = sessionStatusLabel(state.session, analytics?.qualifying.phase);
  const tone = statusTone(effectiveStatus?.replaceAll("_", " "));
  const k = Math.max(.5, Math.min(viewport.width / 1920, viewport.height / 1080)) * (preferences.textSize ?? 1);
  const tvStyle = { "--tv-scale": k, "--safe-x": `${preferences.safeArea ?? 0}vw`, "--safe-y": `${preferences.safeArea ?? 0}vh` } as React.CSSProperties;
  const labels: Record<TVState, string> = { spread: layout === "qualifying" ? "CUT LINE" : "SPREAD", track: "TRACK", battle: "BATTLE", strategy: "STRATEGY", driver: "FOLLOWING", result: "RESULT", tower: "TIMING" };
  const send = (command: ReplayCommand) => { if (!canCommand || canCommand(command)) onCommand?.(command); };
  const hideControls = () => {
    if (root.current?.querySelector(".tv-overlay")) return;
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && root.current?.querySelector(".tv-toolbar")?.contains(focused)) focused.blur();
    setToolbarVisible(false);
  };
  const reveal = () => {
    setToolbarVisible(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(hideControls, 6000);
  };
  const openPanel = (next: typeof panel) => { returnFocus.current = document.activeElement as HTMLElement; setEditingControl(false); setPanel(next); setToolbarVisible(true); };
  const closePanel = () => { setEditingControl(false); setPanel(null); returnFocus.current?.focus(); reveal(); };
  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); if (hideTimer.current) clearTimeout(hideTimer.current); };
  }, []);
  useEffect(() => {
    if (!panel) return;
    [...(root.current?.querySelectorAll<HTMLElement>(".tv-overlay button:not(:disabled), .tv-overlay input:not(:disabled), .tv-overlay select:not(:disabled)") ?? [])].find(element => !element.closest(".tv-overlay-sync > .tv-overlay > header") && !element.hidden)?.focus();
  }, [panel]);
  const rotationKey = authoredStates.join(",");
  useEffect(() => {
    if (!rotating || !rotationKey) return;
    const states = rotationKey.split(",") as TVState[];
    const timer = setInterval(() => setActive((current) => nextAuthoredState(states, current) ?? states[0]), Math.max(5, preferences.rotationIntervalSeconds) * 1000);
    return () => clearInterval(timer);
  }, [rotationKey, preferences.rotationIntervalSeconds, rotating]);
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
      if (event.key === "Tab" && panel) { const targets = [...(root.current?.querySelectorAll<HTMLElement>(".tv-overlay button:not(:disabled), .tv-overlay input:not(:disabled), .tv-overlay select:not(:disabled)") ?? [])].filter(element => !element.closest(".tv-overlay-sync > .tv-overlay > header") && !element.hidden); const first = targets[0]; const last = targets.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } }
      reveal();
    };
    window.addEventListener("keydown", keydown, true);
    return () => window.removeEventListener("keydown", keydown, true);
  });
  const variant = layout === "qualifying" ? "qualifying" : layout === "practice" ? "practice" : "race";
  const tower = (compact = false) => <TimingTower tvScale={k} compact={compact} drivers={drivers} variant={variant} replayAvailable={replayAvailable} analytics={analytics} intervalsAvailable={intervalsAvailable} desktopRaceColumns sectorTimingAvailable={sectorTimingAvailable} />;
  return <div ref={root} tabIndex={-1} style={tvStyle} className={`tv-mode-view tv-redesign${visibleState === "tower" ? " tv-timing-expanded" : ""}`} data-track-tone={tone} data-generation={navigationGeneration} data-editing-control={editingControl} data-controls-visible={toolbarVisible} onPointerMove={reveal} onPointerDownCapture={(event) => setEditingControl(event.target instanceof HTMLElement && Boolean(event.target.closest("input,select,textarea")))} onFocusCapture={(event) => { if (!(event.target instanceof HTMLElement) || !event.target.closest("input,select,textarea")) setEditingControl(false); }}>
    <header className="tv-session-rail"><RailTransition status={effectiveStatus} generation={navigationGeneration} /><div className={`tv-flag flag-${tone}`}>{governingStatus ?? "STATUS —"}</div><div className="tv-rail-middle"><div className="tv-session-identity"><strong>{state.session.meeting_name ?? "Session unavailable"}</strong><small>{qualifyingSettlement === "SETTLING" ? `${analytics?.qualifying.phase} FLAG · LAPS FINISHING` : qualifyingSettlement === "SOURCE_COMPLETE" ? "QUALIFYING · PROVISIONAL" : `${state.session.name ?? sessionKind.replaceAll("_", " ")} · ${state.session.circuit ?? state.circuit.name ?? ""}`}</small></div><div className="tv-progress">{layout === "race" ? <><strong>LAP {state.session.lap ?? "—"}<small>/{state.session.total_laps ?? "—"}</small></strong>{state.session.total_laps != null && state.session.lap != null && <span>{state.session.lap >= state.session.total_laps ? "FINAL LAP" : `${state.session.total_laps - state.session.lap} TO GO`}</span>}</> : <SessionProgress session={state.session} />}</div><div className="tv-rail-clock"><b>{state.session.local_time?.slice(11, 19) ?? "—"}</b><span>LOCAL · {utcOffsetLabel(state.session.gmt_offset)}</span></div></div><span className="tv-viewer-mode">{isPlaying ? "▶" : "▸"} {viewingMode === "live" ? delaySeconds ? `LIVE −${formatLiveDelay(delaySeconds)}` : "LIVE" : `REPLAY ${speed}×`} {isPlaying ? "" : " PAUSED"}</span></header>
    {(notice || (viewingMode === "live" && ["STALE", "RECONNECTING"].includes(livePhase ?? ""))) && <div className="tv-live-notice" role="status">{notice ?? `${livePhase} · waiting for the timing feed`}</div>}
    {viewport.width < 900 && <div className="tv-small-window"><span>TV mode works best in a wider window.</span><button onClick={onExit}>OPEN STANDARD VIEW</button></div>}
    <div className="tv-composition">{visibleState !== "tower" && <aside className="tv-side-tower">{tower(true)}</aside>}<main className={`tv-stage tv-stage-${visibleState}`}>
      <header className="tv-feature-heading"><h1>{labels[visibleState]}</h1><div>{featureStates.map((item, index) => <button key={item} className={visibleState === item ? "active" : ""} disabled={!available(item)} title={available(item) ? labels[item] : reason(item)} onClick={() => { setActive(item); setRotating(false); }}><em>{item === "tower" ? "T" : index + 1}</em>{labels[item]}</button>)}<button className={rotating ? "active" : ""} aria-pressed={rotating} onClick={() => setRotating(value => !value)}><em>A</em>AUTO</button></div></header>
      <div className="tv-feature-content">{layout === "unsupported" ? <div className="unknown-block"><strong>Session layout unavailable</strong></div> : <>
      {visibleState === "spread" && <NonRaceTVFeature state={state} analytics={analytics} followedDriverNumber={preferences.selectedDriverNumber} />}
      {visibleState === "tower" && <div className="tv-tower">{tower()}</div>}
      {visibleState === "track" && <div className="ref-tv-track"><TrackMap posture="tv" showRibbon={false} circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} viewingMode={viewingMode} focusedDriverNumbers={preferences.selectedDriverNumber ? [preferences.selectedDriverNumber] : []} navigationGeneration={navigationGeneration} playing={isPlaying} speed={speed} asOf={state.updated_at} />{layout === "race" && <RaceOrderRibbon posture="tv" drivers={drivers} focusedDriverNumbers={preferences.selectedDriverNumber ? [preferences.selectedDriverNumber] : []} battlePairs={analytics?.battle.candidates} />}</div>}
      {visibleState === "strategy" && layout === "race" && <TVStrategy state={state} analytics={analytics} />}
      {visibleState === "battle" && layout === "race" && <BattleComposition posture="tv" state={state} analytics={analytics} pair={battle?.[0] && battle[1] ? [battle[0], battle[1]] : null} />}
      {visibleState === "result" && layout === "race" && <TVResult state={state} analytics={analytics} />}
      {visibleState === "driver" && layout === "race" && <TVFollowing driver={selectedDriver} analytics={analytics} state={state} positionMode={positionMode} viewingMode={viewingMode} />}
      </>}</div>
      {visibleState !== "tower" && <div className="tv-moments">{moments}</div>}
    </main></div>
    <footer className="tv-ticker"><StoryTicker story={analytics?.story} drivers={state.drivers} session={state.session} sessionKey={state.session.key} generation={navigationGeneration} mode={viewingMode} posture="tv" visible={!toolbarVisible} brand={<BrandMark />} onInspect={event => { setSelectedStoryId(event.id); openPanel("activity"); }} /><button onClick={reveal}>CONTROLS ↑</button></footer>
    {toolbarVisible && <div className="tv-toolbar" role="toolbar" aria-label="TV controls"><button onClick={onExit}>‹ {exitLabel}</button><div className="tv-toolbar-features" role="group" aria-label="Feature">{featureStates.map(item => <button key={item} aria-pressed={!rotating && visibleState === item} disabled={!available(item)} title={available(item) ? labels[item] : reason(item)} onClick={() => { setActive(item); setRotating(false); }}>{labels[item]}</button>)}<button aria-pressed={rotating} onClick={() => { setRotating(value => !value); if (visibleState === "tower") setActive(authoredStates[0] ?? "track"); }}>AUTO</button></div><label className="tv-toolbar-follow"><span>FOLLOW</span><select aria-label="Follow a driver" value={preferences.selectedDriverNumber ?? ""} onChange={event => onPreferencesChange({ ...preferences, selectedDriverNumber: event.target.value || null })}><option value="">— nobody —</option>{drivers.map(driver => <option key={driver.number} value={driver.number}>{driver.code ?? driver.number} · {driver.team ?? "—"}</option>)}</select></label><button className="tv-toolbar-sync" onClick={() => openPanel("sync")}>◴ {viewingMode === "live" ? "DELAY" : "SYNC"}<em>{viewingMode === "live" ? formatLiveDelay(delaySeconds) : `${speed}× · ${formatLiveDelay(syncOffsetSeconds)}`}</em></button><button className="tv-toolbar-play" disabled={canCommand ? !canCommand(isPlaying ? { type: "pause" } : { type: "play", speed: 1 }) : !onCommand} onClick={() => send(isPlaying ? { type: "pause" } : viewingMode === "live" ? { type: "play", speed: 1 } : { type: "play", speed })}>{isPlaying ? "❚❚ PAUSE" : "▶ PLAY"}</button><button onClick={() => openPanel("settings")}>SETTINGS</button><span className="tv-toolbar-keys">D-PAD · OK · BACK</span></div>}
    {panel && <div className={`tv-overlay-backdrop tv-overlay-${panel}`}><section className="tv-overlay" role="dialog" aria-modal="false" aria-label={panel === "sync" ? "Playback and sync" : panel === "follow" ? "Follow a driver" : panel === "features" ? "TV features" : panel === "activity" ? "Session activity" : "TV settings"}><header><h2>{panel === "sync" ? "PLAYBACK / SYNC" : panel === "follow" ? "FOLLOW A DRIVER" : panel === "features" ? "FEATURES" : panel === "activity" ? "ACTIVITY" : "TV SETTINGS"}</h2><button onClick={closePanel} aria-label="Close TV panel">×</button></header>{editingControl && <p className="tv-control-edit-hint" role="status">EDITING · Arrows change the value. OK or Back finishes.</p>}{panel === "sync" ? <TVPlaybackPanel session={state.session} mode={viewingMode} speed={speed} playing={isPlaying} delay={delaySeconds} requestedDelay={requestedDelaySeconds} syncOffset={syncOffsetSeconds} canCommand={command => canCommand?.(command) ?? Boolean(onCommand)} onCommand={command => onCommand?.(command) ?? false} onSpeedChange={onSpeedChange} onSyncOffsetChange={onSyncOffsetChange} onClose={closePanel} hasReturnPoint={hasReturnPoint} onReturn={onReturn} /> : panel === "activity" ? <div className="tv-activity-panel">{selectedStory && <article className="tv-story-detail"><h3>{selectedStory.title}</h3><p>{selectedStory.detail}</p><dl><div><dt>HAPPENED</dt><dd>{selectedStory.occurredAt.slice(11, 19)} UTC</dd></div><div><dt>KNOWN</dt><dd>{selectedStory.availableAt.slice(11, 19)} UTC</dd></div><div><dt>STATE</dt><dd>{selectedStory.state.toUpperCase()}</dd></div></dl>{viewingMode === "replay" && onReplayMoment && <button onClick={() => { onReplayMoment(selectedStory); closePanel(); }}>REPLAY THIS MOMENT</button>}</article>}{ticker}</div> : panel === "features" ? <div className="tv-follow-list">{featureStates.map((item) => <button key={item} aria-pressed={visibleState === item} disabled={!available(item)} title={available(item) ? labels[item] : reason(item)} onClick={() => { setActive(item); setRotating(false); closePanel(); }}>{labels[item]}{available(item) ? "" : ` · ${reason(item)}`}</button>)}</div> : panel === "follow" ? <div className="tv-follow-list"><button onClick={() => onPreferencesChange({ ...preferences, selectedDriverNumber: null })}>AUTOMATIC · LEADER</button>{drivers.map((driver) => <button key={driver.number} aria-pressed={preferences.selectedDriverNumber === driver.number} onClick={() => onPreferencesChange({ ...preferences, selectedDriverNumber: driver.number })}>P{driver.position ?? "—"} · {driver.code ?? driver.number} · {driver.team ?? "—"}</button>)}</div> : <div className="tv-settings-fields"><label>TEXT SIZE<select value={preferences.textSize ?? 1} onChange={(event) => onPreferencesChange({ ...preferences, textSize: Number(event.target.value) })}><option value={.85}>85%</option><option value={1}>100%</option><option value={1.15}>115%</option><option value={1.3}>130%</option></select></label><label>SAFE AREA<select value={preferences.safeArea ?? 0} onChange={(event) => onPreferencesChange({ ...preferences, safeArea: Number(event.target.value) })}><option value={0}>OFF</option><option value={2.5}>2.5%</option><option value={5}>5%</option></select></label>{layout === "race" && <><label>BATTLE PAIR<select value={preferences.battleMode} onChange={(event) => onPreferencesChange({ ...preferences, battleMode: event.target.value as TVPreferences["battleMode"] })}><option value="recommended">RECOMMENDED</option><option value="leader">LEADER</option><option value="pinned">PINNED</option></select></label>{preferences.battleMode === "pinned" && <>{([0, 1] as const).map((index) => <label key={index}>DRIVER {index === 0 ? "A" : "B"}<select value={preferences.pinnedBattle[index]} onChange={(event) => onPreferencesChange({ ...preferences, pinnedBattle: index === 0 ? [event.target.value, preferences.pinnedBattle[1]] : [preferences.pinnedBattle[0], event.target.value] })}><option value="">SELECT DRIVER</option>{drivers.map((driver) => <option key={driver.number} value={driver.number}>{driver.code ?? driver.number} · {driver.team ?? "—"}</option>)}</select></label>)}</>}</>}<label>ROTATION SECONDS<input type="number" min="5" max="60" value={preferences.rotationIntervalSeconds} onChange={(event) => onPreferencesChange({ ...preferences, rotationIntervalSeconds: Math.max(5, Math.min(60, Number(event.target.value) || 12)) })} /></label></div>}</section></div>}
  </div>;
}
