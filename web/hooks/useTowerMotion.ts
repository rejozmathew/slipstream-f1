import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";
import type { StorySnapshot } from "../domain/protocol";
import { freshRowCues, rowMotionTiming } from "../domain/towerMotion";

/** Movement is neutral until current server story evidence establishes its cause. */
export function useTowerMotion(container: RefObject<HTMLDivElement | null>, revision: unknown, story?: StorySnapshot) {
  const positions = useRef(new Map<string, number>());
  const previous = useRef<{ sequence: number; generation?: string; session?: string; recording?: string; hasStory: boolean } | null>(null);
  const animations = useRef<Animation[]>([]);
  const timers = useRef(new Map<HTMLElement, ReturnType<typeof setTimeout>>());
  const clearCue = useCallback((row: HTMLElement) => {
    delete row.dataset.motionCause; delete row.dataset.motionLabel;
    row.querySelectorAll<HTMLElement>("[data-motion-label]").forEach((label) => delete label.dataset.motionLabel);
    const timer = timers.current.get(row); if (timer) clearTimeout(timer); timers.current.delete(row);
  }, []);
  const stop = useCallback((clear: boolean) => {
    animations.current.forEach((animation) => animation.cancel()); animations.current = [];
    if (clear) [...timers.current.keys()].forEach(clearCue);
  }, [clearCue]);
  useLayoutEffect(() => {
    const table = container.current;
    const shell = table?.closest<HTMLElement>(".app-shell");
    animations.current = animations.current.filter((animation) => animation.playState !== "finished");
    const last = previous.current;
    const current = { sequence: story?.sequence ?? 0, generation: shell?.dataset.navigationGeneration, session: shell?.dataset.sessionKey, recording: shell?.dataset.recordingVersion, hasStory: Boolean(story) };
    previous.current = current;
    const jump = Boolean(last && (last.generation !== current.generation || last.session !== current.session || last.recording !== current.recording || current.sequence < last.sequence));
    const reduced = shell?.dataset.reducedMotion === "true";
    const speed = Number(shell?.dataset.playbackSpeed ?? 1);
    if (!table || !table.getBoundingClientRect().width) { stop(true); positions.current.clear(); return; }
    const rows = [...table.querySelectorAll<HTMLElement>("[data-driver-number]")];
    const nextPositions = new Map(rows.map((row) => [row.dataset.driverNumber!, row.offsetTop]));
    const posture = table.closest(".tv-redesign") ? "tv" : table.closest(".phone-timing") ? "phone" : "desktop";
    const cues = last?.hasStory && !jump && shell?.dataset.viewerPlaying !== "false" ? freshRowCues(story, last.sequence, shell?.dataset.trackStatus, speed) : new Map();
    if (jump || speed >= 30) stop(true);
    else if (reduced || rows.some((row) => positions.current.get(row.dataset.driverNumber!) !== row.offsetTop)) stop(false);
    if (jump && !reduced && speed < 30 && typeof table.animate === "function") animations.current.push(table.animate([{ opacity: .5 }, { opacity: 1 }], { duration: 350, easing: "ease-out" }));
    if (!jump) rows.forEach((row) => {
      const cue = cues.get(row.dataset.driverNumber!);
      if (cue) {
        clearCue(row);
        row.dataset.motionCause = cue.cause; row.dataset.motionLabel = cue.label;
        row.querySelectorAll<HTMLElement>(".driver-cell em, .phone-identity small").forEach((label) => { label.dataset.motionLabel = cue.label; });
        const duration = speed >= 5 ? 1400 : posture === "tv" ? 3300 : 2500;
        const timer = setTimeout(() => { if (timers.current.get(row) === timer) clearCue(row); }, duration);
        timers.current.set(row, timer);
        if (!reduced && typeof row.animate === "function") animations.current.push(row.animate([{ boxShadow: "inset 0 0 0 2px var(--motion-cause-color)", backgroundColor: "color-mix(in srgb,var(--motion-cause-color),transparent 78%)" }, { boxShadow: "inset 0 0 0 1px transparent", backgroundColor: "transparent" }], { duration, easing: "ease-out" }));
      }
      const before = positions.current.get(row.dataset.driverNumber!);
      const after = nextPositions.get(row.dataset.driverNumber!);
      if (!reduced && speed < 30 && before != null && after != null && before !== after && typeof row.animate === "function") animations.current.push(row.animate([{ transform: `translateY(${before - after}px)` }, { transform: "translateY(0)" }], rowMotionTiming(cue?.cause, Math.abs(before - after) / Math.max(1, row.offsetHeight), posture, speed)));
    });
    positions.current = nextPositions;
  }, [container, revision, story, clearCue, stop]);
  useLayoutEffect(() => {
    const shell = container.current?.closest<HTMLElement>(".app-shell");
    if (!shell || typeof window.MutationObserver !== "function") return;
    const observer = new window.MutationObserver(() => {
      const jumped = shell.dataset.navigationGeneration !== previous.current?.generation || shell.dataset.recordingVersion !== previous.current?.recording;
      const fast = Number(shell.dataset.playbackSpeed) >= 30;
      if (shell.dataset.reducedMotion === "true" || fast || jumped) { stop(fast || jumped); positions.current.clear(); }
    });
    observer.observe(shell, { attributes: true, attributeFilter: ["data-reduced-motion", "data-playback-speed", "data-navigation-generation", "data-recording-version"] });
    return () => { observer.disconnect(); stop(true); };
  }, [container, stop]);
}
