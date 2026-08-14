import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { PositionMode, RaceState } from "../domain/protocol";

export function PracticeView({ state, replayAvailable, positionMode }: { state: RaceState; replayAvailable: boolean; positionMode: PositionMode }) {
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  return <div className="session-layout practice-layout">
    <TimingTower drivers={drivers} variant="practice" replayAvailable={replayAvailable} />
    <div className="analysis-stack">
      <Panel eyebrow="ANALYTICS CAPABILITY" title="Run analysis"><div className="metric-placeholders"><div><span>REPRESENTATIVE PACE</span><strong>UNKNOWN</strong></div><div><span>QUALIFYING SIMULATION</span><strong>UNSUPPORTED</strong></div><p>Lap observations are retained with quality and stint context. Production analytics are outside this milestone.</p></div></Panel>
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div>;
}
