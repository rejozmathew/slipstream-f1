import { useEffect, useRef, useState, type CSSProperties } from "react";

import { classifySession } from "../../domain/sessionLayout";
import { useDriverHistory } from "../../hooks/useDriverHistory";
import { useBattleRecommendation } from "../../hooks/useBattleRecommendation";
import { useProductPreferences } from "../../hooks/useProductPreferences";
import { useSlipstreamSession } from "../../hooks/useSlipstreamSession";
import { BattleView } from "../../views/BattleView";
import { DriverFocusView } from "../../views/DriverFocusView";
import { DriverPickerView } from "../../views/DriverPickerView";
import { PracticeView } from "../../views/PracticeView";
import { QualifyingView } from "../../views/QualifyingView";
import { RaceView } from "../../views/RaceView";
import { SettingsView, type SettingsSection } from "../../views/SettingsView";
import { StrategyView } from "../../views/StrategyView";
import { TVModeView } from "../../views/TVModeView";
import { TVSessionPicker } from "../../views/TVSessionPicker";
import { StoryFeed } from "../story/StoryFeed";
import { StoryMoments } from "../story/StoryMoments";
import { BrandMark, BrandOpening, Kerb } from "../shared/Brand";
import { useReducedMotion } from "../../hooks/usePresentation";
import { Panel } from "../shared/Panel";
import { LiveControls } from "./LiveControls";
import { ReplayControls } from "./ReplayControls";
import { ReplayLibrary } from "./ReplayLibrary";
import { ReplayRecordingNotice } from "./ReplayRecordingNotice";
import { SessionStrip } from "./SessionStrip";

type ProductView = "session" | "battle" | "driver" | "strategy" | "tv" | "tv-sessions" | "settings";

export function AppShell({ standaloneTV = false }: { standaloneTV?: boolean }) {
  const session = useSlipstreamSession();
  const preferences = useProductPreferences();
  const reducedMotion = useReducedMotion(preferences.appearance.motion);
  const [hasOpened, setHasOpened] = useState(false);
  const previousView = useRef<ProductView>("session");
  useEffect(() => { if (session.state.updated_at || session.connectionError) { const id = window.setTimeout(() => setHasOpened(true), 0); return () => window.clearTimeout(id); } }, [session.state.updated_at, session.connectionError]);
  const [view, setView] = useState<ProductView>(standaloneTV ? "tv-sessions" : "session");
  const [focusedDriver, setFocusedDriver] = useState<string | null>(preferences.lastDriverNumber);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("appearance");
  const classification = classifySession(
    session.state.session.session_type ?? session.selectedCatalogSession?.sessionType,
    session.state.session.name ?? session.selectedCatalogSession?.sessionName,
    session.state.session.session_kind ?? session.selectedCatalogSession?.sessionKind,
    session.state.session.layout_family ?? session.selectedCatalogSession?.layoutFamily,
  );
  const layout = classification.layoutFamily;
  const replayAvailable = session.metadata?.replayAvailable ?? session.selectedCatalogSession?.available ?? false;
  const dataAvailable = session.viewingMode === "live"
    ? ["LIVE", "STALE", "RECONNECTING", "FINALIZING", "COMPLETE", "REPLAY_READY"].includes(session.livePhase)
    : replayAvailable;
  const positionMode = session.viewingMode === "live" ? session.livePositionMode : session.capabilities?.positionMode ?? session.metadata?.positionMode ?? session.selectedCatalogSession?.positionMode ?? "unavailable";
  const sectorTimingAvailable = session.capabilities?.capabilities.sector_timing ?? false;
  const driverHistory = useDriverHistory(session.viewingMode === "replay" ? session.selectedSessionKey : null, focusedDriver);
  const recommendedBattle = useBattleRecommendation(session.analytics, session.state);
  const rootProps = {
    className: `app-shell view-${view} mode-${session.viewingMode}`,
    "data-session-layout": layout,
    "data-navigation-generation": session.navigationGeneration,
    "data-playback-speed": session.playbackSpeed,
    "data-viewer-playing": session.isPlaying,
    "data-session-key": session.selectedSessionKey,
    "data-recording-version": session.analytics?.recordingVersion ?? session.metadata?.recordingVersion,
    "data-track-status": session.state.session.display_status ?? session.state.session.track_status,
    "data-background": preferences.appearance.background,
    "data-accent": preferences.appearance.accent,
    "data-reduced-motion": reducedMotion,
    style: { "--ui-scale": (preferences.appearance.displaySize ?? 80) / 100 } as CSSProperties,
  };
  const liveNow = Boolean(session.catalog?.liveSessionKey);
  const connectionLabel = session.viewingMode === "live"
    ? session.livePhase.replaceAll("_", " ")
    : session.transport === "stream" ? "REPLAY CONNECTED" : session.transport.toUpperCase();
  const connectionClass = session.viewingMode === "live" ? `live-${session.livePhase.toLowerCase()}` : session.transport;

  const openDriver = (driverNumber: string) => {
    setFocusedDriver(driverNumber);
    preferences.setLastDriverNumber(driverNumber);
    setView("driver");
  };
  const openLayoutEditor = () => {
    setSettingsSection("layouts");
    setView("settings");
  };
  const workspaceRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (layout === "race" || (view !== "strategy" && view !== "battle")) return;
    const frame = window.requestAnimationFrame(() => setView("session"));
    return () => window.cancelAnimationFrame(frame);
  }, [layout, view]);
  useEffect(() => {
    window.requestAnimationFrame(() => {
      workspaceRef.current?.scrollTo({ top: 0, left: 0 });
      workspaceRef.current?.querySelectorAll<HTMLElement>(".timing-table, .analysis-stack").forEach((element) => element.scrollTo({ top: 0, left: 0 }));
    });
  }, [view, preferences.towerView]);
  const goLive = () => {
    session.goLive();
    setView("session");
  };

  const controls = session.viewingMode === "replay"
    ? <ReplayControls metadata={session.metadata} playhead={session.playhead} gmtOffset={session.state.session.gmt_offset} isPlaying={session.isPlaying} commandAvailable={session.commandAvailable} onCommand={session.sendReplayCommand} speed={session.playbackSpeed} onSpeedChange={session.setPlaybackSpeed} hasReturnPoint={session.hasReturnPoint} onReturn={session.returnFromMoment} />
    : <LiveControls phase={session.livePhase} delaySeconds={session.liveDelaySeconds} commandAvailable={session.commandAvailable} onCommand={session.sendReplayCommand} isPlaying={session.isPlaying} requestedDelaySeconds={session.requestedLiveDelaySeconds} notice={session.liveNotice} />;
  const storySessionKey = session.selectedSessionKey ?? session.state.session.key ?? session.analytics?.sessionKey;
  const story = <StoryFeed sessionKey={storySessionKey} driverNumber={preferences.tv.selectedDriverNumber} story={session.analytics?.story} recordingVersion={session.analytics?.recordingVersion ?? session.metadata?.recordingVersion} mode={session.viewingMode} generation={session.navigationGeneration} onReplay={(event) => session.replayMoment(event.occurredAt)} />;
  const enterTV = () => { previousView.current = view; setView("tv"); };
  const followedDriver = preferences.tv.selectedDriverNumber ? session.state.drivers[preferences.tv.selectedDriverNumber] : null;

  if (standaloneTV && view === "tv-sessions") return <div {...rootProps}><TVSessionPicker catalog={session.catalog} selectedKey={session.selectedSessionKey} viewingMode={session.viewingMode} preferences={preferences.tv} error={session.connectionError} downloadState={session.downloadState} downloadError={session.downloadError} onSelect={(key) => session.chooseSession(key, "replay")} onDownload={() => void session.downloadReplay()} onWatch={(key, mode) => {
    // Resuming the same viewer preserves its cursor, delay, play state and follow.
    if (key !== session.selectedSessionKey || mode !== session.viewingMode) session.chooseSession(key, mode);
    setView("tv");
  }} /></div>;

  if (view === "tv") return <div {...rootProps}><TVModeView state={session.state} analytics={session.analytics} recommendedBattle={recommendedBattle} sessionLayout={layout} sessionKind={classification.kind} replayAvailable={dataAvailable} positionMode={positionMode} viewingMode={session.viewingMode} sectorTimingAvailable={sectorTimingAvailable} preferences={preferences.tv} onPreferencesChange={preferences.setTV} exitLabel={standaloneTV ? "SESSIONS" : "EXIT TV"} onExit={() => setView(standaloneTV ? "tv-sessions" : previousView.current === "tv" ? "session" : previousView.current)} controls={controls} notice={session.connectionError ?? session.liveNotice} livePhase={session.livePhase} onCommand={session.sendReplayCommand} canCommand={session.canCommand} isPlaying={session.isPlaying} speed={session.playbackSpeed} delaySeconds={session.liveDelaySeconds} navigationGeneration={session.navigationGeneration} intervalsAvailable={session.capabilities?.capabilities.intervals ?? false} ticker={<StoryFeed sessionKey={storySessionKey} driverNumber={preferences.tv.selectedDriverNumber} story={session.analytics?.story} recordingVersion={session.analytics?.recordingVersion ?? session.metadata?.recordingVersion} mode={session.viewingMode} generation={session.navigationGeneration} compact onReplay={(event) => session.replayMoment(event.occurredAt)} />} onReplayMoment={(event) => session.replayMoment(event.occurredAt)} moments={<StoryMoments sessionKey={storySessionKey} story={session.analytics?.story} recordingVersion={session.analytics?.recordingVersion ?? session.metadata?.recordingVersion} mode={session.viewingMode} generation={session.navigationGeneration} playing={session.isPlaying} speed={session.playbackSpeed} reducedMotion={reducedMotion} />} /></div>;

  return <div {...rootProps}>
    <header className="app-header">
      <button className="brand" aria-label="Slipstream session" onClick={() => setView("session")}><BrandMark /><span><b>SLIPSTREAM</b><small>F1 TIMING</small></span></button>
      <nav className="desktop-product-nav" aria-label="Product navigation">
        <button className={view === "session" ? "active" : ""} onClick={() => setView("session")}>SESSION</button>
        <button className={view === "driver" ? "active" : ""} onClick={() => setView("driver")}>DRIVER</button>
        {layout === "race" && <button className={view === "battle" ? "active" : ""} onClick={() => setView("battle")}>BATTLE</button>}
        {layout === "race" && <button className={view === "strategy" ? "active" : ""} onClick={() => setView("strategy")}>STRATEGY</button>}
        <button className="tv-nav-item" onClick={enterTV}>TV MODE</button>
        <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>SETTINGS</button>
      </nav>
      <div className="header-actions">
        <div className={`connection-state connection-${connectionClass}`}><i />{connectionLabel}</div>
        <ReplayLibrary catalog={session.catalog} selected={session.selectedCatalogSession} selectedKey={session.selectedSessionKey} viewingMode={session.viewingMode} downloadState={session.downloadState} downloadError={session.downloadError} onSelect={(key) => { session.chooseSession(key); setView("session"); }} onGoLive={goLive} onWatchReplay={session.watchReplay} onDownload={() => void session.downloadReplay()} />
      </div>
      <details className="phone-menu"><summary aria-label="Open navigation">•••</summary><nav aria-label="Phone menu"><button onClick={(event) => { setView("session"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>SESSION</button><button onClick={(event) => { setView("driver"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>DRIVER</button>{layout === "race" && <button onClick={(event) => { setView("battle"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>COMPARE DRIVERS</button>}<button onClick={enterTV}>TV MODE</button><button onClick={(event) => { setView("settings"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>SETTINGS</button></nav></details>
    </header>
    {view !== "settings" && <SessionStrip navigationGeneration={session.navigationGeneration} session={session.state.session} selected={session.selectedCatalogSession} viewingMode={session.viewingMode} livePhase={session.livePhase} liveNow={liveNow} onGoLive={goLive} />}
    <main ref={workspaceRef} className={`workspace workspace-${layout} workspace-view-${view}`}>
    {session.downloadJobs.filter((job) => job.status !== "AVAILABLE").map((job) => <section className="live-source-state" role="status" key={job.sessionKey}><strong>REPLAY {job.sessionKey}: {job.status}</strong><Kerb />{job.error && <p>{job.error}</p>}</section>)}
      {view !== "settings" && session.viewingMode === "replay" && <ReplayRecordingNotice metadata={session.metadata} />}
      {view !== "settings" && session.transport === "connecting" && !session.connectionError && (!hasOpened ? <BrandOpening phase="Opening session · waiting for timing and playback controls" /> : <section className="live-source-state" role="status"><strong>RECONNECTING</strong><p>Waiting for timing and playback controls.</p></section>)}
      {view !== "settings" && session.connectionError && <section className="service-unavailable"><strong>SLIPSTREAM DATA UNAVAILABLE</strong><p>{session.connectionError}</p><span>No sample race has been substituted.</span></section>}
      {view !== "settings" && (!session.connectionError || session.state.updated_at !== null) && session.viewingMode === "live" && !dataAvailable && <section className={`live-source-state live-source-${session.livePhase.toLowerCase()}`}><strong>{connectionLabel}</strong><p>{session.livePhase === "PRE_EVENT" ? "WAITING FOR PUBLIC TIMING FEED" : session.livePhase === "CONNECTING" ? "Connecting to the public Formula 1 timing source." : "Public live timing is currently unavailable. No replay or sample state has been substituted."}</p></section>}
      {view === "session" && (!session.connectionError || session.state.updated_at !== null) && layout === "race" && <RaceView story={story} state={session.state} analytics={session.analytics} replayAvailable={dataAvailable} intervalsAvailable={session.capabilities?.capabilities.intervals ?? false} positionMode={positionMode} viewingMode={session.viewingMode} layout={preferences.raceLayout} onLayoutChange={preferences.setRaceLayout} onOpenLayoutEditor={openLayoutEditor} onSelectDriver={openDriver} towerView={preferences.towerView} onTowerViewChange={preferences.setTowerView} onOpenStrategy={() => setView("strategy")} />}
      {view === "session" && (!session.connectionError || session.state.updated_at !== null) && layout === "qualifying" && <QualifyingView story={story} timingWidth={preferences.sessionWidths.qualifying} onTimingWidthChange={(qualifying) => preferences.setSessionWidths((widths) => ({ ...widths, qualifying }))} towerView={preferences.qualifyingTowerView} onTowerViewChange={preferences.setQualifyingTowerView} state={session.state} analytics={session.analytics} sessionKind={classification.kind} replayAvailable={dataAvailable} positionMode={positionMode} viewingMode={session.viewingMode} sectorTimingAvailable={sectorTimingAvailable} onSelectDriver={openDriver} />}
      {view === "session" && (!session.connectionError || session.state.updated_at !== null) && layout === "practice" && <PracticeView analytics={session.analytics} story={story} timingWidth={preferences.sessionWidths.practice} onTimingWidthChange={(practice) => preferences.setSessionWidths((widths) => ({ ...widths, practice }))} state={session.state} replayAvailable={dataAvailable} positionMode={positionMode} viewingMode={session.viewingMode} onSelectDriver={openDriver} />}
      {view === "session" && (!session.connectionError || session.state.updated_at !== null) && layout === "unsupported" && <Panel eyebrow="SESSION LAYOUT" title="Session layout unavailable"><div className="unknown-block"><strong>LAYOUT - NOT AVAILABLE</strong><p>This session is present in the catalog but does not classify as Race, Qualifying, or Practice.</p></div></Panel>}
      {view === "strategy" && layout === "race" && (!session.connectionError || session.state.updated_at !== null) && <StrategyView state={session.state} analytics={session.analytics} onSelectDriver={openDriver} />}
      {view === "battle" && layout === "race" && (!session.connectionError || session.state.updated_at !== null) && <BattleView state={session.state} analytics={session.analytics} recommendedPair={recommendedBattle} positionMode={positionMode} viewingMode={session.viewingMode} preferences={preferences.battle} onPreferencesChange={preferences.setBattle} />}
      {view === "driver" && (!session.connectionError || session.state.updated_at !== null) && (!focusedDriver || !session.state.drivers[focusedDriver]) && <DriverPickerView state={session.state} onSelect={openDriver} />}
      {view === "driver" && focusedDriver && session.state.drivers[focusedDriver] && <div className="driver-view-actions"><button aria-pressed={preferences.tv.selectedDriverNumber === focusedDriver} onClick={() => preferences.setTV({ ...preferences.tv, selectedDriverNumber: preferences.tv.selectedDriverNumber === focusedDriver ? null : focusedDriver })}>{preferences.tv.selectedDriverNumber === focusedDriver ? "★ FOLLOWING" : "☆ FOLLOW DRIVER"}</button>{layout === "race" && <button onClick={() => { const other = Object.keys(session.state.drivers).find((number) => number !== focusedDriver) ?? ""; preferences.setBattle({ mode: "pinned", pinnedPair: [focusedDriver, other] }); setView("battle"); }}>COMPARE WITH…</button>}</div>}
      {view === "driver" && (!session.connectionError || session.state.updated_at !== null) && focusedDriver && session.state.drivers[focusedDriver] && <DriverFocusView state={session.state} analytics={session.analytics} sessionLayout={layout} driverNumber={focusedDriver} history={driverHistory.history} historyError={driverHistory.error} playhead={session.playhead} positionMode={positionMode} viewingMode={session.viewingMode} onChangeDriver={() => setFocusedDriver(null)} onBack={() => setView("session")} />}
      {view === "settings" && <SettingsView appearance={preferences.appearance} onAppearanceChange={preferences.setAppearance} raceLayout={preferences.raceLayout} onRaceLayoutChange={preferences.setRaceLayout} tvPreferences={preferences.tv} onTVPreferencesChange={preferences.setTV} drivers={Object.values(session.state.drivers)} section={settingsSection} onSectionChange={setSettingsSection} />}
      {view === "session" && <div className="session-moments"><StoryMoments sessionKey={storySessionKey} story={session.analytics?.story} recordingVersion={session.analytics?.recordingVersion ?? session.metadata?.recordingVersion} mode={session.viewingMode} generation={session.navigationGeneration} playing={session.isPlaying} speed={session.playbackSpeed} reducedMotion={reducedMotion} /></div>}
      {followedDriver && view !== "driver" && view !== "settings" && <div className="follow-strip"><button onClick={() => openDriver(followedDriver.number)}><span>FOLLOWING</span><strong>P{followedDriver.position ?? "—"} · {followedDriver.code ?? followedDriver.number}</strong><small>{followedDriver.team ?? "—"}</small></button><button aria-label="Stop following driver" onClick={() => preferences.setTV({ ...preferences.tv, selectedDriverNumber: null })}>×</button></div>}
    </main>
    {view !== "settings" && controls}
  </div>;
}
