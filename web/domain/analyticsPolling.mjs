/**
 * @param {"live" | "replay"} viewingMode
 * @param {string | null} selectedSessionKey
 * @param {string | undefined} weekendStatus
 * @param {string | undefined} pirelliStatus
 */
export function shouldPollAnalytics(
  viewingMode,
  selectedSessionKey,
  weekendStatus,
  pirelliStatus,
) {
  return viewingMode === "replay"
    && Boolean(selectedSessionKey)
    && (weekendStatus === "preparing" || pirelliStatus === "FETCHING");
}
