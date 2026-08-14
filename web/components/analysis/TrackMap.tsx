import { useMemo } from "react";

import { buildTrackGeometry } from "../../domain/trackGeometry";
import type { Driver, PositionMode, RaceState } from "../../domain/protocol";
import { Panel } from "../shared/Panel";

type TrackMapProps = {
  circuit: RaceState["circuit"];
  session: RaceState["session"];
  drivers: Driver[];
  positionMode: PositionMode;
};

export function TrackMap({ circuit, session, drivers, positionMode }: TrackMapProps) {
  const geometry = useMemo(() => buildTrackGeometry(circuit.path, circuit.rotation ?? 0), [circuit.path, circuit.rotation]);
  const positioned = drivers.filter((driver) => positionMode === "precise_xy"
    ? driver.x != null && driver.y != null
    : driver.track_position != null);
  return (
    <Panel eyebrow="CIRCUIT" title={circuit.name ?? session.circuit ?? "Track map"} action={<span className="panel-badge">{geometry ? "OUTLINE READY" : "UNAVAILABLE"}</span>} className="map-panel">
      <div className="track-map">
        {geometry ? <svg viewBox="0 0 1000 650" role="img" aria-label={`${circuit.name ?? "Circuit"} outline`}>
          <polyline className="circuit-shadow" points={geometry.polyline} />
          <polyline className="circuit-line" points={geometry.polyline} />
          <polyline className="circuit-centerline" points={geometry.polyline} />
          <circle className="start-marker" cx={geometry.points[0].x} cy={geometry.points[0].y} r="8" />
        </svg> : <div className="panel-empty">CIRCUIT SHAPE - UNAVAILABLE</div>}
        {geometry && positioned.map((driver) => {
          const point = positionMode === "precise_xy" ? geometry.project(driver.x ?? 0, driver.y ?? 0) : geometry.pointAt(driver.track_position ?? 0);
          return <span className="car-dot" key={driver.number} style={{ left: `${point.x / 10}%`, top: `${point.y / 6.5}%`, backgroundColor: `#${driver.team_colour ?? "ffffff"}` }}>{driver.position ?? driver.code}</span>;
        })}
        {geometry && positionMode === "unavailable" && <div className="map-note">CAR POSITION - UNSUPPORTED</div>}
        {geometry && positionMode !== "unavailable" && positioned.length === 0 && <div className="map-note">CAR POSITION - UNKNOWN AT THIS SESSION TIME</div>}
        <div className="map-center"><strong>{session.lap ?? "?"}</strong><span>CURRENT LAP</span></div>
      </div>
      <footer className="panel-footer"><span>SHAPE - OBSERVED</span><span>POSITION - {positionMode === "precise_xy" ? "SOURCE X/Y" : positionMode === "timing_estimate" ? "APPROX" : "UNSUPPORTED"}</span></footer>
    </Panel>
  );
}