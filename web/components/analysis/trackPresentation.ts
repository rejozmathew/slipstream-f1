import type { Driver } from "../../domain/protocol";
import type { DisplayPoint, TrackGeometry } from "../../domain/trackGeometry";

export type TrackPosture = "desktop" | "phone" | "tv";
export type TrackPresentationContext = { navigationGeneration?: number; playing?: boolean; speed?: number; reducedMotion?: boolean; asOf?: string | null };
export type AxisItem = { key: string; x: number; priority: number; focus: boolean; label: string };
export type AxisPlacement = { show: boolean; count: number; lane: number; shift: number };
export const AXIS_SIZES = { tv: { font: 17, dot: 18, lane: 27, lanes: 4 }, desktop: { font: 11, dot: 12, lane: 17, lanes: 3 }, phone: { font: 10, dot: 10, lane: 15, lanes: 3 } };

/** Pack labels in screen pixels; merging markers does not merge their facts. */
export function packAxis(items: AxisItem[], posture: TrackPosture, width: number, scale = 1) {
  const authored = AXIS_SIZES[posture];
  const size = { ...authored, font: authored.font * scale, dot: authored.dot * scale };
  const groups: Array<{ x: number; members: AxisItem[] }> = [];
  for (const item of [...items].sort((a, b) => a.x - b.x)) {
    const group = groups.at(-1);
    if (group && item.x - group.x < size.dot * .75) group.members.push(item);
    else groups.push({ x: item.x, members: [item] });
  }
  const lanes: Array<Array<[number, number]>> = Array.from({ length: size.lanes }, () => []);
  const result = new Map<string, AxisPlacement>();
  const priority = (members: AxisItem[]) => Math.min(...members.map((item) => item.focus ? -1 : item.priority));
  for (const group of groups.sort((a, b) => priority(a.members) - priority(b.members))) {
    const representative = group.members.find((item) => item.focus) ?? [...group.members].sort((a, b) => a.priority - b.priority)[0];
    for (const member of group.members) result.set(member.key, { show: member === representative, count: member === representative ? group.members.length : 0, lane: -1, shift: 0 });
    const labelWidth = size.font * .7 * representative.label.length + size.font * .7 + (group.members.length > 1 ? size.font * 1.2 : 0);
    const left = representative.x - labelWidth / 2;
    const shift = Math.max(0, Math.min(width - labelWidth, left)) - left;
    const l = left + shift, r = l + labelWidth, pad = size.font * .4;
    const lane = lanes.findIndex((intervals) => intervals.every(([a, b]) => r + pad <= a || l - pad >= b));
    if (lane >= 0) { lanes[lane].push([l, r]); result.set(representative.key, { show: true, count: group.members.length, lane, shift }); }
  }
  return result;
}

export function focusWithNeighbours(drivers: Driver[], selected: string[]) {
  const focus = new Set(selected);
  if (selected.length !== 1) return focus;
  const ordered = [...drivers].filter((driver) => driver.position != null).sort((a, b) => a.position! - b.position!);
  const index = ordered.findIndex((driver) => driver.number === selected[0]);
  if (index >= 0) for (const neighbour of [ordered[index - 1], ordered[index + 1]]) if (neighbour) focus.add(neighbour.number);
  return focus;
}

export type MapCar = { driver: Driver; point: DisplayPoint; fraction: number | null; normal: DisplayPoint; focus: boolean; priority: number };
export type MapGroup = { point: DisplayPoint; representative: MapCar; members: MapCar[]; label: DisplayPoint | null };
/** Separate display symbols at a shared timing point; source progress is unchanged. */
export function mapMarkerOffsets(groups: MapGroup[], radius: number) {
  const offsets = new Map<string, DisplayPoint>();
  const occupied: DisplayPoint[] = [], step = radius * 2.4;
  const cars = groups.flatMap(group => group.members).sort((a, b) => a.driver.number.localeCompare(b.driver.number, undefined, { numeric: true }));
  for (const car of cars) {
    let placed = false;
    for (let ring = 0; ring <= cars.length && !placed; ring++) {
      const candidates: DisplayPoint[] = [];
      for (let row = -ring; row <= ring; row++) for (let column = -ring; column <= ring; column++) {
        if (Math.max(Math.abs(row), Math.abs(column)) === ring) candidates.push({ x: column * step, y: row * step });
      }
      candidates.sort((a, b) => Math.hypot(a.x, a.y) - Math.hypot(b.x, b.y));
      for (const offset of candidates) {
        const point = { x: car.point.x + offset.x, y: car.point.y + offset.y };
        if (point.x < radius || point.x > 1000 - radius || point.y < radius || point.y > 650 - radius
          || occupied.some(other => Math.hypot(point.x - other.x, point.y - other.y) < step - 1e-8)) continue;
        offsets.set(car.driver.number, offset); occupied.push(point); placed = true; break;
      }
    }
    if (!placed) offsets.set(car.driver.number, { x: 0, y: 0 });
  }
  return offsets;
}
export function trackNormal(geometry: TrackGeometry, fraction: number) {
  const before = geometry.pointAt(fraction - .0001), after = geometry.pointAt(fraction + .0001);
  const length = Math.hypot(after.x - before.x, after.y - before.y) || 1;
  return { x: -(after.y - before.y) / length, y: (after.x - before.x) / length };
}
export function packMapCars(cars: MapCar[], radius: number, font: number, labelCount: number): MapGroup[] {
  const groups: MapGroup[] = [];
  for (const car of cars) {
    const group = groups.find((candidate) => Math.hypot(candidate.point.x - car.point.x, candidate.point.y - car.point.y) < radius * 1.3);
    if (group) group.members.push(car);
    else groups.push({ point: car.point, representative: car, members: [car], label: null });
  }
  const priority = (group: MapGroup) => Math.min(...group.members.map((car) => car.focus ? -1 : car.priority));
  const boxes = groups.map((group) => ({ x0: group.point.x - radius * 1.15, x1: group.point.x + radius * (group.members.length > 1 ? 1.9 : 1.15), y0: group.point.y - radius * (group.members.length > 1 ? 1.9 : 1.15), y1: group.point.y + radius * 1.15 }));
  for (const group of [...groups].sort((a, b) => priority(a) - priority(b))) {
    group.representative = group.members.find((car) => car.focus) ?? group.members[0];
    group.point = group.representative.point;
    if (priority(group) >= labelCount) continue;
    const car = group.representative, code = car.driver.code ?? car.driver.number;
    const width = font * .68 * code.length + font * .3, height = font * 1.02;
    for (const [side, multiplier] of [[1, 1], [-1, 1], [1, 1.8], [-1, 1.8], [1, 2.6], [-1, 2.6]]) {
      const offset = (radius + font * .75) * multiplier;
      const x = group.point.x + car.normal.x * offset * side, y = group.point.y + car.normal.y * offset * side;
      const box = { x0: x - width / 2, x1: x + width / 2, y0: y - height / 2, y1: y + height / 2 };
      if (box.x0 < 0 || box.x1 > 1000 || box.y0 < 0 || box.y1 > 650 || boxes.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) continue;
      boxes.push(box); group.label = { x: x - group.point.x, y: y - group.point.y }; break;
    }
    if (!group.label && car.focus) {
      const offset = radius + font * .75;
      group.label = { x: Math.max(width / 2, Math.min(1000 - width / 2, group.point.x + car.normal.x * offset)) - group.point.x, y: Math.max(height / 2, Math.min(650 - height / 2, group.point.y + car.normal.y * offset)) - group.point.y };
    }
  }
  return groups.sort((a, b) => Number(a.representative.focus || a.representative.priority === 0) - Number(b.representative.focus || b.representative.priority === 0));
}

/** Only interpolate between two received progress values, never extrapolate. */
export function observedProgressDelta(from: number, to: number, oldLap?: number | null, newLap?: number | null) {
  if (!Number.isFinite(from) || !Number.isFinite(to) || (oldLap != null && newLap != null && newLap < oldLap)) return null;
  let delta = to - from;
  if (delta < 0 && from > .75 && to < .25) delta += 1;
  return delta >= 0 && delta <= .25 + 1e-9 ? delta : null;
}

export function sourceLeaderGap(driver: Driver): number | null {
  if (driver.position === 1) return 0;
  if (driver.availability?.gap_to_leader === "unavailable") return null;
  const raw = driver.gap_to_leader?.trim();
  return raw && /^\+?\d+(?:\.\d+)?$/.test(raw) && Number.isFinite(Number(raw)) ? Number(raw) : null;
}
export function sourceLapGap(driver: Driver) {
  return driver.availability?.gap_to_leader !== "unavailable" && /^\+?\d+\s*LAPS?$/i.test(driver.gap_to_leader?.trim() ?? "");
}
export function ribbonScale(maxGap: number, previous?: number) {
  const wanted = [3, 5, 10, 20, 30, 45, 60, 90, 120, 180].find((value) => value >= maxGap * 1.05) ?? Math.ceil(maxGap * 1.05 / 60) * 60;
  return previous == null || wanted > previous || (wanted < previous && maxGap * 1.05 < wanted * .85) ? wanted : previous;
}
