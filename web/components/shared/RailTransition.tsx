import { useLayoutEffect, useRef } from "react";

const severities: Record<string, number> = { GREEN: 1, YELLOW: 2, VSC_ENDING: 2, VSC: 3, SAFETY_CAR: 3, SC: 3, CHEQUERED: 3, RED: 4, RED_FLAG: 4 };
const severity = (status: string | null | undefined) => severities[status ?? ""] ?? 0;

/** The keyed overlay owns no facts or timers, so old transitions cannot restore old status. */
export function RailTransition({ status, generation = 0 }: { status: string | null | undefined; generation?: number }) {
  const effect = useRef<HTMLSpanElement>(null);
  const previous = useRef<{ status: string | null | undefined; generation: number } | null>(null);
  useLayoutEffect(() => {
    const last = previous.current;
    const element = effect.current;
    previous.current = { status, generation };
    if (!element) return;
    element.dataset.transition = !last || last.generation !== generation || !last.status || last.status === "UNKNOWN" || !status || status === "UNKNOWN" || last.status === status ? "none" : severity(status) >= 2 && severity(status) > severity(last.status) ? "escalate" : "fade";
  }, [status, generation]);
  return <span key={`${generation}:${status}`} ref={effect} className="rail-transition" data-status={status} aria-hidden="true" />;
}
