import type { RaceState } from "../../domain/protocol";

/** Presentation only: the server authors both phase and cursor-correct clock. */
export function SessionProgress({ session }: { session: RaceState["session"] }) {
  const kind = session.session_kind;
  if (kind === "race" || kind === "sprint") return <><span>LAP</span><strong>{session.lap ?? "—"} / {session.total_laps ?? "—"}</strong></>;
  const qualifying = kind === "qualifying" || kind === "sprint_qualifying";
  if (qualifying || ["practice_1", "practice_2", "practice_3"].includes(kind)) {
    const label = qualifying && session.qualifying_phase !== "UNKNOWN" ? session.qualifying_phase : "REMAINING";
    return <><span className={qualifying ? "session-progress-phase" : undefined}>{label}</span><strong>{session.session_clock?.replace(/^00:/, "") ?? "—"}</strong></>;
  }
  return <><span>SESSION</span><strong>—</strong></>;
}
