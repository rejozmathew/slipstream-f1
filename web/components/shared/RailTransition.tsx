import { useLayoutEffect, useRef } from "react";

const severity = (status: string | null | undefined) => /RED/.test(status ?? "") ? 4 : /SAFETY_CAR|^SC$/.test(status ?? "") ? 3 : /VSC/.test(status ?? "") ? 2 : /YELLOW/.test(status ?? "") ? 1 : 0;

/** The keyed overlay owns no facts or timers, so old transitions cannot restore old status. */
export function RailTransition({ status, generation = 0 }: { status: string | null | undefined; generation?: number }) {
  const effect = useRef<HTMLSpanElement>(null);
  const previous = useRef<{ status: string | null | undefined; generation: number } | null>(null);
  useLayoutEffect(() => {
    const last = previous.current;
    const element = effect.current;
    previous.current = { status, generation };
    if (!element) return;
    element.dataset.transition = !last || last.generation !== generation || !last.status || last.status === "UNKNOWN" || !status || status === "UNKNOWN" || last.status === status ? "none" : severity(status) > severity(last.status) ? "escalate" : "fade";
  }, [status, generation]);
  return <span key={`${generation}:${status}`} ref={effect} className="rail-transition" aria-hidden="true" />;
}
