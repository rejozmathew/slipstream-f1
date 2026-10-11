import { currentPairGap, completedLapGapTrend } from "../../domain/battle";
import { battleGapPresentation, gapChartModel } from "../../domain/correctness.mjs";
import { formatLapTime } from "../../domain/format";
import { actualStrategyCompounds } from "../../domain/pirelliPresentation.mjs";
import type { AnalyticsSnapshot, Driver, PaceSample, RaceState } from "../../domain/protocol";
import { CompoundBadge, CompoundSequence } from "../shared/CompoundBadge";
import { storyDriverName, storyTeamStyle } from "../story/presentation";

import "./battle-composition.css";

export type BattleCompositionProps = {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  pair: [Driver, Driver] | null;
  posture?: "desktop" | "tv" | "phone";
};

function pitLap(sample: PaceSample) {
  return sample.contaminationReasons.some(reason => /pit|in.lap|out.lap/i.test(reason));
}

export function commonBattleLaps(analytics: AnalyticsSnapshot | null, ahead: Driver, behind: Driver, maximum: number) {
  const other = new Map((analytics?.drivers[behind.number]?.pace.samples ?? []).filter(sample => sample.rawLapTime != null).map(sample => [sample.lap, sample]));
  return (analytics?.drivers[ahead.number]?.pace.samples ?? []).filter(sample => sample.rawLapTime != null && other.has(sample.lap)).slice(-maximum).reverse().map(first => {
    const second = other.get(first.lap)!;
    const pit = pitLap(first) || pitLap(second);
    const comparable = first.quality === "representative" && second.quality === "representative" && !pit;
    return { first, second, pit, comparable, delta: comparable ? second.rawLapTime! - first.rawLapTime! : null };
  });
}

export function BattleComposition({ state, analytics, pair, posture = "desktop" }: BattleCompositionProps) {
  if (!pair) return <section className={`battle-composition battle-composition-${posture}`}><div className="bc-empty"><b>No close battle right now</b><span>A recommendation appears from lap 3 in green running after a known same-lap pair remains within 12 seconds across completed-lap source history.</span></div></section>;
  const [ahead, behind] = [...pair].sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const adjacent = ahead.position != null && behind.position === ahead.position + 1;
  const key = `${ahead.number}:${behind.number}`, reverse = `${behind.number}:${ahead.number}`;
  const candidate = analytics?.battle.candidates.find(item => item.aheadDriverNumber === ahead.number && item.behindDriverNumber === behind.number || item.aheadDriverNumber === behind.number && item.behindDriverNumber === ahead.number);
  const comparison = analytics?.battle.pairs?.[key] ?? analytics?.battle.pairs?.[reverse] ?? candidate;
  const presentation = battleGapPresentation(comparison);
  const gap = currentPairGap(analytics, ahead, behind);
  const history = (analytics?.battle.histories?.[key] ?? analytics?.battle.histories?.[reverse] ?? []).slice(-(posture === "phone" ? 6 : 8));
  const trend = completedLapGapTrend(history.slice(-3));
  const chart = gapChartModel(history);
  const laps = commonBattleLaps(analytics, ahead, behind, posture === "tv" ? 6 : posture === "phone" ? 3 : 4);
  const side = (driver: Driver, following: boolean) => {
    const published = analytics?.publishedStrategy?.drivers[driver.number];
    const stops = published?.actualStrategy?.completedStops ?? analytics?.drivers[driver.number]?.pitEvents.length;
    return <div className={`bc-side${following ? " is-behind" : ""}`} style={storyTeamStyle(driver)}><span className="bc-position">P{driver.position ?? "—"}</span><b className="bc-code">{driver.code ?? driver.number}</b><span className="bc-name">{storyDriverName(driver.number, state.drivers).surname} · {driver.team ?? "—"}</span><div className="bc-facts"><span className="bc-tyre"><CompoundBadge compound={driver.compound} compact /><em>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</em></span><span>{stops == null ? "— stops" : `${stops} stop${stops === 1 ? "" : "s"}`}</span><CompoundSequence compounds={actualStrategyCompounds(published)} compact /></div></div>;
  };
  return <section className={`battle-composition battle-composition-${posture}`}>
    <header className="bc-title"><span>{adjacent ? `BATTLE FOR P${ahead.position}` : `P${ahead.position ?? "—"} VS P${behind.position ?? "—"} · NOT ADJACENT`}</span><b className={`bc-trend bc-trend-${trend.label.toLowerCase().split(" ")[0]}`}>{trend.label === "INSUFFICIENT HISTORY" ? "NEW" : trend.label}</b></header>
    <div className="bc-main">{side(ahead, false)}<div className="bc-middle"><span title={presentation.label}>{gap == null ? "PAIR GAP · UNAVAILABLE" : comparison?.gapBasis === "interval_to_ahead" ? "INTERVAL" : "GAP"}</span><strong>{gap == null ? "—" : gap.toFixed(3)}</strong><small>{gap == null ? presentation.note : `SECONDS · ${behind.code ?? behind.number} BEHIND ${ahead.code ?? ahead.number}`}</small></div>{side(behind, true)}</div>
    <div className="bc-lower"><section className="bc-panel"><h3>GAP AT EACH LAP</h3>{chart ? <><div className="bc-chart"><svg viewBox="0 0 100 38" preserveAspectRatio="none" role="img" aria-label="Completed-lap pair gap history"><line x1="0" y1="34" x2="100" y2="34" /><polyline points={chart.points.map((point: { x: number; y: number }) => `${point.x},${point.y}`).join(" ")} />{chart.points.map((point: { x: number; y: number }, index: number) => <circle key={index} cx={point.x} cy={point.y} r=".8" />)}</svg><span className="bc-chart-min">{chart.min.toFixed(2)}</span><b className="bc-chart-last">{history.at(-1)!.gapSeconds.toFixed(2)}</b></div><p>laps {history[0].lap}–{history.at(-1)!.lap} · completed-lap source history</p></> : <><div className="bc-no-history">Not racing each other on recent laps</div><p>Appears after two completed laps together</p></>}</section>
      <section className="bc-panel"><h3>LAP TIMES</h3>{laps.length ? <table className="bc-laps"><thead><tr><th scope="col">LAP</th><th scope="col">{ahead.code ?? ahead.number}</th><th scope="col">{behind.code ?? behind.number}</th><th scope="col">FASTER</th></tr></thead><tbody>{laps.map(row => {
        const faster = row.delta == null || Math.abs(row.delta) < .0005 ? null : row.delta > 0 ? ahead : behind;
        return <tr key={row.first.lap} className={row.pit ? "is-pit-lap" : ""}><td>L{row.first.lap}</td><td className={faster === ahead ? "is-faster" : ""}>{formatLapTime(row.first.rawLapTime)}</td><td className={faster === behind ? "is-faster" : ""}>{formatLapTime(row.second.rawLapTime)}</td><td>{row.pit ? <span className="bc-pit-lap">PIT LAP</span> : !row.comparable ? <span className="bc-pit-lap">NON-REP</span> : faster ? <span className="bc-faster" style={storyTeamStyle(faster)}><b>{faster.code ?? faster.number}</b><em>−{Math.abs(row.delta!).toFixed(3)}</em></span> : "level"}</td></tr>;
      })}</tbody></table> : <div className="bc-no-history">No common completed laps yet</div>}</section>
    </div>
    {gap != null && <p className="bc-basis">{presentation.label} · {presentation.note}</p>}
  </section>;
}
