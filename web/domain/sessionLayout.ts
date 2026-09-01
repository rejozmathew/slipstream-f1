import type { LayoutFamily, SessionKind } from "./protocol";

export type SessionLayout = LayoutFamily;

export type SessionClassification = {
  kind: SessionKind;
  layoutFamily: LayoutFamily;
};

export function classifySession(
  sessionType: string | null | undefined,
  sessionName: string | null | undefined,
  explicitKind?: SessionKind | null,
  explicitLayout?: LayoutFamily | null,
): SessionClassification {
  if (
    explicitKind && explicitKind !== "unknown"
    && explicitLayout && explicitLayout !== "unsupported"
  ) return { kind: explicitKind, layoutFamily: explicitLayout };
  const value = `${sessionType ?? ""} ${sessionName ?? ""}`.trim().toLowerCase();
  if (/sprint qualifying|sprint shootout/.test(value)) return { kind: "sprint_qualifying", layoutFamily: "qualifying" };
  if (/qualifying|shootout/.test(value)) return { kind: "qualifying", layoutFamily: "qualifying" };
  if (/sprint/.test(value)) return { kind: "sprint", layoutFamily: "race" };
  if (/practice|testing/.test(value)) {
    const practice = value.match(/(?:practice\s*|fp)([123])/i)?.[1];
    return { kind: practice ? `practice_${practice}` as SessionKind : "unknown", layoutFamily: "practice" };
  }
  if (/race|grand prix/.test(value)) return { kind: "race", layoutFamily: "race" };
  return { kind: "unknown", layoutFamily: "unsupported" };
}

export function classifySessionLayout(
  sessionType: string | null | undefined,
  sessionName: string | null | undefined,
): SessionLayout {
  return classifySession(sessionType, sessionName).layoutFamily;
}
