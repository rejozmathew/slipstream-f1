import { formatSessionDate, utcOffsetLabel } from "../../domain/format";
import type { CatalogSession, LiveConnectionStatus, RaceState, ViewingMode } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";

const liveLabels: Record<LiveConnectionStatus, string> = {
  OFFLINE: "LIVE SOURCE UNAVAILABLE",
  CONNECTING: "LIVE CONNECTING",
  LIVE: "LIVE",
  STALE: "LIVE STALE",
  UNAVAILABLE: "LIVE SOURCE UNAVAILABLE",
};

export function SessionStrip({ session, selected, viewingMode, liveStatus, liveNow, onGoLive }: {
  session: RaceState["session"];
  selected: CatalogSession | null;
  viewingMode: ViewingMode;
  liveStatus: LiveConnectionStatus;
  liveNow: boolean;
  onGoLive: () => void;
}) {
  const date = session.started_at ?? selected?.dateStart ?? null;
  const trackStatus = session.track_status ?? (viewingMode === "replay" && selected?.available ? null : "UNAVAILABLE");
  const modeLabel = viewingMode === "live" ? liveLabels[liveStatus] : "REPLAY";
  return (
    <section className="session-strip">
      <div className="session-title">
        <span className={`session-mode ${viewingMode === "live" ? `live live-${liveStatus.toLowerCase()}` : ""}`}>{modeLabel}</span>
        <h1>{session.meeting_name ?? selected?.meetingName ?? "Session unavailable"}</h1>
        <p>{session.name ?? selected?.sessionName ?? "Select a session"}</p>
        {viewingMode === "replay" && liveNow && <div className="live-now-action"><span>LIVE NOW</span><button onClick={onGoLive}>GO LIVE</button></div>}
      </div>
      <div className="session-stat"><span>DATE</span><DataValue compact value={date ? formatSessionDate(date) : null} /></div>
      <div className="session-stat"><span>LOCAL</span><DataValue compact value={session.local_time ? `${session.local_time.slice(11, 19)} ${utcOffsetLabel(session.gmt_offset)}` : null} /></div>
      <div className="session-stat lap-stat"><span>LAP</span><strong><DataValue compact value={session.lap} /> <i>/</i> <DataValue compact value={session.total_laps} /></strong></div>
      <div className="session-stat track-stat" data-track-status={trackStatus?.toLowerCase().replaceAll(" ", "-")}><span>TRACK</span><DataValue compact value={trackStatus} /></div>
    </section>
  );
}
