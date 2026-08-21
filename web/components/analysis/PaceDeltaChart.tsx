import type { CSSProperties } from "react";

import type { PaceSample } from "../../domain/protocol";

function fallbackScale(samples: PaceSample[]) {
  // Only reached when the server has not published a scale (legacy snapshots).
  const values = samples
    .filter((sample) => sample.quality === "representative" && sample.delta != null)
    .map((sample) => Math.abs(sample.delta as number))
    .sort((a, b) => a - b);
  if (values.length === 0) return 0.25;
  const middle = values[Math.floor(values.length / 2)];
  const deviations = values.map((value) => Math.abs(value - middle)).sort((a, b) => a - b);
  const mad = deviations[Math.floor(deviations.length / 2)];
  const retained = values.filter((value) => value <= middle + Math.max(0.25, mad * 3));
  return Math.max(0.25, retained.at(-1) ?? middle);
}

function formatDelta(value: number | null) {
  if (value == null) return "delta unavailable";
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}s`;
}

export function PaceDeltaChart({ samples, compact = false, serverScale }: { samples: PaceSample[]; compact?: boolean; serverScale?: number | null }) {
  if (samples.length === 0) return <div className="panel-empty">PACE EVIDENCE · UNKNOWN AT THIS REPLAY TIME</div>;
  // v2.1 §20: the y-axis scale is SERVER-computed (deterministic, cursor-
  // scoped). The client renders it verbatim; the local fallback only covers
  // snapshots that predate the server field.
  const scale = typeof serverScale === "number" && Number.isFinite(serverScale) && serverScale > 0 ? serverScale : fallbackScale(samples);
  return <div className={`pace-delta-chart${compact ? " pace-delta-chart-compact" : ""}`} role="img" aria-label="Signed pace delta by lap; faster laps above zero and slower laps below zero">
    <div className="pace-legend"><span>FASTER ↑</span><b>0 = STINT BASELINE</b><span>SLOWER ↓</span></div>
    <div className="pace-plot"><div className="pace-zero" />
      <div className="pace-samples">{samples.map((sample) => {
        const rawMagnitude = sample.delta == null ? 0 : Math.abs(sample.delta) / scale;
        const magnitude = sample.quality === "representative" ? Math.min(1, rawMagnitude) : Math.min(.82, rawMagnitude || .16);
        // v2.1 §18: four-way direction. A null delta is "unknown" (centered,
        // hatched), NOT "slower" — the old ternary classified missing data as
        // a slow lap. delta<0 faster, >0 slower, ==0 neutral.
        const direction = sample.delta == null ? "unknown" : sample.delta < 0 ? "faster" : sample.delta > 0 ? "slower" : "neutral";
        const style = { "--pace-magnitude": `${Math.max(8, magnitude * 45)}%` } as CSSProperties;
        const explanation = `Lap ${sample.lap} · ${formatDelta(sample.delta)} · ${sample.compound ?? "compound unavailable"} · age ${sample.tyreAge ?? "—"} · ${sample.quality}${sample.contaminationReasons.length ? ` · ${sample.contaminationReasons.join(", ")}` : ""}`;
        return <div className={`pace-sample pace-${direction} quality-${sample.quality} compound-bar-${(sample.compound ?? "unknown").toLowerCase()}`} key={`${sample.lap}-${sample.stintNumber}`} aria-label={explanation} style={style}>
          <i className="pace-mark" /><span>{sample.lap}</span>
        </div>;
      })}</div>
    </div>
  </div>;
}
