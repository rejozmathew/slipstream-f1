import { useEffect, useRef, useState, type CSSProperties } from "react";

import { BrandMark, BrandOpening } from "../components/shared/Brand";
import type { CatalogSession, ReplayCatalog, ViewingMode } from "../domain/protocol";
import type { TVPreferences } from "../hooks/useProductPreferences";

type Props = {
  catalog: ReplayCatalog | null;
  selectedKey: string | null;
  viewingMode: ViewingMode;
  preferences: TVPreferences;
  error: string | null;
  downloadState: "idle" | "downloading" | "error";
  downloadError: string | null;
  onWatch: (sessionKey: string, mode: ViewingMode) => void;
  onSelect: (sessionKey: string) => void;
  onDownload: () => void;
};

function dateLabel(session: CatalogSession) {
  const date = new Date(session.dateStart);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function TVSessionPicker({ catalog, selectedKey, viewingMode, preferences, error, downloadState, downloadError, onWatch, onSelect, onDownload }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const [year, setYear] = useState<number | null>(null);
  const [browsedKey, setBrowsedKey] = useState<string | null>(selectedKey);
  const sessions = catalog?.sessions ?? [];
  const years = [...new Set(sessions.map((session) => session.year))].sort((a, b) => b - a);
  const activeYear = year != null && years.includes(year) ? year : sessions.find((session) => session.sessionKey === selectedKey)?.year ?? years[0];
  const yearSessions = sessions.filter((session) => session.year === activeYear);
  const browsed = yearSessions.find((session) => session.sessionKey === browsedKey) ?? yearSessions[0];
  const selected = sessions.find((session) => session.sessionKey === selectedKey);
  const style = { "--tv-text-size": preferences.textSize ?? 1, "--safe-x": `${preferences.safeArea ?? 0}vw`, "--safe-y": `${preferences.safeArea ?? 0}vh` } as CSSProperties;
  const resumable = selected && (viewingMode === "live" ? selected.liveAvailable : selected.available);
  const ready = Boolean(catalog);
  useEffect(() => {
    root.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
  }, [ready]);
  const navigate = (event: KeyboardEvent) => {
    if (event.key === "Escape" || event.key === "BrowserBack") {
      // The session list is the root of the standalone route.
      event.preventDefault();
      root.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
      return;
    }
    if (!event.key.startsWith("Arrow")) return;
    event.preventDefault();
    const targets = [...(root.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
    const current = document.activeElement as HTMLButtonElement;
    if (!targets.includes(current)) { targets[0]?.focus(); return; }
    const origin = current.getBoundingClientRect();
    const horizontal = event.key === "ArrowLeft" || event.key === "ArrowRight";
    const sign = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    const nearest = targets.filter((target) => target !== current).map((target) => {
      const box = target.getBoundingClientRect();
      const dx = box.left + box.width / 2 - origin.left - origin.width / 2;
      const dy = box.top + box.height / 2 - origin.top - origin.height / 2;
      return { target, forward: (horizontal ? dx : dy) * sign, distance: Math.abs(horizontal ? dx : dy) + Math.abs(horizontal ? dy : dx) * 3 };
    }).filter((candidate) => candidate.forward > 1).sort((left, right) => left.distance - right.distance)[0];
    nearest?.target.focus();
    nearest?.target.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  };
  useEffect(() => {
    const element = root.current;
    element?.addEventListener("keydown", navigate);
    return () => element?.removeEventListener("keydown", navigate);
  });
  return <div ref={root} role="application" aria-label="TV session library" className="tv-session-picker" style={style}>
    <header><BrandMark /><div><span>SLIPSTREAM TV</span><h1>SESSIONS</h1></div>{resumable && <button className="tv-resume" onClick={() => onWatch(selected.sessionKey, viewingMode)}>RESUME {viewingMode.toUpperCase()} · {selected.sessionName}</button>}</header>
    {error && <p className="tv-library-notice" role="alert">{error}</p>}
    {!catalog ? <BrandOpening phase={error ? "Session catalog unavailable" : "Opening session catalog"} /> : <>
      <nav className="tv-library-years" aria-label="Season">{years.map((item) => <button key={item} aria-pressed={item === activeYear} onClick={() => { setYear(item); setBrowsedKey(null); }}>{item}</button>)}</nav>
      <div className="tv-library-content"><section className="tv-session-list" aria-label="Available sessions">{yearSessions.length ? yearSessions.map((session) => <button key={session.sessionKey} aria-pressed={session.sessionKey === browsed?.sessionKey} onClick={() => setBrowsedKey(session.sessionKey)}><small>{session.meetingName}</small><strong>{session.sessionName}</strong><span>{dateLabel(session)} · {session.liveAvailable ? `LIVE ${session.livePhase.replaceAll("_", " ")}` : session.available ? "REPLAY READY" : "NOT DOWNLOADED"}</span></button>) : <p>No sessions are listed yet.</p>}</section>
      <section className="tv-session-preview" aria-label="Selected session">{browsed ? <><span>{browsed.year} · {browsed.meetingName}</span><h2>{browsed.sessionName}</h2><p>{browsed.circuit ?? browsed.location ?? "Circuit information unavailable"}</p><p>{dateLabel(browsed)}</p><div className="tv-session-actions">
        {browsed.liveAvailable && <button onClick={() => onWatch(browsed.sessionKey, "live")}>{browsed.sessionKey === selectedKey && viewingMode === "live" ? "RESUME LIVE" : "WATCH LIVE"}</button>}
        {browsed.available && <button onClick={() => onWatch(browsed.sessionKey, "replay")}>{browsed.sessionKey === selectedKey && viewingMode === "replay" ? "RESUME REPLAY" : "WATCH REPLAY"}</button>}
        {!browsed.available && catalog.downloadsEnabled && browsed.downloadable && (browsed.sessionKey !== selectedKey ? <button onClick={() => onSelect(browsed.sessionKey)}>SELECT REPLAY FOR DOWNLOAD</button> : <button disabled={downloadState === "downloading"} onClick={onDownload}>{downloadState === "downloading" ? "DOWNLOADING REPLAY…" : "DOWNLOAD REPLAY"}</button>)}
      </div>{!browsed.available && !browsed.liveAvailable && <p className="tv-library-note">{!browsed.downloadable ? "This session is not yet available to watch." : !catalog.downloadsEnabled ? "Replay downloads are disabled on this server." : "Download the recording, then choose Watch replay."}</p>}{browsed.sessionKey === selectedKey && downloadError && <p className="tv-library-notice" role="alert">{downloadError}</p>}</> : <p>Select a session to view its availability.</p>}</section></div>
    </>}
    <footer>Use the D-pad to move · OK to choose · Back returns to this list</footer>
  </div>;
}
