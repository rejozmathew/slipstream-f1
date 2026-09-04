export const LIVE_DELAY_PRESETS = [5, 10, 30, 60, 120, 180, 300];

export function parseLiveDelay(value) {
  const match = String(value).trim().match(/^([0-5]):([0-5][0-9])$/);
  if (!match) return null;
  const seconds = Number(match[1]) * 60 + Number(match[2]);
  return seconds <= 300 ? seconds : null;
}

export function formatLiveDelay(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0 || seconds > 300) return "—";
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}
