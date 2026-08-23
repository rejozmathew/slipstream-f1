import { useEffect, useRef, useState } from "react";

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
import { Panel } from "../shared/Panel";
import { LiveControls } from "./LiveControls";
import { ReplayControls } from "./ReplayControls";
import { ReplayLibrary } from "./ReplayLibrary";
import { SessionStrip } from "./SessionStrip";

type ProductView = "session" | "battle" | "driver" | "strategy" | "tv" | "settings";

export function AppShell() {
  const session = useSlipstreamSession();
  const preferences = useProductPreferences();
  const [view, setView] = useState<ProductView>("session");
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
  const positionMode = session.capabilities?.positionMode ?? session.metadata?.positionMode ?? session.selectedCatalogSession?.positionMode ?? "unavailable";
  const sectorTimingAvailable = session.capabilities?.capabilities.sector_timing ?? false;
  const driverHistory = useDriverHistory(session.viewingMode === "replay" ? session.selectedSessionKey : null, focusedDriver);
  const recommendedBattle = useBattleRecommendation(session.analytics, session.state);
  const rootProps = {
    className: `app-shell view-${view} mode-${session.viewingMode}`,
    "data-background": preferences.appearance.background,
    "data-accent": preferences.appearance.accent,
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

  if (view === "tv") return <div {...rootProps}><TVModeView state={session.state} analytics={session.analytics} recommendedBattle={recommendedBattle} sessionLayout={layout} sessionKind={classification.kind} replayAvailable={dataAvailable} positionMode={positionMode} sectorTimingAvailable={sectorTimingAvailable} preferences={preferences.tv} onPreferencesChange={preferences.setTV} onExit={() => setView("session")} /></div>;

  return <div {...rootProps}>
    <header className="app-header">
      <button className="brand" onClick={() => setView("session")}><i>SS</i><span><b>SLIPSTREAM</b><small>F1 TIMING</small></span></button>
      <nav aria-label="Product navigation">
        <button className={view === "session" ? "active" : ""} onClick={() => setView("session")}>SESSION</button>
        <button className={view === "driver" ? "active" : ""} onClick={() => setView("driver")}>DRIVER</button>
        {layout === "race" && <button className={view === "battle" ? "active" : ""} onClick={() => setView("battle")}>BATTLE</button>}
        {layout === "race" && <button className={view === "strategy" ? "active" : ""} onClick={() => setView("strategy")}>STRATEGY</button>}
        <button className="tv-nav-item" onClick={() => setView("tv")}>TV MODE</button>
        <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>SETTINGS</button>
      </nav>
      <div className="header-actions">
        <div className={`connection-state connection-${connectionClass}`}><i />{connectionLabel}</div>
        <ReplayLibrary catalog={session.catalog} selected={session.selectedCatalogSession} selectedKey={session.selectedSessionKey} viewingMode={session.viewingMode} downloadState={session.downloadState} downloadError={session.downloadError} onSelect={(key) => { session.chooseSession(key); setView("session"); }} onGoLive={goLive} onWatchReplay={session.watchReplay} onDownload={() => void session.downloadReplay()} />
      </div>
    </header>
    {view !== "settings" && <SessionStrip session={session.state.session} selected={session.selectedCatalogSession} viewingMode={session.viewingMode} livePhase={session.livePhase} liveNow={liveNow} onGoLive={goLive} />}
    <main ref={workspaceRef} className={`workspace workspace-${layout} workspace-view-${view}`}>
      {view !== "settings" && session.connectionError && <section className="service-unavailable"><strong>SLIPSTREAM DATA UNAVAILABLE</strong><p>{session.connectionError}</p><span>No sample race has been substituted.</span></section>}
      {view !== "settings" && !session.connectionError && session.viewingMode === "live" && !dataAvailable && <section className={`live-source-state live-source-${session.livePhase.toLowerCase()}`}><strong>{connectionLabel}</strong><p>{session.livePhase === "PRE_EVENT" ? "WAITING FOR PUBLIC TIMING FEED" : session.livePhase === "CONNECTING" ? "Connecting to the public Formula 1 timing source." : "Public live timing is currently unavailable. No replay or sample state has been substituted."}</p></section>}
      {view === "session" && !session.connectionError && layout === "race" && <RaceView state={session.state} analytics={session.analytics} replayAvailable={dataAvailable} positionMode={positionMode} layout={preferences.raceLayout} onLayoutChange={preferences.setRaceLayout} onOpenLayoutEditor={openLayoutEditor} onSelectDriver={openDriver} towerView={preferences.towerView} onTowerViewChange={preferences.setTowerView} onOpenStrategy={() => setView("strategy")} />}
      {view === "session" && !session.connectionError && layout === "qualifying" && <QualifyingView state={session.state} analytics={session.analytics} sessionKind={classification.kind} replayAvailable={dataAvailable} positionMode={positionMode} sectorTimingAvailable={sectorTimingAvailable} onSelectDriver={openDriver} />}
      {view === "session" && !session.connectionError && layout === "practice" && <PracticeView state={session.state} replayAvailable={dataAvailable} positionMode={positionMode} onSelectDriver={openDriver} />}
      {view === "session" && !session.connectionError && layout === "unsupported" && <Panel eyebrow="SESSION LAYOUT" title="Session layout unavailable"><div className="unknown-block"><strong>LAYOUT - NOT AVAILABLE</strong><p>This session is present in the catalog but does not classify as Race, Qualifying, or Practice.</p></div></Panel>}
      {view === "strategy" && layout === "race" && !session.connectionError && <StrategyView state={session.state} analytics={session.analytics} onSelectDriver={openDriver} />}
      {view === "battle" && layout === "race" && !session.connectionError && <BattleView state={session.state} analytics={session.analytics} recommendedPair={recommendedBattle} positionMode={positionMode} />}
      {view === "driver" && !session.connectionError && (!focusedDriver || !session.state.drivers[focusedDriver]) && <DriverPickerView state={session.state} onSelect={openDriver} />}
      {view === "driver" && !session.connectionError && focusedDriver && session.state.drivers[focusedDriver] && <DriverFocusView state={session.state} analytics={session.analytics} sessionLayout={layout} driverNumber={focusedDriver} history={driverHistory.history} historyError={driverHistory.error} playhead={session.playhead} positionMode={positionMode} onChangeDriver={() => setFocusedDriver(null)} onBack={() => setView("session")} />}
      {view === "settings" && <SettingsView appearance={preferences.appearance} onAppearanceChange={preferences.setAppearance} raceLayout={preferences.raceLayout} onRaceLayoutChange={preferences.setRaceLayout} tvPreferences={preferences.tv} onTVPreferencesChange={preferences.setTV} drivers={Object.values(session.state.drivers)} section={settingsSection} onSectionChange={setSettingsSection} />}
    </main>
    {view !== "settings" && session.viewingMode === "replay" && <ReplayControls metadata={session.metadata} playhead={session.playhead} isPlaying={session.isPlaying} sequence={session.sequence} commandAvailable={session.commandAvailable} onCommand={session.sendReplayCommand} />}
    {view !== "settings" && session.viewingMode === "live" && <LiveControls phase={session.livePhase} commandAvailable={session.commandAvailable} onCommand={session.sendReplayCommand} />}
  </div>;
}
