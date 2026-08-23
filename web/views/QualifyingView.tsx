import { useEffect, useMemo, useState } from "react";

import { Conditions } from "../components/analysis/Conditions";
import { RaceControl } from "../components/analysis/RaceControl";
import { TrackMap } from "../components/analysis/TrackMap";
import { CompoundBadge } from "../components/shared/CompoundBadge";
import { DataValue } from "../components/shared/DataValue";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import type { AnalyticsSnapshot, PositionMode, QualifyingIntelligence, RaceState, SessionKind } from "../domain/protocol";

function DriverSummary({ value }: { value: QualifyingIntelligence["cutLine"]["cutoff"] }) {
  if (!value) return <span>—</span>;
  return <strong>P{value.position} · {value.code ?? value.driverNumber} <small>{value.bestLap ?? "—"}</small></strong>;
}

function CutLinePanel({ intelligence, sprint }: { intelligence: QualifyingIntelligence | null; sprint: boolean }) {
  const phaseLabel = intelligence?.phase === "UNKNOWN" ? (sprint ? "SQ UNKNOWN" : "Q UNKNOWN") : intelligence?.phase ?? "UNKNOWN";
  return <Panel eyebrow="FACTUAL SESSION INTELLIGENCE" title="Session / cut line" className="qualifying-cut-panel">
    <div className="qualifying-cut-grid">
      <div><span>PHASE</span><strong>{phaseLabel}</strong></div>
      <div><span>TIME</span><DataValue compact value={intelligence?.sessionClock ?? null} /></div>
      <div><span>BENCHMARK</span><strong>{intelligence?.benchmark ? `${intelligence.benchmark.code ?? intelligence.benchmark.driverNumber} · ${intelligence.benchmark.lapTime}` : "—"}</strong></div>
      <div><span>ADVANCE</span><strong>{intelligence?.cutLine.advancePosition ? `TOP ${intelligence.cutLine.advancePosition}` : "—"}</strong></div>
      <div><span>CUTOFF</span><DriverSummary value={intelligence?.cutLine.cutoff ?? null} /></div>
      <div><span>FIRST OUT</span><DriverSummary value={intelligence?.cutLine.firstOut ?? null} /></div>
    </div>
    {intelligence?.phase === "UNKNOWN" && <p className="qualifying-evidence-note">Phase remains UNKNOWN because normalized source evidence has not established it.</p>}
  </Panel>;
}

function AttemptsPanel({ intelligence }: { intelligence: QualifyingIntelligence | null }) {
  const attempts = useMemo(() => Object.values(intelligence?.drivers ?? {}).flatMap((driver) => driver.attempts.map((attempt) => ({ ...attempt, driverNumber: driver.driverNumber }))).sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt)).slice(0, 24), [intelligence]);
  return <Panel eyebrow="CURSOR-SAFE LAP EVIDENCE" title="Attempts" className="qualifying-attempts-panel">
    {attempts.length === 0 && <div className="panel-empty">NO FACTUAL ATTEMPTS AT THIS CURSOR</div>}
    <div className="qualifying-attempt-list">{attempts.map((attempt) => <div key={`${attempt.driverNumber}-${attempt.attempt}-${attempt.occurredAt}`}><strong>{attempt.driverNumber}</strong><span>{attempt.phase === "UNKNOWN" ? "PHASE —" : attempt.phase} · ATTEMPT {attempt.attempt}</span><b>{attempt.lapTime ?? "—"}</b><CompoundBadge compound={attempt.compound} compact /><em>{attempt.tyreAge == null ? "—" : `${attempt.tyreAge}L`} · {attempt.tyreUsage === "UNKNOWN" ? "—" : attempt.tyreUsage}</em></div>)}</div>
  </Panel>;
}

export function QualifyingView({ state, analytics, sessionKind, replayAvailable, positionMode, onSelectDriver }: { state: RaceState; analytics: AnalyticsSnapshot | null; sessionKind: SessionKind; replayAvailable: boolean; positionMode: PositionMode; onSelectDriver: (driverNumber: string) => void }) {
  const [mobileTab, setMobileTab] = useState<"timing" | "cutline" | "attempts" | "sectors">("timing");
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const intelligence = analytics?.qualifying?.status === "AVAILABLE" ? analytics.qualifying : null;
  const sprintQualifying = sessionKind === "sprint_qualifying";
  const hasAttempts = Object.values(intelligence?.drivers ?? {}).some((driver) => driver.attempts.length > 0);
  const hasSectors = drivers.some((driver) => driver.sector_1 != null || driver.sector_2 != null || driver.sector_3 != null);
  const tabs = useMemo(() => ["timing", "cutline", ...(hasAttempts ? ["attempts"] : []), ...(hasSectors ? ["sectors"] : [])] as Array<"timing" | "cutline" | "attempts" | "sectors">, [hasAttempts, hasSectors]);
  useEffect(() => {
    if (!tabs.includes(mobileTab)) queueMicrotask(() => setMobileTab("timing"));
  }, [mobileTab, tabs]);
  const cutLine = <CutLinePanel intelligence={intelligence} sprint={sprintQualifying} />;
  return <><div className="session-layout qualifying-layout session-desktop">
    <TimingTower drivers={drivers} variant="qualifying" analytics={analytics} replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} />
    <div className="analysis-stack">
      {cutLine}
      <TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} />
      <Conditions weather={state.weather} session={state.session} />
      <RaceControl messages={state.race_control} />
    </div>
  </div><div className="mobile-session mobile-qualifying-session"><nav className="mobile-priority-tabs" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }}>{tabs.map((tab) => <button className={mobileTab === tab ? "active" : ""} key={tab} onClick={() => setMobileTab(tab)}>{tab.toUpperCase()}</button>)}</nav><div className="mobile-session-content">{mobileTab === "timing" ? <TimingTower drivers={drivers} variant="qualifying" analytics={analytics} replayAvailable={replayAvailable} onSelectDriver={onSelectDriver} /> : mobileTab === "cutline" ? cutLine : mobileTab === "attempts" ? <AttemptsPanel intelligence={intelligence} /> : <Panel eyebrow="FACTUAL SECTORS" title="Current sector evidence"><div className="qualifying-sector-list">{drivers.filter((driver) => driver.sector_1 != null || driver.sector_2 != null || driver.sector_3 != null).map((driver) => <div key={driver.number}><strong>{driver.code ?? driver.number}</strong><span>S1 {driver.sector_1 ?? "—"}</span><span>S2 {driver.sector_2 ?? "—"}</span><span>S3 {driver.sector_3 ?? "—"}</span></div>)}</div></Panel>}</div></div></>;
}
