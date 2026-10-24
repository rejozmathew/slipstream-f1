import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { DisplayPoint, TrackGeometry } from "../domain/trackGeometry";
import { observedProgressDelta, type TrackPosture, type TrackPresentationContext } from "../components/analysis/trackPresentation";

export function useTrackViewport(ref: RefObject<HTMLElement | SVGSVGElement | null>, posture?: TrackPosture) {
  const [size, setSize] = useState({ width: 800, height: 500, scale: 1, posture: posture ?? "desktop" as TrackPosture });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const bounds = element.getBoundingClientRect();
      const detected = posture ?? (element.closest(".tv-redesign") ? "tv" : element.closest(".mobile-session") ? "phone" : "desktop");
      const authoredScale = Number(window.getComputedStyle(element).getPropertyValue("--tv-scale"));
      const scale = detected === "tv" && Number.isFinite(authoredScale) && authoredScale > 0 ? authoredScale : 1;
      if (bounds.width > 0) setSize((current) => current.width === bounds.width && current.height === bounds.height && current.posture === detected && current.scale === scale ? current : { width: bounds.width, height: bounds.height || 500, posture: detected, scale });
    };
    if (typeof ResizeObserver === "function") { const observer = new ResizeObserver(measure); observer.observe(element); return () => observer.disconnect(); }
    const frame = window.requestAnimationFrame?.(measure);
    window.addEventListener("resize", measure);
    return () => { if (frame != null) window.cancelAnimationFrame(frame); window.removeEventListener("resize", measure); };
  }, [ref, posture]);
  return { ...size, posture: posture ?? size.posture };
}

function motionContext(element: Element | null, context: TrackPresentationContext) {
  const shell = element?.closest<HTMLElement>(".app-shell");
  const at = Date.parse(context.asOf ?? shell?.dataset.viewerTime ?? "");
  return { generation: String(context.navigationGeneration ?? shell?.dataset.navigationGeneration ?? "0"), identity: `${shell?.dataset.sessionKey ?? ""}:${shell?.dataset.recordingVersion ?? ""}`,
    reduced: context.reducedMotion ?? shell?.dataset.reducedMotion === "true", playing: context.playing ?? shell?.dataset.viewerPlaying !== "false", speed: context.speed ?? Number(shell?.dataset.playbackSpeed ?? 1), at: Number.isFinite(at) ? at : null };
}

/** Disable axis transitions before layout is painted on every explicit jump. */
export function useAxisMotion(ref: RefObject<HTMLElement | null>, revision: unknown, context: TrackPresentationContext) {
  const previous = useRef<ReturnType<typeof motionContext> | null>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const current = motionContext(element, context), last = previous.current;
    const snap = !last || last.generation !== current.generation || last.identity !== current.identity || (last.at != null && current.at != null && current.at < last.at) || current.reduced || !current.playing || current.speed >= 30;
    previous.current = current; element.dataset.trackMotion = snap ? "snap" : "smooth";
  }, [ref, revision, context]);
  useLayoutEffect(() => {
    const shell = ref.current?.closest<HTMLElement>(".app-shell");
    if (!shell || typeof window.MutationObserver !== "function") return;
    const observer = new window.MutationObserver(() => {
      const value = motionContext(ref.current, context);
      if (ref.current && (value.generation !== previous.current?.generation || value.reduced || !value.playing || value.speed >= 30)) ref.current.dataset.trackMotion = "snap";
    });
    observer.observe(shell, { attributes: true, attributeFilter: ["data-navigation-generation", "data-recording-version", "data-reduced-motion", "data-viewer-playing", "data-playback-speed"] });
    return () => observer.disconnect();
  }, [ref, context]);
}

export type TrackMotionTarget = { number: string; point: DisplayPoint; fraction: number | null; lap: number | null };
type MovingCar = { node: SVGGElement; point: DisplayPoint; progress: number | null; targetProgress: number | null; target: TrackMotionTarget; from: DisplayPoint; fromProgress: number | null; velocity: number; fromVelocity: number; response: number; samples: Array<{ distance: number; ms: number }>; started: number; duration: number; active: boolean; observedAt: number | null; receivedAt: number };

function advanceCar(car: MovingCar, timestamp: number, geometry: TrackGeometry, stop = false) {
  if (!car.active) return;
  const elapsed = Math.max(0, timestamp - car.started);
  let done = stop;
  if (car.fromProgress != null && car.targetProgress != null) {
    // Critically damped travel keeps velocity continuous when a new packet
    // arrives and gently approaches a sparse endpoint instead of slamming to
    // a stop. The response bound below keeps this entirely inside received
    // progress: it never predicts a future point or overshoots a corner.
    const distance = car.targetProgress - car.fromProgress;
    const coefficient = Math.max(0, car.response * distance - car.fromVelocity);
    const decay = Math.exp(-car.response * elapsed);
    const remaining = (distance + coefficient * elapsed) * decay;
    done ||= remaining <= .00001;
    car.progress = done ? car.targetProgress : car.targetProgress - remaining;
    car.velocity = done ? 0 : (car.fromVelocity + car.response * coefficient * elapsed) * decay;
    car.point = geometry.pointAt(car.progress);
  } else {
    const mix = stop ? 1 : Math.min(1, elapsed / car.duration);
    car.point = { x: car.from.x + (car.target.point.x - car.from.x) * mix, y: car.from.y + (car.target.point.y - car.from.y) * mix };
    done ||= mix === 1;
  }
  if (done) {
    car.point = car.target.point; car.progress = car.targetProgress; car.velocity = 0; car.active = false;
    delete car.node.dataset.trackMoving;
  }
}

/** Smooth only between already-received positions. No prediction or future cursor. */
export function useTrackMotion(ref: RefObject<SVGSVGElement | null>, targets: TrackMotionTarget[], geometry: TrackGeometry | null, context: TrackPresentationContext) {
  const cars = useRef(new Map<string, MovingCar>());
  const frame = useRef<number | null>(null);
  const drawFrame = useRef<((timestamp: number) => void) | null>(null);
  const previous = useRef<(ReturnType<typeof motionContext> & { geometry: TrackGeometry | null }) | null>(null);
  useLayoutEffect(() => {
    const svg = ref.current;
    if (!svg || !geometry) {
      if (frame.current != null) window.cancelAnimationFrame(frame.current);
      frame.current = null;
      cars.current.clear();
      previous.current = null;
      return;
    }
    const current = { ...motionContext(svg, context), geometry }, last = previous.current;
    previous.current = current;
    const jumped = !last || last.generation !== current.generation || last.identity !== current.identity || last.geometry !== geometry || (last.at != null && current.at != null && current.at < last.at);
    const snap = jumped || current.reduced || !current.playing || current.speed >= 30 || typeof window.requestAnimationFrame !== "function";
    const nodes = new Map([...svg.querySelectorAll<SVGGElement>("[data-track-driver]")].map((node) => [node.dataset.trackDriver!, node]));
    const now = window.performance.now();
    const place = (car: MovingCar) => car.node.setAttribute("transform", `translate(${car.point.x.toFixed(2)} ${car.point.y.toFixed(2)})`);
    const present = new Set(targets.map((target) => target.number));
    cars.current.forEach((_car, number) => { if (!present.has(number)) cars.current.delete(number); });
    for (const target of targets) {
      const node = nodes.get(target.number); if (!node) continue;
      const old = cars.current.get(target.number);
      // Timing-derived positions can arrive many seconds apart. Unrelated
      // packets must not shorten this driver's journey to a single frame.
      const sourceMs = old?.observedAt != null && current.at != null ? (current.at - old.observedAt) / Math.max(.01, current.speed) : old ? now - old.receivedAt : 1000;
      const duration = Math.min(15000, Math.max(120, sourceMs > 0 ? sourceMs : old?.duration ?? 1000));
      // Validate source movement against the previous observation, not a dot
      // that is still travelling towards it. Display lag is not a source jump.
      const delta = old?.target.fraction != null && target.fraction != null ? observedProgressDelta(old.target.fraction, target.fraction, old.target.lap, target.lap) : null;
      const changed = !old || old.target.point.x !== target.point.x || old.target.point.y !== target.point.y;
      if (!old || old.node !== node || snap || (changed && target.fraction != null && delta == null)) {
        const car: MovingCar = { node, point: target.point, progress: target.fraction, targetProgress: target.fraction, target, from: target.point, fromProgress: target.fraction, velocity: 0, fromVelocity: 0, response: 0, samples: [], started: now, duration, active: false, observedAt: current.at, receivedAt: now };
        cars.current.set(target.number, car); delete node.dataset.trackMoving; place(car);
      } else if (changed) {
        advanceCar(old, now, geometry);
        old.from = old.point; old.fromProgress = old.progress;
        if (delta != null && old.targetProgress != null && old.progress != null) {
          old.targetProgress += delta;
          if (sourceMs > 15000) old.samples = [];
          if (delta > 0) old.samples = [...old.samples, { distance: delta, ms: duration }].slice(-4);
          const distance = old.samples.reduce((sum, sample) => sum + sample.distance, 0);
          const elapsed = old.samples.reduce((sum, sample) => sum + sample.ms, 0);
          // A burst must not compress the entire unfinished journey into the
          // tiny gap between the newest packets. Smooth observed cadence only.
          old.duration = distance > 0 ? Math.max(120, (old.targetProgress - old.progress) * elapsed / distance) : duration;
          old.fromVelocity = old.velocity;
          old.response = Math.max(4 / old.duration, old.velocity / Math.max(.00001, old.targetProgress - old.progress));
        } else {
          old.targetProgress = null; old.duration = duration;
        }
        old.target = target; old.started = now; old.active = true; old.observedAt = current.at; old.receivedAt = now; node.dataset.trackMoving = "true"; place(old);
      } else {
        // 1.0 and 0.0 are the same physical point. Keep its updated lap counter
        // without restarting a journey or treating the next lap as a reversal.
        old.target = target;
        place(old);
      }
    }
    drawFrame.current = (timestamp: number) => {
      frame.current = null;
      const live = motionContext(svg, context);
      const stop = live.generation !== current.generation || live.identity !== current.identity || live.reduced || !live.playing || live.speed >= 30;
      let active = false;
      cars.current.forEach((car) => {
        if (!car.active) return;
        advanceCar(car, timestamp, geometry, stop);
        active ||= car.active;
        place(car);
      });
      if (active) frame.current = window.requestAnimationFrame((at) => drawFrame.current?.(at));
    };
    // Ordinary snapshot renders must not cancel/requeue a pending animation
    // tick. Keep one loop and let it read the latest targets and context.
    if (snap && frame.current != null) { window.cancelAnimationFrame(frame.current); frame.current = null; }
    if (!snap && frame.current == null && [...cars.current.values()].some((car) => car.active)) frame.current = window.requestAnimationFrame((at) => drawFrame.current?.(at));
  }, [ref, targets, geometry, context]);
  useLayoutEffect(() => {
    const states = cars.current;
    return () => { if (frame.current != null) window.cancelAnimationFrame(frame.current); frame.current = null; states.clear(); };
  }, []);
}
