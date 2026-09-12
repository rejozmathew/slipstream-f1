import type { RaceState } from "./protocol";

// Published by Formula 1 on 2026-09-10. This is a reference image, not
// ordered geometry; it must never establish car-placement capability.
const MADRING_2026 = {
  imageUrl: "https://media.formula1.com/image/upload/c_lfill%2Cw_3392/q_auto/v1740000001/fom-website/2026/Spain%20%28Madrid%29/Madring%20Circuit%20Map.webp",
  sourceUrl: "https://www.formula1.com/en/latest/article/circuit-guide-everything-you-need-to-know-about-the-madring.NF7Mh3iag3w9GUPlihwJA",
  label: "Madring 2026 official circuit map",
};

export function circuitReference(session: RaceState["session"]) {
  return session.circuit?.trim().toLowerCase() === "madring"
    && session.started_at?.startsWith("2026-") ? MADRING_2026 : null;
}
