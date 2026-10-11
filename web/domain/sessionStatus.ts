import type { RaceState } from "./protocol";

export function sessionStatusLabel(session: RaceState["session"], phase = session.qualifying_phase): string | null {
  const status = session.display_status ?? session.track_status;
  if (!status || status === "UNKNOWN") return null;
  if (status === "CHEQUERED" && session.layout_family === "qualifying" && /^(S?Q)[123]$/.test(phase ?? "")) {
    return `${phase} ENDED`;
  }
  return status.replaceAll("_", " ");
}
