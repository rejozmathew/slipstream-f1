export function isCriticalTrackStatus(value) {
  return Boolean(value && /yellow|safety|\bsc\b|vsc|red/i.test(value));
}

export function nextAuthoredState(states, current) {
  if (states.length === 0) return null;
  const index = states.indexOf(current);
  return states[(Math.max(0, index) + 1) % states.length];
}
