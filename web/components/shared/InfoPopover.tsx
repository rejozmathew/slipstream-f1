import type { ReactNode } from "react";

export function InfoPopover({ meaning, why, children }: { meaning: ReactNode; why: ReactNode; children?: ReactNode }) {
  return <details className="info-popover">
    <summary aria-label="Show explanation">ⓘ</summary>
    <div className="info-popover-content" role="dialog" aria-label="Metric explanation">
      <section><span>WHAT IT MEANS</span><p>{meaning}</p></section>
      <section><span>WHY THIS VALUE IS SHOWN NOW</span><p>{why}</p></section>
      {children}
    </div>
  </details>;
}
