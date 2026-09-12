import { useMemo, useState } from "react";

import { driverLifecycle, lifecycleClassName } from "../../domain/lifecycle";
import { buildTrackGeometry } from "../../domain/trackGeometry";
import { circuitReference } from "../../domain/circuitReference";
import { isTrackMapActive, trackCoverage } from "../../domain/correctness.mjs";
import type { Driver, PositionMode, RaceState, ViewingMode } from "../../domain/protocol";
import { Panel } from "../shared/Panel";

type TrackMapProps = {
  circuit: RaceState["circuit"];
  session: RaceState["session"];
  drivers: Driver[];
  positionMode: PositionMode;
  viewingMode: ViewingMode;
  focusedDriverNumbers?: string[];
  focusLabel?: string;
};

export function TrackMap({ circuit, session, drivers, positionMode, viewingMode, focusedDriverNumbers = [], focusLabel }: TrackMapProps) {
  const geometry = useMemo(() => buildTrackGeometry(circuit.path, circuit.rotation ?? 0), [circuit.path, circuit.rotation]);
  const reference = geometry ? null : circuitReference(session);
  const [failedReference, setFailedReference] = useState<string | null>(null);
  const focus = new Set(focusedDriverNumbers);
  const positioned = drivers.filter((driver) => isTrackMapActive(driver) && positionMode !== "unavailable" && (
    (positionMode === "precise_xy" && driver.x != null && driver.y != null)
    || driver.track_position != null
  )).sort((a, b) => Number(focus.has(a.number)) - Number(focus.has(b.number)));
  const coverage = trackCoverage(drivers, geometry ? positionMode : "unavailable");
  return (
    <Panel eyebrow="CIRCUIT" title={circuit.name ?? session.circuit ?? "Track map"} action={geometry ? <span className="panel-badge">OUTLINE READY</span> : undefined} className="map-panel">
      <div className="track-map">
        {geometry ? <svg viewBox="0 0 1000 650" role="img" aria-label={`${circuit.name ?? "Circuit"} outline`} preserveAspectRatio="xMidYMid meet">
          <polyline className="circuit-shadow" points={geometry.polyline} />
          <polyline className="circuit-line" points={geometry.polyline} />
          <polyline className="circuit-centerline" points={geometry.polyline} />
          <circle className="start-marker" cx={geometry.points[0].x} cy={geometry.points[0].y} r="8" />
          <g className="car-markers">
            {positioned.map((driver) => {
              const hasPrecisePosition = positionMode === "precise_xy" && driver.x != null && driver.y != null;
              const point = hasPrecisePosition ? geometry.project(driver.x!, driver.y!) : geometry.pointAt(driver.track_position ?? 0);
              const lifecycle = driverLifecycle(driver);
              const focusClass = focus.has(driver.number) ? " car-focused" : focus.size > 0 ? " car-deemphasized" : "";
              return <g className={"car-marker " + lifecycleClassName(driver) + focusClass} key={driver.number} aria-label={[driver.code ?? driver.number, lifecycle.label].filter(Boolean).join(" ")} transform={`translate(${point.x} ${point.y})`}>
                <title>{[driver.name ?? driver.code ?? driver.number, lifecycle.label].filter(Boolean).join(" · ")}</title>
                <circle r="12" fill={`#${(driver.team_colour ?? "ffffff").replace(/^#/, "")}`} />
                <text textAnchor="middle" dominantBaseline="central">{driver.code ?? driver.number}</text>
              </g>;
            })}
          </g>
        </svg> : reference ? <div className="circuit-reference">
          {failedReference !== reference.imageUrl ? <img src={reference.imageUrl} alt={reference.label} referrerPolicy="no-referrer" onError={() => setFailedReference(reference.imageUrl)} /> : <div className="panel-empty">MAP IMAGE UNAVAILABLE</div>}
          <a href={reference.sourceUrl} target="_blank" rel="noreferrer">Official circuit map · Formula 1 ↗</a>
          <span>REFERENCE MAP · CAR POSITIONS UNAVAILABLE</span>
        </div> : <div className="panel-empty">CIRCUIT SHAPE - UNAVAILABLE</div>}
        {geometry && positionMode === "unavailable" && <div className="map-note">{viewingMode === "live" ? "CAR POSITION NOT AVAILABLE IN PUBLIC LIVE FEED" : "CAR POSITION NOT AVAILABLE FOR THIS REPLAY"}</div>}
        {geometry && positionMode !== "unavailable" && positioned.length === 0 && <div className="map-note">CAR POSITION NOT YET AVAILABLE</div>}
        {coverage.inactiveLabels.length > 0 && <div className="map-out-list"><strong>OUT / STOPPED</strong>{coverage.inactiveLabels.map((label: string) => <span key={label}>{label}</span>)}</div>}
        {geometry && ["race", "sprint"].includes(session.session_kind) && <div className="map-center"><strong>{session.lap ?? "—"}</strong><span>{focusLabel ?? "CURRENT LAP"}</span></div>}
      </div>
      <footer className="panel-footer"><span>{geometry ? "SHAPE · OBSERVED" : reference ? "MAP · OFFICIAL REFERENCE" : "SHAPE · UNAVAILABLE"}</span>{geometry && positionMode !== "unavailable" && <span>{positionMode === "timing_estimate" ? "POSITION · APPROX · TIMING-DERIVED" : "POSITION · SOURCE X/Y"}</span>}<span title={coverage.unpositionedLabels.join(", ") || "All active cars positioned"}>ACTIVE COVERAGE · {coverage.positioned}/{coverage.eligible}{coverage.unpositioned ? ` · ${coverage.unpositioned} UNPOSITIONED` : ""}</span></footer>
    </Panel>
  );
}
