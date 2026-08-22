import type { CatalogSession, ReplayCatalog, ViewingMode } from "../../domain/protocol";

type ReplayLibraryProps = {
  catalog: ReplayCatalog | null;
  selected: CatalogSession | null;
  selectedKey: string | null;
  viewingMode: ViewingMode;
  downloadState: "idle" | "downloading" | "error";
  downloadError: string | null;
  onSelect: (sessionKey: string) => void;
  onGoLive: () => void;
  onWatchReplay: () => void;
  onDownload: () => void;
};

export function ReplayLibrary({ catalog, selected, selectedKey, viewingMode, downloadState, downloadError, onSelect, onGoLive, onWatchReplay, onDownload }: ReplayLibraryProps) {
  const sessions = catalog?.sessions ?? [];
  const years = [...new Set(sessions.map((item) => item.year))].sort((a, b) => b - a);
  const selectedYear = selected?.year ?? years[0] ?? null;
  const yearSessions = sessions.filter((item) => item.year === selectedYear);
  const meetings = yearSessions.filter((item, index, items) => items.findIndex((candidate) => candidate.meetingKey === item.meetingKey) === index);
  const selectedMeetingKey = selected?.meetingKey ?? meetings[0]?.meetingKey ?? null;
  const meetingSessions = yearSessions.filter((item) => item.meetingKey === selectedMeetingKey);
  const selectionState = viewingMode === "live"
    ? selected?.liveStatus === "LIVE" ? "LIVE" : `LIVE ${selected?.liveStatus ?? "UNAVAILABLE"}`
    : selected?.available ? "REPLAY" : "NOT DOWNLOADED";

  return (
    <details className="replay-library" aria-label="Live and replay session selector">
      <summary>
        <span>{viewingMode === "live" ? "LIVE" : "REPLAY"}</span>
        <strong>{selected ? `${selected.year} / ${selected.meetingName}` : "SESSION LIBRARY"}</strong>
        <em>{selected?.sessionName ?? "SELECT SESSION"} - {selectionState}</em>
        <i aria-hidden="true" />
      </summary>
      <div className="replay-popover">
        <header><strong>SELECT SESSION</strong><span>SEASON / WEEKEND / SESSION</span></header>
        <div className="replay-library-fields">
          <label className="season-select"><span>SEASON</span><select aria-label="Season" value={selectedYear ?? ""} disabled={!catalog} onChange={(event) => {
            const first = sessions.find((item) => item.year === Number(event.target.value));
            if (first) onSelect(first.sessionKey);
          }}>
            {!catalog && <option>CATALOG UNAVAILABLE</option>}
            {years.map((year) => <option value={year} key={year}>{year}</option>)}
          </select></label>
          <label className="weekend-select"><span>WEEKEND</span><select aria-label="Race weekend" value={selectedMeetingKey ?? ""} disabled={!catalog} onChange={(event) => {
            const first = yearSessions.find((item) => item.meetingKey === event.target.value);
            if (first) onSelect(first.sessionKey);
          }}>
            {meetings.map((meeting) => <option value={meeting.meetingKey} key={meeting.meetingKey}>{meeting.meetingName}</option>)}
          </select></label>
          <label className="session-select"><span>SESSION</span><select aria-label="Weekend session" value={selectedKey ?? ""} disabled={!catalog} onChange={(event) => onSelect(event.target.value)}>
            {meetingSessions.map((session) => <option value={session.sessionKey} key={session.sessionKey}>{session.sessionName}{session.liveAvailable ? " - LIVE NOW" : session.available ? " - REPLAY" : " - NOT DOWNLOADED"}</option>)}
          </select></label>
        </div>
        <div className="replay-library-actions">
          {catalog?.liveSessionKey && viewingMode === "replay" && <button className="button button-live" onClick={onGoLive}>GO LIVE</button>}
          {viewingMode === "live" && selected?.available && <button className="button" onClick={onWatchReplay}>WATCH REPLAY</button>}
          {selected && !selected.available && !selected.liveAvailable && <button className="button button-primary" onClick={onDownload} disabled={!catalog?.downloadsEnabled || !selected.downloadable || downloadState === "downloading"}>{downloadState === "downloading" ? "DOWNLOADING..." : "DOWNLOAD REPLAY"}</button>}
          {selected && !selected.available && !selected.liveAvailable && !selected.downloadable && <span className="library-note">NOT YET AVAILABLE</span>}
          {selected && !selected.available && !selected.liveAvailable && !catalog?.downloadsEnabled && <span className="library-note">SERVER DOWNLOADS DISABLED</span>}
          {downloadError && <span className="library-error">{downloadError}</span>}
        </div>
      </div>
    </details>
  );
}
