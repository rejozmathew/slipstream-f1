export type SessionLayout = "race" | "qualifying" | "practice" | "unsupported";

export function classifySessionLayout(
  sessionType: string | null | undefined,
  sessionName: string | null | undefined,
): SessionLayout {
  const value = `${sessionType ?? ""} ${sessionName ?? ""}`.trim().toLowerCase();
  if (/qualifying|shootout/.test(value)) return "qualifying";
  if (/practice|testing/.test(value)) return "practice";
  if (/race|sprint/.test(value)) return "race";
  return "unsupported";
}