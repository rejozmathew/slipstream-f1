/** Presentation-only widths. Sporting values remain authored by the server. */
export function fitTowerColumns(headers: string[], available: number, showAll = false, scale = 1) {
  const widths = headers.map((header) => header.startsWith("DRIVER") ? 140 : header === "P" ? 28 : header === "TYRE" ? 38 : ["PIT", "AGE", "STOPS", "STINT"].includes(header) ? 36 : header === "TYRE STRATEGY" ? 94 : header === "STATUS" || header === "Q STATUS" ? 86 : header.startsWith("S") && header.length === 2 ? 62 : 78).map((width) => width * scale);
  const priorities = ["S3", "S2", "S1", "LAST STOP", "AGE", "STINT", "STATUS", "PIT", "STOPS", "BEST", "LAST", "Q1", "SQ1", "Q2", "SQ2", "INT", "TYRE STRATEGY"];
  const hidden: number[] = [];
  let total = widths.reduce((sum, width) => sum + width, 0);
  if (available > 0 && !showAll) for (const header of priorities) {
    if (total <= available) break;
    const index = headers.indexOf(header);
    if (index >= 0) { hidden.push(index); total -= widths[index]; }
  }
  return { hidden, minimumWidth: total, template: widths.flatMap((width, index) => hidden.includes(index) ? [] : [headers[index].startsWith("DRIVER") ? `minmax(${140 * scale}px, 1fr)` : `${width}px`]).join(" ") };
}

/** TV fills its measured viewport; regular tables retain comfortable scrollable rows. */
export function fittedTowerRowHeight(available: number, header: number, count: number, tv = false) {
  if (available <= 0 || count <= 0) return 32;
  const fitted = Math.floor((available - header) / count * 100) / 100;
  return tv ? Math.max(20, fitted) : Math.max(28, Math.min(38, fitted));
}
