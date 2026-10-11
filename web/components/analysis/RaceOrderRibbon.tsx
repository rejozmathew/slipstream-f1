import { useRef, useState, type CSSProperties } from "react";
import type { BattleCandidate, Driver } from "../../domain/protocol";
import { driverLifecycle } from "../../domain/lifecycle";
import { useAxisMotion, useTrackViewport } from "../../hooks/useTrackPresentation";
import { focusWithNeighbours, packAxis, ribbonScale, sourceLapGap, sourceLeaderGap, type AxisPlacement, type TrackPosture, type TrackPresentationContext } from "./trackPresentation";
import "./trackPresentation.css";

export type RaceOrderRibbonProps = TrackPresentationContext & {
  drivers: Driver[]; focusedDriverNumbers?: string[]; posture?: TrackPosture;
  battlePairs?: ReadonlyArray<Pick<BattleCandidate, "aheadDriverNumber" | "behindDriverNumber" | "comparisonState">>;
};
export type AxisDriver = { driver: Driver; x: number; focus: boolean; placement?: AxisPlacement };
export function TrackAxisDots({ cars, posture }: { cars: AxisDriver[]; posture: TrackPosture }) {
  return <>{cars.map(({ driver, x, focus, placement }) => placement?.show && <div key={driver.number} data-axis-driver={driver.number}
    className={`track-axis-dot d1--${posture}${placement.lane < 0 ? " no-lbl" : ""}${focus ? " is-focus" : ""}${driver.position === 1 ? " is-lead" : ""}${driverLifecycle(driver).inPit ? " is-pit" : ""}`}
    style={{ left: `${x * 100}%`, "--team": `#${(driver.team_colour ?? "77808f").replace(/^#/, "")}`, "--lane": Math.max(0, placement.lane), "--shift": `${placement.shift}px` } as CSSProperties}
    title={`${driver.name ?? driver.code ?? driver.number}${driver.gap_to_leader ? ` · ${driver.gap_to_leader}` : ""}${placement.count > 1 ? ` · ${placement.count} cars share this marker` : ""}`}>
    <i /><s /><b>{driver.code ?? driver.number}{placement.count > 1 && <em>{placement.count}</em>}</b>
  </div>)}</>;
}

/** Axis coordinates are only canonical, numeric gaps to the leader. */
export function RaceOrderRibbon({ drivers, focusedDriverNumbers = [], posture, battlePairs = [], ...motion }: RaceOrderRibbonProps) {
  const root = useRef<HTMLDivElement>(null), plot = useRef<HTMLDivElement>(null);
  const viewport = useTrackViewport(plot, posture);
  useAxisMotion(root, drivers, motion);
  const focus = focusWithNeighbours(drivers, focusedDriverNumbers);
  const rows = [...drivers].filter((driver) => { const lifecycle = driverLifecycle(driver); return !lifecycle.stopped && !lifecycle.retiredIndicated && (!lifecycle.terminal || lifecycle.status === "FINISHED"); }).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const gaps = new Map(rows.map((driver) => [driver.number, sourceLeaderGap(driver)]));
  const maxGap = Math.max(0, ...[...gaps.values()].filter((gap): gap is number => gap != null));
  const [scale, setScale] = useState(() => ribbonScale(maxGap));
  const wanted = ribbonScale(maxGap, scale);
  if (wanted !== scale) setScale(wanted);
  const tick = scale <= 5 ? 1 : scale <= 20 ? 5 : scale <= 45 ? 10 : scale <= 90 ? 15 : scale <= 180 ? 30 : 60;
  const ticks = Array.from({ length: Math.floor(scale / tick) + 1 }, (_, index) => index * tick);
  const lapped = rows.filter(sourceLapGap);
  const positions = rows.flatMap((driver, index) => {
    const gap = gaps.get(driver.number);
    return gap == null || sourceLapGap(driver) ? [] : [{ driver, x: Math.min(1, gap / scale), focus: focus.has(driver.number), priority: index }];
  });
  const packing = packAxis(positions.map(({ driver, x, focus: selected, priority }) => ({ key: driver.number, x: x * viewport.width, priority, focus: selected, label: driver.code ?? driver.number })), viewport.posture, viewport.width, viewport.scale);
  const byNumber = new Map(positions.map((car) => [car.driver.number, car.x]));
  const links = battlePairs.flatMap((pair) => {
    const ahead = byNumber.get(pair.aheadDriverNumber), behind = byNumber.get(pair.behindDriverNumber);
    return pair.comparisonState !== "COMPARABLE" || ahead == null || behind == null || behind < ahead ? [] : [{ key: `${pair.aheadDriverNumber}-${pair.behindDriverNumber}`, ahead, width: Math.max(.005, behind - ahead) }];
  });
  return <div ref={root} className={`race-order-ribbon ribbon--${viewport.posture}`} aria-label="Race order in time">
    <header className="rb-head"><b>RACE ORDER IN TIME</b><span>gap to the leader, from timing</span>{lapped.length > 0 && <span className="rb-lapped"><b>LAPPED</b><span>{lapped.map((driver) => <em key={driver.number} style={{ "--team": `#${(driver.team_colour ?? "77808f").replace(/^#/, "")}` } as CSSProperties}>{driver.code ?? driver.number}</em>)}</span></span>}</header>
    <div ref={plot} className="rb-plot"><div className="rb-axis">{ticks.map((value) => <span key={value} style={{ left: `${value / scale * 100}%` }}><em>{value === 0 ? "LEADER" : `+${value}s`}</em></span>)}</div>
      <div className="rb-links">{links.map((link) => <i key={link.key} style={{ left: `${link.ahead * 100}%`, width: `${link.width * 100}%` }} />)}</div>
      <div className="rb-cars"><TrackAxisDots cars={positions.map((car) => ({ ...car, placement: packing.get(car.driver.number) }))} posture={viewport.posture} /></div>
      {!positions.some((car) => car.driver.position !== 1) && <div className="rb-empty">Timing gaps not yet available.</div>}
    </div>
  </div>;
}
