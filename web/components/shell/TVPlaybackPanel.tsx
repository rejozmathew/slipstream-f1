import { useState } from "react";
import { formatLiveDelay, parseLiveDelay } from "../../domain/liveDelay.mjs";
import type { RaceState, ReplayCommand, ViewingMode } from "../../domain/protocol";

/** The reference TV controls, using the same viewer commands as every other posture. */
export function TVPlaybackPanel({ session, mode, speed, playing, delay, requestedDelay = delay, syncOffset = 0, canCommand, onCommand, onSpeedChange, onSyncOffsetChange, onClose, hasReturnPoint, onReturn }: {
  session: RaceState["session"]; mode: ViewingMode; speed: number; playing: boolean;
  delay: number; requestedDelay?: number; syncOffset?: number;
  canCommand: (command: ReplayCommand) => boolean; onCommand: (command: ReplayCommand) => boolean;
  onSpeedChange?: (speed: number) => boolean | void; onSyncOffsetChange?: (seconds: number) => boolean | void;
  onClose: () => void; hasReturnPoint?: boolean; onReturn?: () => boolean | void;
}) {
  const live = mode === "live";
  const [custom, setCustom] = useState("");
  const [error, setError] = useState<string | null>(null);
  const selected = live ? requestedDelay : syncOffset;
  const command = (value: ReplayCommand) => canCommand(value) && onCommand(value);
  const setOffset = (seconds: number) => {
    const sent = live ? command({ type: "delay", seconds }) : onSyncOffsetChange?.(seconds);
    setError(sent === false ? "The timing connection is unavailable." : null);
  };
  const play = playing ? { type: "pause" as const } : { type: "play" as const, speed: live ? 1 : speed };
  const race = ["race", "sprint"].includes(session.session_kind);
  return <div className="tv-sync-content">
    <div className="tv-sync-summary"><span>{live ? "LIVE DELAY" : "REPLAY"}</span><strong>{live ? formatLiveDelay(delay) : race ? `LAP ${session.lap ?? "—"}/${session.total_laps ?? "—"}` : [session.qualifying_phase === "UNKNOWN" ? null : session.qualifying_phase, session.session_clock?.replace(/^00:/, "") ?? "—"].filter(Boolean).join(" ")}</strong><p>{session.local_time?.slice(11, 19) ?? "—"} local · {live ? "behind the live feed" : `${speed}× · sync offset ${formatLiveDelay(syncOffset)}`}</p></div>
    {!live && <div className="tv-sync-row"><span>SPEED</span>{[.5, 1, 2, 5, 10, 30, 60, 120].map(value => <button key={value} type="button" aria-pressed={speed === value} disabled={!canCommand({ type: "play", speed: value })} onClick={() => onSpeedChange?.(value)}>{value}×</button>)}</div>}
    <form className="tv-sync-row" onSubmit={event => { event.preventDefault(); const seconds = parseLiveDelay(custom); if (seconds == null) setError("Enter M:SS from 0:00 to 5:00."); else setOffset(seconds); }}>
      <span>{live ? "DELAY" : "SYNC OFFSET"}</span>{[0, 5, 10, 30, 60, 120, ...(live ? [300] : [])].map(value => <button key={value} type="button" aria-pressed={selected === value} disabled={!canCommand(live ? { type: "delay", seconds: value } : { type: "seek_relative", seconds: 0 })} onClick={() => setOffset(value)}>{value < 60 ? `${value}s` : `${value / 60}m`}</button>)}
      <input aria-label={live ? "Custom live delay M:SS" : "Replay sync offset M:SS"} placeholder="M:SS" maxLength={4} value={custom} onChange={event => setCustom(event.target.value)} /><button type="submit">APPLY</button>
    </form>
    <div className="tv-sync-row"><span>{live ? "ADJUST" : "POSITION"}</span><button disabled={!canCommand(live ? { type: "delay", seconds: Math.max(0, selected - 1) } : { type: "seek_relative", seconds: -30 })} onClick={() => live ? setOffset(Math.max(0, selected - 1)) : command({ type: "seek_relative", seconds: -30 })}>{live ? "−1 s" : "−30 S"}</button><button disabled={!canCommand(play)} onClick={() => command(play)}>{playing ? "❚❚ PAUSE" : "▶ PLAY"}</button><button disabled={!canCommand(live ? { type: "delay", seconds: Math.min(300, selected + 1) } : { type: "seek_relative", seconds: 30 })} onClick={() => live ? setOffset(Math.min(300, selected + 1)) : command({ type: "seek_relative", seconds: 30 })}>{live ? "+1 s" : "+30 S"}</button>{live && <button className="tv-sync-live" disabled={!canCommand({ type: "reset" })} onClick={() => command({ type: "reset" })}>GO LIVE</button>}{!live && hasReturnPoint && <button onClick={onReturn}>↩ RETURN</button>}<button onClick={onClose}>CLOSE</button></div>
    {error && <p className="tv-sync-error" role="alert">{error}</p>}
    {live && requestedDelay > delay + .5 && <p className="tv-sync-note">Asked {formatLiveDelay(requestedDelay)} · buffer holds {formatLiveDelay(delay)}</p>}
    <p className="tv-sync-note">{live ? "Match your TV broadcast. Pause holds this moment; the delay grows up to 5:00." : "Sync offset lines the replay up with a recorded broadcast. ←/→ move 30 s."}</p>
  </div>;
}
