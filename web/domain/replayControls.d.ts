export function replayDisplayPosition(
  serverElapsed: number,
  scrubSeconds: number | null,
  pendingSeconds: number | null,
): number;

export function reconciledPendingPosition(
  serverElapsed: number,
  pendingSeconds: number | null,
  tolerance?: number,
): number | null;

export function sessionClockLabel(
  startTime: string | null,
  elapsedSeconds: number,
  gmtOffset: string | null,
): string;
