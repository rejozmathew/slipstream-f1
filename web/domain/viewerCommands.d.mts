import type { ReplayCommand, ViewingMode } from "./protocol";
export function canViewerCommand(mode: ViewingMode, ready: boolean, replayAvailable: boolean, command: ReplayCommand | ReplayCommand["type"]): boolean;
export function isNavigationCommand(command: ReplayCommand): boolean;
