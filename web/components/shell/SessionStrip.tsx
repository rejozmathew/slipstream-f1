import { useEffect, useMemo, useState } from "react";

import { formatSessionDate, utcOffsetLabel } from "../../domain/format";
import type { CatalogSession, LiveProductPhase, RaceState, ViewingMode } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";

function countdownLabel(target: string | null, now: number) {
  if (!target) return "—";
  const remaining = Math.max(0, Math.floor((Date.parse(target) - now) / 1000));
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function sessionStartLabel(date: string | null, offset: string | null) {
  if (!date) return null;
  const parts = offset?.match(/^([+-])(\d{2}):(\d{2})/);
  const offsetMs = parts ? (parts[1] === "-" ? -1 : 1) * (Number(parts[2]) * 60 + Number(parts[3])) * 60_000 : 0;
  return `${new Date(Date.parse(date) + offsetMs).toISOString().slice(11, 16)} ${utcOffsetLabel(offset)}`;
}

export function SessionStrip({ session, selected, viewingMode, livePhase, liveNow, onGoLive }: {
  session: RaceState["session"];
  selected: CatalogSession | null;
  viewingMode: ViewingMode;
  livePhase: LiveProductPhase;
  liveNow: boolean;
  onGoLive: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const date = session.started_at ?? selected?.dateStart ?? null;
  const gmtOffset = session.gmt_offset ?? selected?.gmtOffset ?? null;
  const preEvent = viewingMode === "live" && livePhase === "PRE_EVENT";
  const qualifying = session.layout_family === "qualifying" || selected?.layoutFamily === "qualifying";
  const canonicalStatus = session.display_status ?? session.track_status;
  const displayStatus = !canonicalStatus || canonicalStatus === "UNKNOWN"
    ? (viewingMode === "replay" && selected?.available ? null : "UNAVAILABLE")
    : canonicalStatus.replaceAll("_", " ");
  const modeLabel = viewingMode === "live" ? livePhase.replaceAll("_", " ") : "REPLAY";
  const startsIn = useMemo(() => countdownLabel(selected?.dateStart ?? date, now), [date, now, selected?.dateStart]);
  useEffect(() => {
    if (!preEvent) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [preEvent]);
  return (
    <section className={`session-strip${preEvent ? " session-strip-pre-event" : ""}`}>
      <div className="session-title">
        <span className={`session-mode ${viewingMode === "live" ? `live live-${livePhase.toLowerCase()}` : ""}`}>{modeLabel}</span>
        <h1>{session.meeting_name ?? selected?.meetingName ?? "Session unavailable"}</h1>
        <p>{session.name ?? selected?.sessionName ?? "Select a session"}</p>
        {preEvent && <div className="pre-event-inline"><span>STARTS IN <strong>{startsIn}</strong></span><b>{sessionStartLabel(selected?.dateStart ?? date, gmtOffset)}</b><em>WAITING FOR PUBLIC TIMING FEED</em></div>}
        {viewingMode === "replay" && liveNow && <div className="live-now-action"><span>LIVE NOW</span><button onClick={onGoLive}>GO LIVE</button></div>}
      </div>
      <div className="session-stat"><span>DATE</span><DataValue compact value={date ? formatSessionDate(date) : null} /></div>
      <div className="session-stat"><span>LOCAL</span><DataValue compact value={session.local_time ? `${session.local_time.slice(11, 19)} ${utcOffsetLabel(gmtOffset)}` : sessionStartLabel(selected?.dateStart ?? null, gmtOffset)} /></div>
      {qualifying ? <div className="session-stat lap-stat qualifying-clock-stat"><span>{session.qualifying_phase === "UNKNOWN" ? "PHASE" : session.qualifying_phase}</span><strong><DataValue compact value={session.session_clock} /></strong></div> : <div className="session-stat lap-stat"><span>LAP</span><strong><DataValue compact value={session.lap} /> <i>/</i> <DataValue compact value={session.total_laps} /></strong></div>}
      <div className="session-stat track-stat" data-track-status={displayStatus?.toLowerCase().replaceAll(" ", "-")}><span>STATUS</span><DataValue compact value={displayStatus} /></div>
    </section>
  );
}
