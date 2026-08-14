import type { CatalogSession, ReplayCatalog } from "../../domain/protocol";

type ReplayLibraryProps = {
  catalog: ReplayCatalog | null;
  selected: CatalogSession | null;
  selectedKey: string | null;
  downloadState: "idle" | "downloading" | "error";
  downloadError: string | null;
  onSelect: (sessionKey: string) => void;
  onDownload: () => void;
};

export function ReplayLibrary({ catalog, selected, selectedKey, downloadState, downloadError, onSelect, onDownload }: ReplayLibraryProps) {
  return (
    <section className="replay-library" aria-label="Replay library">
      <label>
        <span>SEASON / WEEKEND / SESSION</span>
        <select value={selectedKey ?? ""} onChange={(event) => onSelect(event.target.value)} disabled={!catalog}>
          {!catalog && <option>CATALOG UNAVAILABLE</option>}
          {catalog?.sessions.map((session) => (
            <option value={session.sessionKey} key={session.sessionKey}>
              {session.year} - {session.meetingName} - {session.sessionName}{session.isLive ? " - LIVE" : session.available ? "" : " - NOT DOWNLOADED"}
            </option>
          ))}
        </select>
      </label>
      {selected && !selected.available && (
        <button className="button button-primary" onClick={onDownload} disabled={!catalog?.downloadsEnabled || !selected.downloadable || downloadState === "downloading"}>
          {downloadState === "downloading" ? "DOWNLOADING..." : "DOWNLOAD REPLAY"}
        </button>
      )}
      {selected && !selected.available && !selected.downloadable && <span className="library-note">NOT YET AVAILABLE</span>}
      {selected && !selected.available && !catalog?.downloadsEnabled && <span className="library-note">SERVER DOWNLOADS DISABLED</span>}
      {downloadError && <span className="library-error">{downloadError}</span>}
    </section>
  );
}
