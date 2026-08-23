import { useState } from "react";

import type { LiveProductPhase, ReplayCommand } from "../../domain/protocol";

const DELAYS = [0, 5, 10, 15, 30] as const;

export function LiveControls({ phase, commandAvailable, onCommand }: {
  phase: LiveProductPhase;
  commandAvailable: boolean;
  onCommand: (command: ReplayCommand) => boolean;
}) {
  const [delaySeconds, setDelaySeconds] = useState(0);
  const selectDelay = (seconds: number) => {
    if (!commandAvailable) return;
    if (onCommand({ type: "delay", seconds })) setDelaySeconds(seconds);
  };
  const resetLive = () => {
    if (!commandAvailable) return;
    if (onCommand({ type: "reset" })) setDelaySeconds(0);
  };
  return <footer className="live-controls" aria-label="Live sync controls">
    <div className="live-controls-status"><span>LIVE PHASE</span><strong>{phase.replaceAll("_", " ")}</strong></div>
    <div className="live-delay-options"><span>LIVE DELAY</span>{DELAYS.map((seconds) => <button key={seconds} className={delaySeconds === seconds ? "active" : ""} disabled={!commandAvailable} onClick={() => selectDelay(seconds)}>{seconds}s</button>)}</div>
    <button className="live-reset" disabled={!commandAvailable || delaySeconds === 0} onClick={resetLive}>RESET / LIVE</button>
    {!commandAvailable && <span className="live-command-unavailable">SYNC TRANSPORT UNAVAILABLE</span>}
  </footer>;
}
