import { useEffect, useState } from "react";
import type { MotionPreference } from "../domain/appearance";

export function useReducedMotion(preference: MotionPreference = "system") {
  const [systemReduced, setSystemReduced] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const changed = () => setSystemReduced(query.matches);
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, []);
  return preference === "reduced" || (preference === "system" && systemReduced);
}
