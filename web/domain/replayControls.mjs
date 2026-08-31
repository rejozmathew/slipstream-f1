export function replayDisplayPosition(serverElapsed, scrubSeconds, pendingSeconds) {
  return scrubSeconds ?? pendingSeconds ?? serverElapsed;
}

export function reconciledPendingPosition(serverElapsed, pendingSeconds, tolerance = 1) {
  if (pendingSeconds == null) return null;
  return Math.abs(serverElapsed - pendingSeconds) <= tolerance ? null : pendingSeconds;
}

export function sessionClockLabel(startTime, elapsedSeconds, gmtOffset) {
  if (!startTime) return "—";
  const match = String(gmtOffset ?? "").match(/^([+-]?)(\d{2}):(\d{2})/);
  const direction = match?.[1] === "-" ? -1 : 1;
  const offsetSeconds = match
    ? direction * (Number(match[2]) * 3600 + Number(match[3]) * 60)
    : 0;
  const target = new Date(Date.parse(startTime) + (elapsedSeconds + offsetSeconds) * 1000);
  return Number.isNaN(target.valueOf()) ? "—" : target.toISOString().slice(11, 19);
}
