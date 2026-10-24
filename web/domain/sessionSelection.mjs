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


const dateValue = (value) => {
  const stamp = Date.parse(value);
  return Number.isFinite(stamp) ? stamp : Infinity;
};
const compareDates = (left, right) => dateValue(left) - dateValue(right) || 0;
const validRound = (value) => Number.isInteger(value) && value > 0;

export function catalogMeetingLabel(session) {
  if (session.isCancelled) return `${session.meetingName} · CANCELLED`;
  return validRound(session.roundNumber)
    ? `R${String(session.roundNumber).padStart(2, "0")} · ${session.meetingName}`
    : session.meetingName;
}

/** Keep each weekend together, independent of catalog arrival/download order. */
export function orderedSeasonWeekends(sessions, year) {
  const byMeeting = new Map();
  for (const session of sessions) {
    if (session.year !== year) continue;
    const meeting = byMeeting.get(session.meetingKey) ?? [];
    meeting.push(session);
    byMeeting.set(session.meetingKey, meeting);
  }
  const weekends = [...byMeeting.values()].map((items) => {
    const ordered = [...items].sort((left, right) => compareDates(left.dateStart, right.dateStart)
      || left.sessionKey.localeCompare(right.sessionKey, undefined, { numeric: true }));
    const race = ordered.find((item) => item.sessionKind === "race");
    const cancelled = race?.isCancelled === true || ordered.every((item) => item.isCancelled === true);
    const testing = !race && /test/i.test(ordered[0].meetingName);
    const rounds = [...new Set(ordered.map((item) => item.roundNumber).filter(validRound))];
    const weekend = { ...ordered[0], sessions: ordered, isCancelled: cancelled,
      roundNumber: !cancelled && rounds.length === 1 ? rounds[0] : null,
      group: cancelled ? "cancelled" : testing ? "testing" : "races" };
    return { ...weekend, label: catalogMeetingLabel(weekend) };
  });
  const numbered = weekends.filter((item) => item.group === "races").every((item) => validRound(item.roundNumber));
  const rank = { races: 0, cancelled: 1, testing: 2 };
  return weekends.sort((left, right) => rank[left.group] - rank[right.group]
    || (numbered && left.group === "races" ? left.roundNumber - right.roundNumber : 0)
    || compareDates(left.dateStart, right.dateStart)
    || left.meetingName.localeCompare(right.meetingName)
    || left.meetingKey.localeCompare(right.meetingKey, undefined, { numeric: true }));
}
