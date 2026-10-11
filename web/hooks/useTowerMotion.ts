import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";
import type { StorySnapshot } from "../domain/protocol";
import { freshRowCues, rowMotionTiming, towerMotionScale, translationY, type RowCause, type RowCue } from "../domain/towerMotion";

type RowRuntime = {
  row: HTMLElement; top: number; index: number; height: number;
  movement?: Animation; effects: Set<Animation>; timers: Map<string, ReturnType<typeof setTimeout>>;
  recent?: RowCue;
};

function schedule(runtime: RowRuntime, key: string, duration: number, action: () => void) {
  const old = runtime.timers.get(key);
  if (old) clearTimeout(old);
  const timer = setTimeout(() => { runtime.timers.delete(key); action(); }, duration);
  runtime.timers.set(key, timer);
}

function cancelAnimations(runtime: RowRuntime) {
  runtime.movement?.cancel(); runtime.movement = undefined;
  runtime.effects.forEach((animation) => animation.cancel()); runtime.effects.clear();
  delete runtime.row.dataset.motionMoving;
}

function clearRow(runtime: RowRuntime) {
  cancelAnimations(runtime);
  runtime.timers.forEach(clearTimeout); runtime.timers.clear(); runtime.recent = undefined;
  delete runtime.row.dataset.motionCause; delete runtime.row.dataset.motionLabel;
  runtime.row.style.removeProperty("z-index");
  runtime.row.querySelectorAll<HTMLElement>("[data-motion-flash]").forEach((cell) => delete cell.dataset.motionFlash);
  const wash = runtime.row.querySelector<HTMLElement>(".tower-motion-wash"); if (wash) wash.style.opacity = "0";
  const delta = runtime.row.querySelector<HTMLElement>(".tower-motion-delta"); if (delta) { delta.className = "tower-motion-delta"; delta.textContent = ""; }
  runtime.row.querySelector(".tower-motion-chips")?.replaceChildren();
}

function effect(runtime: RowRuntime, element: HTMLElement | null, frames: Keyframe[], options: KeyframeAnimationOptions) {
  if (!element || typeof element.animate !== "function") return;
  const animation = element.animate(frames, options);
  runtime.effects.add(animation);
  animation.onfinish = () => runtime.effects.delete(animation);
}

function wash(runtime: RowRuntime, colour: string, duration: number, peak: number, reduced: boolean) {
  const element = runtime.row.querySelector<HTMLElement>(".tower-motion-wash");
  if (!element) return;
  element.style.background = colour;
  if (reduced || typeof element.animate !== "function") {
    element.style.opacity = String(peak * .6);
    schedule(runtime, "wash", duration, () => { element.style.opacity = "0"; });
  } else effect(runtime, element, [{ opacity: 0 }, { opacity: peak, offset: .12 }, { opacity: peak * .7, offset: .6 }, { opacity: 0 }], { duration, easing: "linear" });
}

function delta(runtime: RowRuntime, up: boolean, distance: number, duration: number) {
  const element = runtime.row.querySelector<HTMLElement>(".tower-motion-delta");
  if (!element) return;
  element.className = `tower-motion-delta ${up ? "is-up" : "is-down"}`;
  element.textContent = `${up ? "▲" : "▼"}${distance}`;
  schedule(runtime, "delta", duration, () => { element.className = "tower-motion-delta"; });
}

function chip(runtime: RowRuntime, text: string, kind: string, duration: number, compound?: string) {
  const host = runtime.row.querySelector(".tower-motion-chips");
  if (!host) return;
  host.querySelector(`[data-chip="${kind}"]`)?.remove();
  const element = document.createElement("span");
  element.className = `tower-motion-chip chip-${kind}`; element.dataset.chip = kind; element.textContent = text;
  if (compound) {
    const badge = document.createElement("span"); badge.className = "tower-chip-compound"; badge.dataset.compound = compound;
    badge.textContent = ({ SOFT: "S", MEDIUM: "M", HARD: "H", INTERMEDIATE: "I", WET: "W" } as Record<string, string>)[compound] ?? "—";
    element.append(badge);
  }
  host.append(element);
  schedule(runtime, `chip-${kind}`, duration, () => {
    element.classList.add("is-leaving");
    schedule(runtime, `chip-remove-${kind}`, 320, () => element.remove());
  });
}

function flash(runtime: RowRuntime, kind: "best" | "improve" | "deleted", duration: number, reduced: boolean) {
  const cell = runtime.row.querySelector<HTMLElement>(".tower-time");
  if (!cell) return;
  cell.dataset.motionFlash = kind;
  if (!reduced && kind !== "deleted") {
    const colour = kind === "best" ? "#b14cff" : "#2fd97f";
    effect(runtime, cell, [{ color: kind === "best" ? "#fff" : "#06120c", backgroundColor: colour, boxShadow: `0 0 0 4px ${colour}` }, { color: kind === "best" ? "#fff" : "#06120c", backgroundColor: colour, boxShadow: `0 0 0 4px ${colour}`, offset: .3 }, { backgroundColor: "transparent", boxShadow: "0 0 0 0 transparent" }], { duration, easing: "cubic-bezier(.16,1,.3,1)" });
  }
  schedule(runtime, "flash", duration, () => delete cell.dataset.motionFlash);
}

function pulse(runtime: RowRuntime, reduced: boolean) {
  if (!reduced) effect(runtime, runtime.row.querySelector<HTMLElement>(":scope > strong, .phone-position"), [{ transform: "scale(1.6)", color: "#2fd97f" }, { transform: "scale(1)" }], { duration: 900, easing: "cubic-bezier(.16,1,.3,1)" });
}

/** Keyed rows retain their own travel: another driver's update never cancels it. */
export function useTowerMotion(container: RefObject<HTMLDivElement | null>, revision: unknown, story?: StorySnapshot) {
  const rows = useRef(new Map<string, RowRuntime>());
  const previous = useRef<{ sequence: number; generation?: string; session?: string; recording?: string; hasStory: boolean; visible: boolean } | null>(null);
  const tableFade = useRef<Animation | null>(null);
  const stop = useCallback((clear: boolean) => {
    tableFade.current?.cancel(); tableFade.current = null;
    rows.current.forEach((runtime) => clear ? clearRow(runtime) : cancelAnimations(runtime));
  }, []);

  useLayoutEffect(() => {
    const table = container.current;
    const shell = table?.closest<HTMLElement>(".app-shell");
    const last = previous.current;
    const visible = Boolean(table?.getBoundingClientRect().width);
    const current = { sequence: story?.sequence ?? last?.sequence ?? 0, generation: shell?.dataset.navigationGeneration,
      session: shell?.dataset.sessionKey, recording: shell?.dataset.recordingVersion,
      hasStory: Boolean(story) || Boolean(last?.hasStory), visible };
    previous.current = current;
    const jump = Boolean(last && (last.generation !== current.generation || last.session !== current.session || last.recording !== current.recording || current.sequence < last.sequence));
    const reduced = shell?.dataset.reducedMotion === "true";
    const speed = Number(shell?.dataset.playbackSpeed ?? 1);
    const playing = shell?.dataset.viewerPlaying !== "false";
    const silent = jump || !last?.visible || speed >= 30 || !playing;
    if (!table || !visible) { stop(true); rows.current.clear(); return; }
    const elements = [...table.querySelectorAll<HTMLElement>("[data-driver-number]")];
    const posture = table.closest(".tv-redesign") ? "tv" : table.closest(".phone-timing") ? "phone" : "desktop";
    const scale = towerMotionScale(posture, speed);
    const cues = last?.hasStory && !silent ? freshRowCues(story, last.sequence, shell?.dataset.trackStatus, speed) : new Map<string, RowCue>();
    const now = story?.asOf ? Date.parse(story.asOf) : 0;
    // Read every current transform before cancelling or changing any row. An
    // interrupted move starts at its visible location, not its old destination.
    const measured = elements.map((row, index) => {
      const prior = rows.current.get(row.dataset.driverNumber!);
      const runtime = prior?.row === row ? prior : undefined;
      return { row, index, top: row.offsetTop, height: Math.max(1, row.offsetHeight), runtime,
        remainder: runtime?.movement?.playState === "running" ? translationY(window.getComputedStyle(row).transform) : 0 };
    });
    if (silent) stop(true);
    else if (reduced) stop(false);
    if (jump && !reduced && speed < 30 && typeof table.animate === "function") tableFade.current = table.animate([{ opacity: .35 }, { opacity: 1 }], { duration: 350, easing: "ease-out" });
    const present = new Set(elements.map((row) => row.dataset.driverNumber!));
    rows.current.forEach((runtime, number) => { if (!present.has(number)) { clearRow(runtime); rows.current.delete(number); } });
    for (const item of measured) {
      const { row, top, index, height } = item;
      const number = row.dataset.driverNumber!;
      if (!item.runtime) {
        const old = rows.current.get(number); if (old) clearRow(old);
        rows.current.set(number, { row, top, index, height, effects: new Set(), timers: new Map() });
        continue;
      }
      const runtime = item.runtime;
      const moved = runtime.index !== index;
      const geometryChanged = runtime.top !== top;
      const up = index < runtime.index;
      const distance = Math.abs(index - runtime.index);
      const cue = cues.get(number);
      if (cue) runtime.recent = cue;
      const recent = runtime.recent && now - Date.parse(runtime.recent.availableAt) < 8000 && !["pass", "passed"].includes(runtime.recent.cause) ? runtime.recent : undefined;
      const factual = cue ?? recent;
      let cause: RowCause = factual?.cause ?? "neutral";
      const timed = table.dataset.motionVariant !== "race";
      if (moved && !factual) {
        if (timed) cause = up ? "promoted" : "pushed";
        else if (row.dataset.motionState === "IN_PIT") cause = "pit";
        else if (!up && ["STOPPED", "RETIRED", "RETIRED_INDICATED", "DNF", "DSQ", "DNS", "WITHDRAWN", "EXCLUDED"].includes(row.dataset.motionState ?? "")) cause = "out";
        else if (Number(table.dataset.motionLap) > 0 && Number(table.dataset.motionLap) <= 1) cause = "start";
      } else if (moved && up && cause === "pit" && row.dataset.motionState !== "IN_PIT") cause = "promoted";
      const timing = rowMotionTiming(cause, distance, posture, speed);
      if (!silent && (moved || cue)) {
        row.dataset.motionCause = cause;
        row.dataset.motionLabel = cue?.label ?? "ORDER CHANGE";
        row.style.zIndex = String(timing.zIndex);
        schedule(runtime, "cause", timing.duration + 1400 * scale, () => { delete row.dataset.motionCause; delete row.dataset.motionLabel; if (!runtime.movement) row.style.removeProperty("z-index"); });
        const cut = Number(table.dataset.motionCut);
        const crossesCut = moved && cut > 0 && ((runtime.index < cut && index >= cut) || (runtime.index >= cut && index < cut));
        if (cause === "pass") { wash(runtime, "var(--tower-team)", 2600 * scale, .3, reduced); delta(runtime, true, cue?.count ?? distance, 3600 * scale); pulse(runtime, reduced); }
        else if (cause === "passed") delta(runtime, false, cue?.count ?? distance, 2400 * scale);
        else if (cause === "improve" || cause === "best") {
          const colour = cause === "best" ? "var(--tower-session-best)" : "var(--tower-personal-best)";
          wash(runtime, colour, (moved ? 2600 : 1800) * scale, moved ? .26 : .16, reduced);
          flash(runtime, cause, 2600 * scale, reduced);
          if (moved && up) { delta(runtime, true, distance, 3600 * scale); pulse(runtime, reduced); if (crossesCut) chip(runtime, "ABOVE CUT", "safe", 3500 * scale); }
        } else if (cause === "pushed" && moved) {
          if (crossesCut) { chip(runtime, "DROP ZONE", "drop", 4200 * scale); wash(runtime, "var(--tower-loss)", 2200 * scale, .18, reduced); }
          else delta(runtime, false, distance, 1800 * scale);
        } else if (cause === "deleted" && cue) { chip(runtime, "LAP DELETED", "amber", 4200 * scale); wash(runtime, "var(--tower-amber)", 2400 * scale, .2, reduced); flash(runtime, "deleted", 2600 * scale, reduced); }
        else if (cause === "class") { wash(runtime, "var(--tower-amber)", 2600 * scale, .22, reduced); if (moved) delta(runtime, up, distance, 5000 * scale); }
        else if (cause === "out" && cue) chip(runtime, cue.label === "SOURCE STOPPAGE" ? row.dataset.motionState ?? "STOPPED" : cue.label, "out", 5000 * scale);
        else if (cause === "penalty" && cue) chip(runtime, "PENALTY NOTICE", "pen", 5000 * scale);
        if (cue?.kind === "PIT_EXIT") chip(runtime, "PIT EXIT", "fresh", 7000 * scale, row.dataset.motionCompound);
      }
      // The pit-exit badge follows the current source compound if it arrives late.
      const compound = row.querySelector<HTMLElement>('.chip-fresh .tower-chip-compound');
      if (compound && row.dataset.motionCompound) {
        compound.dataset.compound = row.dataset.motionCompound;
        compound.textContent = ({ SOFT: "S", MEDIUM: "M", HARD: "H", INTERMEDIATE: "I", WET: "W" } as Record<string, string>)[row.dataset.motionCompound] ?? "—";
      }
      if (!silent && !reduced && geometryChanged && typeof row.animate === "function") {
        const from = runtime.top + item.remainder - top;
        runtime.movement?.cancel();
        const animation = row.animate([{ transform: `translateY(${from}px)` }, { transform: "translateY(0)" }], moved ? timing : { duration: 400 * scale, easing: "cubic-bezier(.16,1,.3,1)" });
        runtime.movement = animation; row.dataset.motionMoving = "true";
        row.style.zIndex = String(timing.zIndex);
        animation.onfinish = () => {
          if (runtime.movement !== animation) return;
          runtime.movement = undefined; delete row.dataset.motionMoving;
          if (!row.dataset.motionCause) row.style.removeProperty("z-index");
        };
      }
      runtime.top = top; runtime.index = index; runtime.height = height;
    }
  }, [container, revision, story, stop]);

  useLayoutEffect(() => {
    const shell = container.current?.closest<HTMLElement>(".app-shell");
    if (!shell || typeof window.MutationObserver !== "function") return;
    const rowStates = rows.current;
    const observer = new window.MutationObserver(() => {
      const jumped = shell.dataset.navigationGeneration !== previous.current?.generation || shell.dataset.recordingVersion !== previous.current?.recording;
      const fast = Number(shell.dataset.playbackSpeed) >= 30;
      const paused = shell.dataset.viewerPlaying === "false";
      if (shell.dataset.reducedMotion === "true" || fast || jumped || paused) {
        stop(fast || jumped || paused);
        if (jumped) rows.current.clear();
      }
    });
    observer.observe(shell, { attributes: true, attributeFilter: ["data-reduced-motion", "data-playback-speed", "data-navigation-generation", "data-recording-version", "data-viewer-playing"] });
    return () => { observer.disconnect(); stop(true); rowStates.clear(); };
  }, [container, stop]);
}
