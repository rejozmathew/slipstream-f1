import { useRef, useState } from "react";

import { formatLiveDelay, LIVE_DELAY_PRESETS, parseLiveDelay } from "../../domain/liveDelay.mjs";
import type { LiveProductPhase, ReplayCommand } from "../../domain/protocol";

type LiveControlsProps = {
  phase: LiveProductPhase;
  delaySeconds: number;
  requestedDelaySeconds?: number;
  isPlaying?: boolean;
  notice?: string | null;
  commandAvailable: boolean;
  onCommand: (command: ReplayCommand) => boolean;
};

export function LiveControls(props: LiveControlsProps) {
  return <ConfirmedLiveControls {...props} />;
}

function ConfirmedLiveControls({ phase, delaySeconds, requestedDelaySeconds = delaySeconds, isPlaying = true, notice, commandAvailable, onCommand }: LiveControlsProps) {
  const [customDelay, setCustomDelay] = useState(() => formatLiveDelay(delaySeconds));
  const [confirmedDelay, setConfirmedDelay] = useState(requestedDelaySeconds);
  const [editing, setEditing] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsButton = useRef<HTMLButtonElement>(null);
  const [error, setError] = useState<string | null>(null);
  if (confirmedDelay !== requestedDelaySeconds && !editing) {
    setConfirmedDelay(requestedDelaySeconds);
    setCustomDelay(formatLiveDelay(requestedDelaySeconds));
  }
  const selectDelay = (seconds: number) => {
    if (!commandAvailable) return;
    setError(onCommand({ type: "delay", seconds }) ? null : "Sync command could not be sent.");
    setCustomDelay(formatLiveDelay(seconds));
  };
  const resetLive = () => {
    if (!commandAvailable) return;
    const sent = onCommand({ type: "reset" });
    setError(sent ? null : "Sync command could not be sent.");
    if (sent) setCustomDelay("0:00");
  };
  return <footer className="live-controls" aria-label="Live sync controls" onKeyDownCapture={(event) => {
    if (event.key === "Escape" && settingsOpen) {
      event.preventDefault(); event.stopPropagation(); setSettingsOpen(false); settingsButton.current?.focus();
    }
  }}>
    <div className="live-controls-status"><span>{phase.replaceAll("_", " ")}</span><strong aria-live="polite">{delaySeconds === 0 ? "LIVE" : `DELAY ${formatLiveDelay(delaySeconds)}`}</strong></div>
    <button className="play-button" disabled={!commandAvailable} onClick={() => onCommand(isPlaying ? { type: "pause" } : { type: "play", speed: 1 })}>{isPlaying ? "PAUSE" : "RESUME"}</button>
    <button ref={settingsButton} className="transport-settings-toggle" aria-expanded={settingsOpen} aria-controls="live-delay-settings" onClick={() => setSettingsOpen((value) => !value)}>DELAY</button>
    <div id="live-delay-settings" className={`transport-settings${settingsOpen ? " is-open" : ""}`}>
    <div className="live-delay-options"><span>LIVE DELAY</span>{LIVE_DELAY_PRESETS.map((seconds) => <button key={seconds} className={delaySeconds === seconds ? "active" : ""} disabled={!commandAvailable} onClick={() => selectDelay(seconds)}>{seconds < 60 ? `${seconds}s` : `${seconds / 60}m`}</button>)}</div>
    <div className="live-delay-nudges"><button disabled={!commandAvailable || requestedDelaySeconds >= 300} onClick={() => selectDelay(Math.min(300, requestedDelaySeconds + 1))}>+1s delay</button><button disabled={!commandAvailable || requestedDelaySeconds <= 0} onClick={() => selectDelay(Math.max(0, requestedDelaySeconds - 1))}>−1s delay</button></div>
    <form className="live-custom-delay" onSubmit={(event) => {
      event.preventDefault();
      const seconds = parseLiveDelay(customDelay);
      if (seconds === null) { setError("Enter M:SS from 0:00 to 5:00."); return; }
      selectDelay(seconds);
    }}>
      <label><span>DELAY M:SS</span><input aria-label="Custom live delay M:SS" aria-invalid={Boolean(error)} aria-describedby={error ? "live-delay-error" : undefined} placeholder="0:00" maxLength={4} value={customDelay} disabled={!commandAvailable} onFocus={() => setEditing(true)} onBlur={() => setEditing(false)} onChange={(event) => { setCustomDelay(event.target.value); setError(null); }} /></label>
      <button type="submit" disabled={!commandAvailable}>APPLY</button>
    </form>
    </div>
    <button className="live-reset" disabled={!commandAvailable} onClick={resetLive}>GO LIVE</button>
    {requestedDelaySeconds > delaySeconds + 0.5 && <span className="live-delay-capacity">Asked {formatLiveDelay(requestedDelaySeconds)} · buffer holds {formatLiveDelay(delaySeconds)}</span>}
    {notice && <span className="live-limit-notice" role="status">{notice}</span>}
    {error && <span id="live-delay-error" className="live-delay-error" role="alert">{error}</span>}
    {!commandAvailable && <span className="live-command-unavailable">SYNC TRANSPORT UNAVAILABLE</span>}
  </footer>;
}
