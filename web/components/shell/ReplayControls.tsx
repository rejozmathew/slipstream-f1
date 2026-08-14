import { useMemo, useState } from "react";

import { formatDuration } from "../../domain/format";
import type { ReplayCommand, ReplayMetadata } from "../../domain/protocol";

type ReplayControlsProps = {
  metadata: ReplayMetadata | null;
  playhead: string | null;
  isPlaying: boolean;
  sequence: number;
  commandAvailable: boolean;
  onCommand: (command: ReplayCommand) => boolean;
};

export function ReplayControls({ metadata, playhead, isPlaying, sequence, commandAvailable, onCommand }: ReplayControlsProps) {
  const [speed, setSpeed] = useState(10);
  const [delaySeconds, setDelaySeconds] = useState(0);
  const elapsed = useMemo(() => {
    if (!metadata?.startTime || !playhead) return 0;
    return Math.max(0, (Date.parse(playhead) - Date.parse(metadata.startTime)) / 1000);
  }, [metadata?.startTime, playhead]);
  const duration = metadata?.durationSeconds ?? 0;
  const enabled = metadata?.available === true && commandAvailable;
  const seekTo = (seconds: number) => {
    if (!metadata?.startTime || !enabled) return;
    onCommand({ type: "seek", at: new Date(Date.parse(metadata.startTime) + seconds * 1000).toISOString() });
  };
  const changeSpeed = (nextSpeed: number) => {
    setSpeed(nextSpeed);
    if (isPlaying && commandAvailable) onCommand({ type: "play", speed: nextSpeed });
  };

  return (
    <section className="replay-controls" aria-label="Replay controls">
      <button className="transport-button" disabled={!enabled} onClick={() => onCommand({ type: "reset" })} title="Return to session start">|&lt;</button>
      <button className="transport-button" disabled={!enabled} onClick={() => onCommand({ type: "seek_relative", seconds: -30 })}>-30s</button>
      <button className="play-button" disabled={!enabled} onClick={() => onCommand(isPlaying ? { type: "pause" } : { type: "play", speed })}>{isPlaying ? "PAUSE" : "PLAY"}</button>
      <button className="transport-button" disabled={!enabled} onClick={() => onCommand({ type: "seek_relative", seconds: 30 })}>+30s</button>
      <div className="timeline">
        <input type="range" min={0} max={Math.max(duration, 1)} step={1} value={Math.min(elapsed, Math.max(duration, 1))} disabled={!enabled || !metadata?.startTime} onChange={(event) => seekTo(Number(event.target.value))} aria-label="Replay position" />
        <div><time>{formatDuration(elapsed)}</time><span>{metadata?.available && !commandAvailable ? "COMMAND TRANSPORT UNAVAILABLE" : `SEQ ${sequence.toLocaleString()}`}</span><time>{formatDuration(duration)}</time></div>
      </div>
      <label className="speed-select"><span>SPEED</span><select aria-label="Replay speed" value={speed} disabled={!enabled} onChange={(event) => changeSpeed(Number(event.target.value))}>
        {[0.5, 1, 2, 5, 10, 30, 60, 120].map((value) => <option value={value} key={value}>{value}x</option>)}
      </select></label>
      <div className="delay-control">
        <label><span>TV SYNC</span><input aria-label="Seconds behind session data" type="number" min={0} step={1} value={delaySeconds} disabled={!enabled} onChange={(event) => setDelaySeconds(Math.max(0, Number(event.target.value) || 0))} /></label>
        <span>SEC BEHIND</span>
        <button disabled={!enabled} onClick={() => onCommand({ type: "delay", seconds: delaySeconds })}>APPLY</button>
      </div>
    </section>
  );
}
