import type { CSSProperties } from "react";
import type { Driver } from "../../domain/protocol";
import { driverLifecycle } from "../../domain/lifecycle";
import "./towerMotion.css";

export function towerMotionRowProps(driver: Driver) {
  const lifecycle = driverLifecycle(driver);
  return {
    style: { "--tower-team": `#${driver.team_colour ?? "77808f"}` } as CSSProperties,
    "data-motion-state": lifecycle.inPit ? "IN_PIT" : lifecycle.status,
    "data-motion-compound": driver.compound ?? "UNKNOWN",
  };
}

/** Decorative layers preserve the table's actual columns and accessible facts. */
export function TowerRowEffects() {
  return <span className="tower-motion-effects" aria-hidden="true">
    <span className="tower-motion-wash" />
    <span className="tower-motion-delta" />
    <span className="tower-motion-chips" />
  </span>;
}
