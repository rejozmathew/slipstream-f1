import type { RaceState } from "../domain/protocol";
import { Panel } from "../components/shared/Panel";

export function DriverPickerView({ state, onSelect }: { state: RaceState; onSelect: (driverNumber: string) => void }) {
  const drivers = Object.values(state.drivers).sort((left, right) => (left.position ?? 999) - (right.position ?? 999));
  return <div className="driver-picker-view">
    <header className="experience-heading"><div><span>DRIVER</span><h1>Choose a driver</h1><p>Open factual pace, battle, pit, and shared Strategy context.</p></div></header>
    <Panel eyebrow="CURRENT SESSION" title="Driver picker">
      {drivers.length === 0 && <div className="panel-empty">NO DRIVER TIMING ROWS YET</div>}
      <div className="driver-picker-grid">{drivers.map((driver) => <button key={driver.number} onClick={() => onSelect(driver.number)} style={{ borderColor: `#${driver.team_colour ?? "313a45"}` }}><strong>{driver.number}</strong><span><b>{driver.code ?? driver.number}</b><small>{driver.name ?? "Driver name unavailable"}</small><em>{driver.team ?? "Team unavailable"}</em></span><i>P{driver.position ?? "—"}</i></button>)}</div>
    </Panel>
  </div>;
}
