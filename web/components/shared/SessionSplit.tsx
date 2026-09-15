import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

import { SESSION_SPLIT_LIMITS } from "../../domain/layout";

import "./session-split.css";

type SessionSplitProps = {
  className: string;
  timing: ReactNode;
  analysis: ReactNode;
  timingWidth: number;
  onTimingWidthChange: (width: number) => void;
};

export function SessionSplit({ className, timing, analysis, timingWidth, onTimingWidthChange }: SessionSplitProps) {
  const container = useRef<HTMLDivElement>(null);
  const pointer = useRef<{ id: number; offset: number } | null>(null);
  const [width, setWidth] = useState(0);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Keep both panes usable, including at browser zoom. Stored preferences are
  // only constrained for rendering; resizing the window does not overwrite them.
  const available = Math.max(1, width - 18);
  const minimum = width ? Math.max(SESSION_SPLIT_LIMITS.minimum, Math.min(560, available * .65) / available * 100) : SESSION_SPLIT_LIMITS.minimum;
  const maximum = width ? Math.max(minimum, Math.min(SESSION_SPLIT_LIMITS.maximum, (available - 300) / available * 100)) : SESSION_SPLIT_LIMITS.maximum;
  const clamp = (value: number) => Math.min(maximum, Math.max(minimum, value));
  const value = clamp(Number.isFinite(timingWidth) ? timingWidth : 66);

  const start = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    pointer.current = { id: event.pointerId, offset: event.clientX - bounds.left - bounds.width / 2 };
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (pointer.current?.id !== event.pointerId || !container.current) return;
    const bounds = container.current.getBoundingClientRect();
    onTimingWidthChange(clamp((event.clientX - bounds.left - pointer.current.offset - 9) / (bounds.width - 18) * 100));
  };
  const stop = (event: PointerEvent<HTMLDivElement>) => {
    if (pointer.current?.id !== event.pointerId) return;
    pointer.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 5 : 1;
    const next = event.key === "ArrowLeft" ? value - step : event.key === "ArrowRight" ? value + step : event.key === "Home" ? minimum : event.key === "End" ? maximum : null;
    if (next == null) return;
    event.preventDefault();
    onTimingWidthChange(clamp(next));
  };

  return <div ref={container} className={`session-split ${className}`} style={{ gridTemplateColumns: `minmax(0, ${value}fr) 18px minmax(0, ${100 - value}fr)` }}>
    {timing}
    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex -- A focusable ARIA separator with value and keyboard controls is the window splitter pattern. */}
    <div className="session-split-handle" role="separator" tabIndex={0} aria-label="Resize timing and analysis panels" aria-orientation="vertical" aria-valuemin={Math.round(minimum)} aria-valuemax={Math.round(maximum)} aria-valuenow={Math.round(value)} aria-valuetext={`${Math.round(value)}% timing tower`} data-dragging={dragging || undefined} title="Drag to resize · Arrow keys to adjust · Double-click to reset" onPointerDown={start} onPointerMove={move} onPointerUp={stop} onPointerCancel={stop} onLostPointerCapture={stop} onKeyDown={keyboard} onDoubleClick={() => onTimingWidthChange(clamp(66))}><span /><b aria-hidden="true">⋮</b></div>
    {analysis}
  </div>;
}
