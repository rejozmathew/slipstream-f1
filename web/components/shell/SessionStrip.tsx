import { formatSessionDate, utcOffsetLabel } from "../../domain/format";
import type { CatalogSession, RaceState } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";

export function SessionStrip({ session, selected }: { session: RaceState["session"]; selected: CatalogSession | null }) {
  const date = session.started_at ?? selected?.dateStart ?? null;
  const trackStatus = session.track_status ?? (selected?.available ? null : "UNAVAILABLE");
  return (
    <section className="session-strip">
      <div className="session-title">
        <span className={`session-mode ${selected?.isLive ? "live" : ""}`}>{selected?.isLive ? "LIVE" : "REPLAY"}</span>
        <h1>{session.meeting_name ?? selected?.meetingName ?? "Session unavailable"}</h1>
        <p>{session.name ?? selected?.sessionName ?? "Select a session from the replay library"}</p>
      </div>
      <div className="session-stat"><span>DATE</span><DataValue compact value={date ? formatSessionDate(date) : null} /></div>
      <div className="session-stat"><span>LOCAL</span><DataValue compact value={session.local_time ? `${session.local_time.slice(11, 19)} ${utcOffsetLabel(session.gmt_offset)}` : null} /></div>
      <div className="session-stat lap-stat"><span>LAP</span><strong><DataValue compact value={session.lap} /> <i>/</i> <DataValue compact value={session.total_laps} /></strong></div>
      <div className="session-stat track-stat" data-track-status={trackStatus?.toLowerCase().replaceAll(" ", "-")}><span>TRACK</span><DataValue compact value={trackStatus} /></div>
    </section>
  );
}
