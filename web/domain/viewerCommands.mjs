/** One transport capability check, shared by every presentation/input path. */
export function canViewerCommand(mode, ready, replayAvailable, command) {
  if (!ready) return false;
  const type = typeof command === "string" ? command : command.type;
  const allowed = mode === "live"
    ? ["snapshot", "pause", "play", "delay", "reset"]
    : ["snapshot", "pause", "play", "delay", "reset", "seek", "seek_relative", "step"];
  if (!allowed.includes(type) || (mode === "replay" && !replayAvailable && type !== "snapshot")) return false;
  if (typeof command === "string") return true;
  if (type === "play") return Number.isFinite(command.speed) && (mode === "live" ? command.speed === 1 : command.speed >= 0.5 && command.speed <= 120);
  if (type === "delay") return Number.isFinite(command.seconds) && command.seconds >= 0 && (mode !== "live" || command.seconds <= 300);
  if (type === "seek_relative") return Number.isFinite(command.seconds);
  if (type === "seek") return "at" in command ? Number.isFinite(Date.parse(command.at)) : Number.isInteger(command.seq) && command.seq >= 0 && (command.playhead == null || Number.isFinite(Date.parse(command.playhead)));
  return true;
}

export function isNavigationCommand(command) {
  return ["seek", "seek_relative", "reset", "delay", "step"].includes(command.type);
}
