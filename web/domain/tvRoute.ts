/** Web entry points usable by a TV browser or a thin TV wrapper. */
export function isStandaloneTVRoute(pathname: string, search: string): boolean {
  return new URLSearchParams(search).get("app") === "1" || /^\/tv(?:\/|$)/.test(pathname) || pathname === "/tv.html";
}
