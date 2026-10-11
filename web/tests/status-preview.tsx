/* Manual visual fixture: real components/styles, explicitly labelled test data. */
import { createRoot } from "react-dom/client";
import { SessionStrip } from "../components/shell/SessionStrip";
import { StoryMomentCard } from "../components/story/StoryMoments";
import { EMPTY_RACE_STATE, type StoryEvent } from "../domain/protocol";
import "../app/globals.css";
import "../app/redesign.css";
import "../components/shared/rail-status.css";

const flags = ["GREEN", "YELLOW", "VSC", "VSC_ENDING", "SAFETY_CAR", "RED_FLAG", "CHEQUERED"] as const;
const event = (flag: string): StoryEvent => ({ id: flag, sessionKey: "visual-fixture", kind: "FLAG", occurredAt: "2026-07-26T13:22:00Z", availableAt: "2026-07-26T13:22:00Z", availableSequence: 1, driverNumbers: [], cause: flag, state: "confirmed", priority: 3, supersedes: null, lap: 20, phase: null, title: flag, detail: "", evidence: [], data: { flag } });
createRoot(document.getElementById("root")!).render(<div className="app-shell" data-reduced-motion="true" style={{ padding: 24, display: "block", height: "auto" }}>
  <h1 style={{ fontSize: 22 }}>Status presentation · validation fixtures</h1>
  <p style={{ marginBottom: 20 }}>Real presentation components. These are test states, not a live session.</p>
  {flags.map(flag => <div key={flag} style={{ marginBottom: 12 }}><SessionStrip session={{ ...EMPTY_RACE_STATE.session, layout_family: "race", meeting_name: "Hungarian Grand Prix", name: "Race", lap: 20, total_laps: 70, display_status: flag, track_status: flag }} selected={null} viewingMode="replay" livePhase="PRE_EVENT" liveNow={false} onGoLive={() => {}} /></div>)}
  <div className="story-moments to-layer--desktop" style={{ position: "static", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, width: "100%", maxWidth: "none" }}>
    {["SAFETY_CAR", "RED_FLAG", "VSC", "CHEQUERED"].map(flag => <StoryMomentCard key={flag} event={event(flag)} />)}
  </div>
</div>);
