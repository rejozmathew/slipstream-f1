import { useState } from "react";

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
import { TVModeView } from "../../views/TVModeView";
import { Panel } from "../shared/Panel";
import { ReplayControls } from "./ReplayControls";
import { ReplayLibrary } from "./ReplayLibrary";
import { SessionStrip } from "./SessionStrip";

type ProductView = "session" | "battle" | "driver" | "tv" | "settings";

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
  const replayAvailable = session.metadata?.available ?? session.selectedCatalogSession?.available ?? false;
  const positionMode = session.metadata?.positionMode ?? session.selectedCatalogSession?.positionMode ?? "unavailable";
  const driverHistory = useDriverHistory(session.selectedSessionKey, focusedDriver);
  const recommendedBattle = useBattleRecommendation(session.analytics, session.state);
  const rootProps = {
    className: `app-shell view-${view}`,
    "data-background": preferences.appearance.background,
    "data-accent": preferences.appearance.accent,
  };

  const openDriver = (driverNumber: string) => {
    setFocusedDriver(driverNumber);
    preferences.setLastDriverNumber(driverNumber);
    setView("driver");
  };
  const openLayoutEditor = () => {
    setSettingsSection("layouts");
    setView("settings");
  };

  if (view === "tv") return <div {...rootProps}><TVModeView state={session.state} analytics={session.analytics} recommendedBattle={recommendedBattle} sessionLayout={layout} sessionKind={classification.kind} replayAvailable={replayAvailable} positionMode={positionMode} preferences={preferences.tv} onPreferencesChange={preferences.setTV} onExit={() => setView("session")} /></div>;

  return <div {...rootProps}>
    <header className="app-header">
      <button className="brand" onClick={() => setView("session")}><i>SS</i><span><b>SLIPSTREAM</b><small>F1 TIMING</small></span></button>
      <nav aria-label="Product navigation">
        <button className={view === "session" ? "active" : ""} onClick={() => setView("session")}>SESSION</button>
        <button className={view === "driver" ? "active" : ""} onClick={() => setView("driver")}>DRIVER</button>
        <button className={view === "battle" ? "active" : ""} onClick={() => setView("battle")}>BATTLE</button>
        <button className="tv-nav-item" onClick={() => setView("tv")}>TV MODE</button>
        <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>SETTINGS</button>
      </nav>
      <div className="header-actions">
        <div className={`connection-state connection-${session.transport}`}><i />{session.transport === "stream" ? "REPLAY CONNECTED" : session.transport.toUpperCase()}</div>
        <ReplayLibrary catalog={session.catalog} selected={session.selectedCatalogSession} selectedKey={session.selectedSessionKey} downloadState={session.downloadState} downloadError={session.downloadError} onSelect={(key) => { session.chooseSession(key); setView("session"); }} onDownload={() => void session.downloadReplay()} />
      </div>
    </header>
    {view !== "settings" && <SessionStrip session={session.state.session} selected={session.selectedCatalogSession} />}
    <main className={`workspace workspace-${layout} workspace-view-${view}`}>
      {view !== "settings" && session.connectionError && <section className="service-unavailable"><strong>SLIPSTREAM DATA UNAVAILABLE</strong><p>{session.connectionError}</p><span>No sample race has been substituted.</span></section>}
      {view === "session" && !session.connectionError && layout === "race" && <RaceView state={session.state} analytics={session.analytics} replayAvailable={replayAvailable} positionMode={positionMode} layout={preferences.raceLayout} onLayoutChange={preferences.setRaceLayout} onOpenLayoutEditor={openLayoutEditor} onSelectDriver={openDriver} towerView={preferences.towerView} onTowerViewChange={preferences.setTowerView} />}
      {view === "session" && !session.connectionError && layout === "qualifying" && <QualifyingView state={session.state} sessionKind={classification.kind} replayAvailable={replayAvailable} positionMode={positionMode} onSelectDriver={openDriver} />}
      {view === "session" && !session.connectionError && layout === "practice" && <PracticeView state={session.state} replayAvailable={replayAvailable} positionMode={positionMode} onSelectDriver={openDriver} />}
      {view === "session" && !session.connectionError && layout === "unsupported" && <Panel eyebrow="SESSION LAYOUT" title="Session layout unavailable"><div className="unknown-block"><strong>LAYOUT - NOT AVAILABLE</strong><p>This session is present in the catalog but does not classify as Race, Qualifying, or Practice.</p></div></Panel>}
      {view === "battle" && !session.connectionError && <BattleView state={session.state} stateHistory={session.stateHistory} analytics={session.analytics} recommendedPair={recommendedBattle} />}
      {view === "driver" && !session.connectionError && (!focusedDriver || !session.state.drivers[focusedDriver]) && <DriverPickerView state={session.state} onSelect={openDriver} />}
      {view === "driver" && !session.connectionError && focusedDriver && session.state.drivers[focusedDriver] && <DriverFocusView state={session.state} analytics={session.analytics} driverNumber={focusedDriver} history={driverHistory.history} historyError={driverHistory.error} playhead={session.playhead} positionMode={positionMode} onChangeDriver={() => setFocusedDriver(null)} onBack={() => setView("session")} />}
      {view === "settings" && <SettingsView appearance={preferences.appearance} onAppearanceChange={preferences.setAppearance} raceLayout={preferences.raceLayout} onRaceLayoutChange={preferences.setRaceLayout} tvPreferences={preferences.tv} onTVPreferencesChange={preferences.setTV} drivers={Object.values(session.state.drivers)} section={settingsSection} onSectionChange={setSettingsSection} />}
    </main>
    {view !== "settings" && <ReplayControls metadata={session.metadata} playhead={session.playhead} isPlaying={session.isPlaying} sequence={session.sequence} commandAvailable={session.commandAvailable} onCommand={session.sendReplayCommand} />}
  </div>;
}
