import type { AnalyticsSnapshot, RaceState } from "../../domain/protocol";
import { storyDriverName, storyTeamStyle } from "../story/presentation";
import { driverLifecycle } from "../../domain/lifecycle";
import "./tv-result.css";

export function TVResult({ state, analytics }: { state: RaceState; analytics: AnalyticsSnapshot | null }) {
  const verdict = analytics?.story?.result;
  if (!verdict || verdict.state === "none") return <div className="ref-result-wait"><b>Result available after the flag</b><span>The live timing order is still changing.</span></div>;
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const top = drivers.filter(driver => driver.position != null && driver.position <= 3 && drivers.filter(other => other.position === driver.position).length === 1);
  const result = [...(analytics?.story?.events ?? [])].reverse().find(event => ["RESULT", "RESULT_CORRECTION"].includes(event.kind));
  const fastest = [...(analytics?.story?.events ?? [])].reverse().find(event => event.kind === "LAP_IMPROVEMENT" && event.data.sessionBest === true);
  const winner = result?.driverNumbers[0];
  const out = drivers.filter(driver => driverLifecycle(driver).terminal && driver.classification !== "FINISHED");
  return <section className="ref-tv-result"><header><span>{verdict.state === "final" ? "FINAL CLASSIFICATION" : "PROVISIONAL · ON THE ROAD"}</span><h2>{state.session.meeting_name ?? "Race result"}</h2></header><div className="ref-result-podium">{top.map(driver => <article className={`ref-result-pod ref-result-p${driver.position}`} key={driver.number} style={storyTeamStyle(driver)}><span>P{driver.position}</span><b>{driver.code ?? driver.number}</b><strong>{storyDriverName(driver.number, state.drivers).surname}</strong><small>{driver.team ?? "—"}</small><em>{driver.number === winner ? "WINNER ON THE ROAD" : driver.classification === "FINISHED" ? driver.gap_to_leader ?? "FINISHED" : driverLifecycle(driver).label ?? "AWAITING FLAG"}</em></article>)}</div><div className="ref-result-facts"><section><span>FASTEST LAP · OBSERVED</span><strong>{fastest?.driverNumbers[0] ? state.drivers[fastest.driverNumbers[0]]?.code ?? fastest.driverNumbers[0] : "—"}</strong><p>{fastest?.detail ?? "Not available at this cursor"}</p></section><section><span>RACE DISTANCE</span><strong>{state.session.lap ?? "—"}<small> / {state.session.total_laps ?? "—"}</small></strong><p>laps at this viewer cursor</p></section></div>{out.length > 0 && <div className="ref-result-out">{out.map(driver => <span key={driver.number}>{driver.code ?? driver.number} · {driver.classification}</span>)}</div>}<p className="ref-result-note">{verdict.state === "final" ? "Source-confirmed classification." : "Provisional classification · subject to official confirmation."}</p></section>;
}
