import { classifySessionLayout } from "../../domain/sessionLayout";
import { useSlipstreamSession } from "../../hooks/useSlipstreamSession";
import { PracticeView } from "../../views/PracticeView";
import { QualifyingView } from "../../views/QualifyingView";
import { RaceView } from "../../views/RaceView";
import { Panel } from "../shared/Panel";
import { ReplayControls } from "./ReplayControls";
import { ReplayLibrary } from "./ReplayLibrary";
import { SessionStrip } from "./SessionStrip";

export function AppShell() {
  const session = useSlipstreamSession();
  const layout = classifySessionLayout(session.state.session.session_type ?? session.selectedCatalogSession?.sessionType, session.state.session.name ?? session.selectedCatalogSession?.sessionName);
  const replayAvailable = session.metadata?.available ?? session.selectedCatalogSession?.available ?? false;
  const positionMode = session.metadata?.positionMode ?? session.selectedCatalogSession?.positionMode ?? "unavailable";
  return <div className="app-shell">
    <header className="app-header">
      <a className="brand" href="/"><i>SS</i><span><b>SLIPSTREAM</b><small>F1 TIMING</small></span></a>
      <nav aria-label="Session layout"><span className={layout === "race" ? "active" : ""}>RACE</span><span className={layout === "qualifying" ? "active" : ""}>QUALIFYING</span><span className={layout === "practice" ? "active" : ""}>PRACTICE</span></nav>
      <div className={`connection-state connection-${session.transport}`}><i />{session.transport === "stream" ? "REPLAY CONNECTED" : session.transport.toUpperCase()}</div>
    </header>
    <ReplayLibrary catalog={session.catalog} selected={session.selectedCatalogSession} selectedKey={session.selectedSessionKey} downloadState={session.downloadState} downloadError={session.downloadError} onSelect={session.chooseSession} onDownload={() => void session.downloadReplay()} />
    <SessionStrip session={session.state.session} selected={session.selectedCatalogSession} />
    <main>
      {session.connectionError && <section className="service-unavailable"><strong>SLIPSTREAM DATA UNAVAILABLE</strong><p>{session.connectionError}</p><span>No sample race has been substituted.</span></section>}
      {!session.connectionError && layout === "race" && <RaceView state={session.state} replayAvailable={replayAvailable} positionMode={positionMode} />}
      {!session.connectionError && layout === "qualifying" && <QualifyingView state={session.state} replayAvailable={replayAvailable} positionMode={positionMode} />}
      {!session.connectionError && layout === "practice" && <PracticeView state={session.state} replayAvailable={replayAvailable} positionMode={positionMode} />}
      {!session.connectionError && layout === "unsupported" && <Panel eyebrow="SESSION LAYOUT" title="Unsupported session"><div className="unknown-block"><strong>LAYOUT - UNSUPPORTED</strong><p>This session is present in the catalog but does not classify as Race, Qualifying, or Practice.</p></div></Panel>}
    </main>
    <ReplayControls metadata={session.metadata} playhead={session.playhead} isPlaying={session.isPlaying} sequence={session.sequence} onCommand={session.sendReplayCommand} />
  </div>;
}
