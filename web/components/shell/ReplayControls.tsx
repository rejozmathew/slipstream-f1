import { useEffect, useMemo, useState } from "react";

import { formatDuration } from "../../domain/format";
import { reconciledPendingPosition, replayDisplayPosition, replayKeyboardPosition, sessionClockLabel } from "../../domain/replayControls.mjs";
import type { ReplayCommand, ReplayMetadata } from "../../domain/protocol";

type ReplayControlsProps = {
  metadata: ReplayMetadata | null;
  playhead: string | null;
  gmtOffset: string | null;
  isPlaying: boolean;
  commandAvailable: boolean;
  onCommand: (command: ReplayCommand) => boolean;
};

export function ReplayControls({ metadata, playhead, gmtOffset, isPlaying, commandAvailable, onCommand }: ReplayControlsProps) {
  const [speed, setSpeed] = useState(10);
  const [delaySeconds, setDelaySeconds] = useState(0);
  const [scrubSeconds, setScrubSeconds] = useState<number | null>(null);
  const [pendingSeconds, setPendingSeconds] = useState<number | null>(null);
  const serverElapsed = useMemo(() => {
    if (!metadata?.startTime || !playhead) return 0;
    return Math.max(0, (Date.parse(playhead) - Date.parse(metadata.startTime)) / 1000);
  }, [metadata?.startTime, playhead]);
  const duration = metadata?.durationSeconds ?? 0;
  const enabled = metadata?.available === true && commandAvailable;
  const displayedSeconds = Math.min(
    replayDisplayPosition(serverElapsed, scrubSeconds, pendingSeconds),
    Math.max(duration, 1),
  );
  useEffect(() => {
    const reconciliation = window.setTimeout(() => {
      setPendingSeconds((current) => reconciledPendingPosition(serverElapsed, current));
    }, 0);
    return () => window.clearTimeout(reconciliation);
  }, [serverElapsed]);
  const commitSeek = (seconds: number) => {
    if (!metadata?.startTime || !enabled) return;
    setScrubSeconds(null);
    setPendingSeconds(seconds);
    if (!onCommand({ type: "seek", at: new Date(Date.parse(metadata.startTime) + seconds * 1000).toISOString() })) {
      setPendingSeconds(null);
    }
  };
  const changeSpeed = (nextSpeed: number) => {
    setSpeed(nextSpeed);
    if (isPlaying && commandAvailable) onCommand({ type: "play", speed: nextSpeed });
  };

  return (
    <section className="replay-controls" aria-label="Replay controls">
      <div className="transport-controls">
        <button className="transport-button" disabled={!enabled} onClick={() => onCommand({ type: "reset" })} title="Return to session start">|&lt;</button>
        <button className="transport-button" disabled={!enabled} onClick={() => onCommand({ type: "seek_relative", seconds: -30 })}>-30s</button>
        <button className="play-button" disabled={!enabled} onClick={() => onCommand(isPlaying ? { type: "pause" } : { type: "play", speed })}>{isPlaying ? "PAUSE" : "PLAY"}</button>
        <button className="transport-button" disabled={!enabled} onClick={() => onCommand({ type: "seek_relative", seconds: 30 })}>+30s</button>
      </div>
      <div className="timeline">
        <input
          type="range"
          min={0}
          max={Math.max(duration, 1)}
          step={1}
          value={displayedSeconds}
          disabled={!enabled || !metadata?.startTime}
          onPointerDown={() => setScrubSeconds(displayedSeconds)}
          onInput={(event) => setScrubSeconds(Number(event.currentTarget.value))}
          onPointerUp={(event) => commitSeek(Number(event.currentTarget.value))}
          onPointerCancel={() => setScrubSeconds(null)}
          onKeyDown={(event) => {
            const next = replayKeyboardPosition(event.key, displayedSeconds, duration);
            if (next != null) {
              event.preventDefault();
              commitSeek(next);
            }
          }}
          onBlur={(event) => {
            if (scrubSeconds != null) commitSeek(Number(event.currentTarget.value));
          }}
          aria-label="Replay position"
          aria-valuetext={`Elapsed ${formatDuration(displayedSeconds)}, session ${sessionClockLabel(metadata?.startTime ?? null, displayedSeconds, gmtOffset)}`}
        />
        <div className="timeline-meta">
          <time>ELAPSED {formatDuration(displayedSeconds)}</time>
          <span>{metadata?.available && !commandAvailable ? "COMMAND TRANSPORT UNAVAILABLE" : `SESSION ${sessionClockLabel(metadata?.startTime ?? null, displayedSeconds, gmtOffset)}`}</span>
          <time>TOTAL {formatDuration(duration)}</time>
        </div>
      </div>
      <label className="speed-select"><span>SPEED</span><select aria-label="Replay speed" value={speed} disabled={!enabled} onChange={(event) => changeSpeed(Number(event.target.value))}>
        {[0.5, 1, 2, 5, 10, 30, 60, 120].map((value) => <option value={value} key={value}>{value}x</option>)}
      </select></label>
      <div className="delay-control">
        <label><span>SYNC DELAY</span><input aria-label="Seconds behind session data" type="number" min={0} step={1} value={delaySeconds} disabled={!enabled} onChange={(event) => setDelaySeconds(Math.max(0, Number(event.target.value) || 0))} /></label>
        <span>SEC</span>
        <button disabled={!enabled} onClick={() => onCommand({ type: "delay", seconds: delaySeconds })}>APPLY</button>
      </div>
    </section>
  );
}
