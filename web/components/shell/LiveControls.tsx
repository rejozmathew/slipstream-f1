import { useState } from "react";

import { formatLiveDelay, LIVE_DELAY_PRESETS, parseLiveDelay } from "../../domain/liveDelay.mjs";
import type { LiveProductPhase, ReplayCommand } from "../../domain/protocol";

export function LiveControls({ phase, delaySeconds, commandAvailable, onCommand }: {
  phase: LiveProductPhase;
  delaySeconds: number;
  commandAvailable: boolean;
  onCommand: (command: ReplayCommand) => boolean;
}) {
  const [customDelay, setCustomDelay] = useState("");
  const [error, setError] = useState<string | null>(null);
  const selectDelay = (seconds: number) => {
    if (!commandAvailable) return;
    setError(onCommand({ type: "delay", seconds }) ? null : "Sync command could not be sent.");
  };
  const resetLive = () => {
    if (!commandAvailable) return;
    setError(onCommand({ type: "reset" }) ? null : "Sync command could not be sent.");
  };
  return <footer className="live-controls" aria-label="Live sync controls">
    <div className="live-controls-status"><span>{phase.replaceAll("_", " ")}</span><strong aria-live="polite">{delaySeconds === 0 ? "LIVE" : `DELAY ${formatLiveDelay(delaySeconds)}`}</strong></div>
    <div className="live-delay-options"><span>LIVE DELAY</span>{LIVE_DELAY_PRESETS.map((seconds) => <button key={seconds} className={delaySeconds === seconds ? "active" : ""} disabled={!commandAvailable} onClick={() => selectDelay(seconds)}>{seconds < 60 ? `${seconds}s` : `${seconds / 60}m`}</button>)}</div>
    <form className="live-custom-delay" onSubmit={(event) => {
      event.preventDefault();
      const seconds = parseLiveDelay(customDelay);
      if (seconds === null) { setError("Enter M:SS from 0:00 to 5:00."); return; }
      selectDelay(seconds);
    }}>
      <label><span>DELAY M:SS</span><input aria-label="Custom live delay M:SS" aria-invalid={Boolean(error)} aria-describedby={error ? "live-delay-error" : undefined} placeholder="2:17" maxLength={4} value={customDelay} disabled={!commandAvailable} onChange={(event) => { setCustomDelay(event.target.value); setError(null); }} /></label>
      <button type="submit" disabled={!commandAvailable}>APPLY</button>
    </form>
    <button className="live-reset" disabled={!commandAvailable} onClick={resetLive}>GO LIVE</button>
    {error && <span id="live-delay-error" className="live-delay-error" role="alert">{error}</span>}
    {!commandAvailable && <span className="live-command-unavailable">SYNC TRANSPORT UNAVAILABLE</span>}
  </footer>;
}
