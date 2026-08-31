const SESSION_PRIORITY = new Map([
  ["race", 1],
  ["sprint", 2],
  ["qualifying", 3],
  ["sprint_qualifying", 4],
  ["practice_3", 5],
  ["practice_2", 6],
  ["practice_1", 7],
]);

/**
 * @template {{sessionKey: string, sessionKind: string, dateStart: string}} T
 * @param {T[]} sessions
 * @param {string | null} currentSessionKey
 * @returns {T | null}
 */
export function preferredWeekendSession(sessions, currentSessionKey = null) {
  const current = sessions.find((session) => session.sessionKey === currentSessionKey);
  if (current) return current;
  return [...sessions].sort((left, right) => {
    const priority = (SESSION_PRIORITY.get(left.sessionKind) ?? 99)
      - (SESSION_PRIORITY.get(right.sessionKind) ?? 99);
    return priority || left.dateStart.localeCompare(right.dateStart);
  })[0] ?? null;
}
