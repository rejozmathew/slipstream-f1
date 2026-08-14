import { useState, type PointerEvent as ReactPointerEvent } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { PositionMode, RaceState } from "../domain/protocol";

type RaceViewProps = { state: RaceState; replayAvailable: boolean; positionMode: PositionMode };
const presets = { balanced: 62, timing: 74, strategy: 52 } as const;

export function RaceView({ state, replayAvailable, positionMode }: RaceViewProps) {
  const [timingWidth, setTimingWidth] = useState<number>(presets.balanced);
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const container = event.currentTarget.parentElement;
    if (!container) return;
    const move = (pointer: PointerEvent) => {
      const bounds = container.getBoundingClientRect();
      const next = ((pointer.clientX - bounds.left) / bounds.width) * 100;
      setTimingWidth(Math.min(76, Math.max(48, next)));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  };

  return (
    <div className="race-workspace">
      <div className="layout-presets" role="group" aria-label="Race layout preset">
        <span>LAYOUT</span><button onClick={() => setTimingWidth(presets.balanced)}>BALANCED</button><button onClick={() => setTimingWidth(presets.timing)}>TIMING FOCUS</button><button onClick={() => setTimingWidth(presets.strategy)}>STRATEGY FOCUS</button>
      </div>
      <div className="race-split" style={{ gridTemplateColumns: `minmax(0, ${timingWidth}fr) 9px minmax(350px, ${100 - timingWidth}fr)` }}>
        <TimingTower drivers={drivers} variant="race" replayAvailable={replayAvailable} />
        <button className="split-handle" onPointerDown={startDrag} aria-label="Resize timing and analysis panels"><span /></button>
        <div className="analysis-stack">
          <Panel eyebrow="ANALYTICS CAPABILITY" title="Strategy outlook" action={<span className="status-unknown">UNSUPPORTED</span>}>
            <div className="unknown-block"><strong>STRATEGY - UNKNOWN</strong><p>No production strategy model is enabled. Slipstream will not infer a recommendation from incomplete evidence.</p></div>
          </Panel>
          <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
          <Conditions weather={state.weather} session={state.session} />
          <RaceControl messages={state.race_control} />
        </div>
      </div>
    </div>
  );
}
