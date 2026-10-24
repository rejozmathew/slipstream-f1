import { useMemo, useRef, useState, type CSSProperties } from "react";

import { driverLifecycle, lifecycleClassName } from "../../domain/lifecycle";
import { buildTrackGeometry } from "../../domain/trackGeometry";
import { circuitReference } from "../../domain/circuitReference";
import { isTrackMapActive, trackCoverage } from "../../domain/correctness.mjs";
import type { Driver, PositionMode, RaceState, ViewingMode } from "../../domain/protocol";
import { useAxisMotion, useTrackMotion, useTrackViewport } from "../../hooks/useTrackPresentation";
import { Panel } from "../shared/Panel";
import { RaceOrderRibbon, TrackAxisDots, type RaceOrderRibbonProps } from "./RaceOrderRibbon";
import { mapMarkerOffsets, packAxis, packMapCars, trackNormal, type MapCar, type TrackPosture, type TrackPresentationContext } from "./trackPresentation";
import "./trackPresentation.css";

type TrackMapProps = TrackPresentationContext & {
  circuit: RaceState["circuit"];
  session: RaceState["session"];
  drivers: Driver[];
  positionMode: PositionMode;
  viewingMode: ViewingMode;
  focusedDriverNumbers?: string[];
  focusLabel?: string;
  lapInHeader?: boolean;
  posture?: TrackPosture;
  showRibbon?: boolean;
  battlePairs?: RaceOrderRibbonProps["battlePairs"];
};
const teamStyle = (driver: Driver) => ({ "--team": `#${(driver.team_colour ?? "77808f").replace(/^#/, "")}` }) as CSSProperties;
const hasProgress = (driver: Driver) => driver.track_position != null && Number.isFinite(driver.track_position) && driver.track_position >= 0 && driver.track_position <= 1;

export function TrackMap({ circuit, session, drivers, positionMode, viewingMode, focusedDriverNumbers = [], focusLabel, lapInHeader = false, posture, showRibbon, battlePairs, ...motion }: TrackMapProps) {
  // Snapshot packets may contain a newly allocated but unchanged path. Retain the
  // geometry identity so that ordinary position updates do not reset smoothing.
  const shape = JSON.stringify([circuit.path, circuit.rotation ?? 0]);
  const geometry = useMemo(() => { const [path, rotation] = JSON.parse(shape); return buildTrackGeometry(path, rotation); }, [shape]);
  const reference = geometry ? null : circuitReference(session);
  const [failedReference, setFailedReference] = useState<string | null>(null);
  const map = useRef<HTMLDivElement>(null), svg = useRef<SVGSVGElement>(null), line = useRef<HTMLDivElement>(null);
  const viewport = useTrackViewport(map, posture), lineViewport = useTrackViewport(line, posture);
  const focus = new Set(focusedDriverNumbers);
  const positioned = [...drivers].filter((driver) => isTrackMapActive(driver) && !driverLifecycle(driver).inPit && positionMode !== "unavailable" && (
    (positionMode === "precise_xy" && Number.isFinite(driver.x) && Number.isFinite(driver.y)) || hasProgress(driver)
  )).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const lineAvailable = !geometry && !reference && positionMode !== "unavailable" && positioned.some(hasProgress);
  const coverage = trackCoverage(drivers, geometry || lineAvailable ? positionMode : "unavailable");
  const pits = drivers.filter((driver) => driverLifecycle(driver).inPit && !driverLifecycle(driver).terminal && !driverLifecycle(driver).stopped);
  const unit = Math.max(1000 / viewport.width, 650 / viewport.height);
  const radius = (viewport.posture === "tv" ? 12 : viewport.posture === "phone" ? 7 : 8) * unit * viewport.scale;
  const font = (viewport.posture === "tv" ? 18 : viewport.posture === "phone" ? 10.5 : 12) * unit * viewport.scale;
  const cars: MapCar[] = geometry ? positioned.map((driver, priority) => {
    const precise = positionMode === "precise_xy" && Number.isFinite(driver.x) && Number.isFinite(driver.y);
    const fraction = precise ? null : driver.track_position!;
    return { driver, fraction, priority, point: precise ? geometry.project(driver.x!, driver.y!) : geometry.pointAt(fraction!), normal: trackNormal(geometry, driver.track_position ?? 0), focus: focus.has(driver.number) };
  }) : [];
  const groups = packMapCars(cars, radius, font, viewport.posture === "tv" ? 10 : viewport.posture === "phone" ? 3 : 6);
  const markerOffsets = mapMarkerOffsets(groups, radius * 1.15);
  const grouped = [...markerOffsets.values()].some(offset => offset.x !== 0 || offset.y !== 0);
  const representatives = new Map(groups.map((group) => [group.representative.driver.number, group]));
  const targets = cars.map((car) => ({ number: car.driver.number, point: car.point, fraction: car.fraction, lap: car.driver.lap }));
  useTrackMotion(svg, targets, geometry, motion);
  useAxisMotion(line, drivers, motion);
  const lineCars = positioned.filter(hasProgress).map((driver, priority) => ({ driver, x: driver.track_position!, focus: focus.has(driver.number), priority }));
  const packing = packAxis(lineCars.map((car) => ({ key: car.driver.number, x: car.x * lineViewport.width, priority: car.priority, focus: car.focus, label: car.driver.code ?? car.driver.number })), viewport.posture, lineViewport.width, lineViewport.scale);
  const start = geometry?.pointAt(0), normal = geometry ? trackNormal(geometry, 0) : null;
  const race = ["race", "sprint"].includes(session.session_kind);
  const ribbon = showRibbon ?? (race && focusedDriverNumbers.length === 0);
  return <Panel eyebrow="CIRCUIT" title={circuit.name ?? session.circuit ?? "Track map"} action={lapInHeader && race ? <span className="panel-badge">LAP {session.lap ?? "—"} / {session.total_laps ?? "—"}</span> : focusLabel ? <span className="panel-badge">{focusLabel}</span> : undefined} className={`map-panel track-presentation map--${viewport.posture}${ribbon ? " has-ribbon" : ""}`}>
    <div ref={map} className={`track-map${lineAvailable ? " has-track-line" : ""}`}>
      {geometry ? <svg ref={svg} viewBox="0 0 1000 650" role="img" aria-label={`${circuit.name ?? "Circuit"} outline${positionMode === "timing_estimate" ? " with approximate car positions" : ""}`} preserveAspectRatio="xMidYMid meet">
        <polyline className="circuit-shadow" points={geometry.polyline} />
        <polyline className="circuit-line" points={geometry.polyline} />
        <polyline className="circuit-centerline" points={geometry.polyline} />
        {start && normal && <line className="circuit-start-finish" x1={start.x - normal.x * 16} y1={start.y - normal.y * 16} x2={start.x + normal.x * 16} y2={start.y + normal.y * 16} />}
        <g className="car-markers">{[...cars].sort((a, b) => Number(a.focus || a.priority === 0) - Number(b.focus || b.priority === 0)).map((car) => {
          const driver = car.driver, lifecycle = driverLifecycle(driver), group = representatives.get(driver.number), offset = markerOffsets.get(driver.number) ?? { x: 0, y: 0 };
          return <g className={`car-marker ${lifecycleClassName(driver)}${car.focus ? " is-focus" : ""}${driver.position === 1 ? " is-leader" : ""}`} key={driver.number} data-track-driver={driver.number} style={teamStyle(driver)} aria-label={driver.code ?? driver.number} transform={`translate(${car.point.x} ${car.point.y})`}>
            <title>{[driver.name ?? driver.code ?? driver.number, lifecycle.label].filter(Boolean).join(" · ")}</title>
            {(offset.x !== 0 || offset.y !== 0) && <line className="track-car-anchor" x1={0} y1={0} x2={offset.x} y2={offset.y} />}
            <circle className="track-car-dot" cx={0} cy={0} r={radius} />
            {(offset.x !== 0 || offset.y !== 0) ? <g className="track-car-badge" transform={`translate(${offset.x} ${offset.y})`}>
              <rect x={-radius * 1.1} y={-radius * .65} width={radius * 2.2} height={radius * 1.3} rx={radius * .2} />
              <text textAnchor="middle" dominantBaseline="central" style={{ fontSize: radius * .64 }}>{driver.code ?? driver.number}</text>
            </g> : group?.label && <text className="track-car-label" x={group.label.x} y={group.label.y} textAnchor="middle" dominantBaseline="central" style={{ fontSize: font * (car.focus ? 1.12 : 1) }}>{driver.code ?? driver.number}</text>}
          </g>;
        })}</g>
      </svg> : reference ? <div className="circuit-reference">
        {failedReference !== reference.imageUrl ? <img src={reference.imageUrl} alt={reference.label} referrerPolicy="no-referrer" onError={() => setFailedReference(reference.imageUrl)} /> : <div className="panel-empty">MAP IMAGE UNAVAILABLE</div>}
        <a href={reference.sourceUrl} target="_blank" rel="noreferrer">Official circuit map · Formula 1 ↗</a><span>REFERENCE MAP · CAR POSITIONS UNAVAILABLE</span>
      </div> : lineAvailable ? <div className={`track-line tline--${viewport.posture}`}>
        <div className="tline-head"><b>AROUND THE LAP</b><span>known progress, without a circuit outline</span></div>
        <div ref={line} className="tline-track"><div className="tline-rail" /><div className="tline-ticks">{[.25, .5, .75].map((fraction) => <i key={fraction} style={{ left: `${fraction * 100}%` }} />)}</div><div className="tline-cars"><TrackAxisDots cars={lineCars.map((car) => ({ ...car, placement: packing.get(car.driver.number) }))} posture={viewport.posture} /></div></div>
        <div className="tline-axis"><span>START / FINISH</span><span>ONE LAP</span></div>
      </div> : <div className="panel-empty">CIRCUIT SHAPE - UNAVAILABLE</div>}
      {geometry && positionMode === "unavailable" && <div className="map-note">{viewingMode === "live" ? "CAR POSITION NOT AVAILABLE IN PUBLIC LIVE FEED" : "CAR POSITION NOT AVAILABLE FOR THIS REPLAY"}</div>}
      {geometry && positionMode !== "unavailable" && positioned.length === 0 && <div className="map-note">CAR POSITION NOT YET AVAILABLE</div>}
      {(pits.length > 0 || coverage.inactiveLabels.length > 0) && <div className="track-map-boxes">
        {pits.length > 0 && <div className="track-map-box map-pit-list"><b>PIT LANE</b><span>{pits.map((driver) => <em key={driver.number} style={teamStyle(driver)}>{driver.code ?? driver.number}</em>)}</span></div>}
        {coverage.inactiveLabels.length > 0 && <div className="track-map-box map-out-list"><b>OUT / STOPPED</b><span>{coverage.inactiveLabels.map((label: string) => <em key={label}>{label}</em>)}</span></div>}
      </div>}
    </div>
    <footer className="panel-footer track-map-footer"><span>{geometry ? "SHAPE · OBSERVED" : reference ? "MAP · OFFICIAL REFERENCE" : "SHAPE · UNAVAILABLE"}</span>{(geometry || lineAvailable) && positionMode !== "unavailable" && <span>{positionMode === "timing_estimate" ? "POSITION · APPROX · TIMING-DERIVED" : "POSITION · SOURCE X/Y"}</span>}<span title={coverage.unpositionedLabels.join(", ") || "All active cars positioned"}>ACTIVE COVERAGE · {coverage.positioned}/{coverage.eligible}{coverage.unpositioned ? ` · ${coverage.unpositioned} UNPOSITIONED` : ""}</span></footer>
    {grouped && <div className="track-group-note">Overlapping labels separated · dots stay on track</div>}
    {ribbon && <RaceOrderRibbon drivers={drivers} focusedDriverNumbers={focusedDriverNumbers} posture={viewport.posture} battlePairs={battlePairs} {...motion} />}
  </Panel>;
}
