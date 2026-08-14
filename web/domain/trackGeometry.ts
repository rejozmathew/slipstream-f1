export type DisplayPoint = { x: number; y: number };
export type TrackGeometry = {
  points: DisplayPoint[];
  polyline: string;
  pointAt: (fraction: number) => DisplayPoint;
  project: (x: number, y: number) => DisplayPoint;
};

export function buildTrackGeometry(
  sourcePath: Array<[number, number]> | undefined,
  rotation = 0,
): TrackGeometry | null {
  if (!sourcePath || sourcePath.length < 3) return null;
  const center = sourcePath.reduce(
    (value, point) => ({ x: value.x + point[0] / sourcePath.length, y: value.y + point[1] / sourcePath.length }),
    { x: 0, y: 0 },
  );
  const angle = (rotation * Math.PI) / 180;
  const rotated = sourcePath.map(([x, y]) => {
    const dx = x - center.x;
    const dy = y - center.y;
    return { x: dx * Math.cos(angle) - dy * Math.sin(angle), y: dx * Math.sin(angle) + dy * Math.cos(angle) };
  });
  const minX = Math.min(...rotated.map((point) => point.x));
  const maxX = Math.max(...rotated.map((point) => point.x));
  const minY = Math.min(...rotated.map((point) => point.y));
  const maxY = Math.max(...rotated.map((point) => point.y));
  const width = 1000;
  const height = 650;
  const padding = 58;
  const scale = Math.min((width - padding * 2) / Math.max(maxX - minX, 1), (height - padding * 2) / Math.max(maxY - minY, 1));
  const xOffset = (width - (maxX - minX) * scale) / 2;
  const yOffset = (height - (maxY - minY) * scale) / 2;
  const points = rotated.map((point) => ({ x: xOffset + (point.x - minX) * scale, y: yOffset + (maxY - point.y) * scale }));
  const closed = [...points, points[0]];
  const distances = [0];
  for (let index = 1; index < closed.length; index += 1) {
    distances.push(distances[index - 1] + Math.hypot(closed[index].x - closed[index - 1].x, closed[index].y - closed[index - 1].y));
  }
  const totalDistance = distances[distances.length - 1];
  return {
    points,
    polyline: closed.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" "),
    pointAt(fraction) {
      const target = (((fraction % 1) + 1) % 1) * totalDistance;
      let index = distances.findIndex((distance) => distance >= target);
      if (index <= 0) index = 1;
      const start = closed[index - 1];
      const end = closed[index];
      const length = distances[index] - distances[index - 1];
      const mix = length ? (target - distances[index - 1]) / length : 0;
      return { x: start.x + (end.x - start.x) * mix, y: start.y + (end.y - start.y) * mix };
    },
    project(x, y) {
      const dx = x - center.x;
      const dy = y - center.y;
      const rotatedX = dx * Math.cos(angle) - dy * Math.sin(angle);
      const rotatedY = dx * Math.sin(angle) + dy * Math.cos(angle);
      return { x: xOffset + (rotatedX - minX) * scale, y: yOffset + (maxY - rotatedY) * scale };
    },
  };
}