import { useEffect, useRef, useState } from "react";
import type { StoryEvent } from "../../domain/protocol";
import type { StoryProps } from "./StoryFeed";
import { StoryMomentQueue, type ActiveMoment } from "./momentQueue";
import { availableStoryEvents, describeStory, storyDriverCode, storyDriverName, storyKind, storyLapTime, storyStamp, storyTeamStyle, type StoryDrivers, type StorySession } from "./presentation";
import "./story.css";

function DriverName({ number, drivers }: { number?: string; drivers: StoryDrivers }) {
  const name = storyDriverName(number, drivers);
  return <>{name.first && <><span className="to-first">{name.first}</span>{" "}</>}{name.surname}</>;
}

function DriverChip({ number, drivers, label }: { number: string; drivers: StoryDrivers; label?: string }) {
  return <span className="to-drv" style={storyTeamStyle(drivers[number])}><i /><b>{storyDriverCode(number, drivers)}</b>{label && <small>{label}</small>}</span>;
}

export function StoryMomentCard({ event, drivers = {}, session, exiting = false }: { event: StoryEvent; drivers?: StoryDrivers; session?: StorySession; exiting?: boolean }) {
  const description = describeStory(event, drivers, session);
  const kind = storyKind(event);
  const first = event.driverNumbers[0];
  const flag = kind === "FLAG" ? String(event.data.flag ?? event.cause ?? "").toLowerCase().replace(/[^a-z_]/g, "") : "";
  const provisional = event.state === "provisional" ? " · PROVISIONAL" : "";
  const name = first && drivers[first] ? <DriverName number={first} drivers={drivers} /> : event.title;
  let contents;
  switch (kind) {
    case "FLAG":
      contents = <div className="to-flagbox"><span className="to-tag">{event.lap != null ? `LAP ${event.lap}` : storyStamp(event, session)}</span><strong>{description.title}</strong>{description.detail && <em>{description.detail}</em>}</div>;
      break;
    case "WINNER": {
      // These are positions at this viewer cursor, not a prediction of the
      // final podium. A finisher's gap is printed only after their own flag.
      const classified = Object.values(drivers);
      const currentTop = classified.filter(driver => driver.position != null && driver.position <= 3
        && classified.filter(other => other.position === driver.position).length === 1)
        .sort((left, right) => left.position! - right.position!);
      const knownOrder = first && currentTop[0]?.number === first ? currentTop.map(driver => driver.number)
        : first ? [first] : [];
      const corrected = event.kind === "RESULT_CORRECTION";
      contents = <><div className="to-head"><span className="to-tag">{corrected ? "RESULT UPDATED" : `CHEQUERED FLAG${event.lap != null ? ` · LAP ${event.lap}` : ""}`}{provisional || " · PROVISIONAL"}</span><strong>{corrected || !first || !drivers[first] ? event.title : <>{name} wins</>}</strong></div><div className="to-podium">{knownOrder.map((number, index) => {
        const driver = drivers[number];
        const position = index === 0 ? 1 : driver?.position;
        const gap = index === 0 ? "WINNER" : driver?.classification === "FINISHED" ? driver.gap_to_leader ?? "FINISHED"
          : driver?.classification ?? (session?.total_laps != null && driver?.lap === session.total_laps ? "ON FINAL LAP" : "AWAITING FLAG");
        return <div key={number} className={`to-pod to-pod--${position}`} style={storyTeamStyle(driver)}><span className="to-pod-p">P{position}</span><b>{storyDriverCode(number, drivers)}</b><span className="to-pod-n">{storyDriverName(number, drivers).surname}</span><span className="to-pod-g mono">{gap}</span></div>;
      })}</div></>;
      break;
    }
    case "ELIMINATED":
      contents = <><div className="to-head"><span className="to-tag">{description.tag}{provisional}</span><strong>{event.driverNumbers.length} drivers eliminated</strong></div><div className="to-list">{event.driverNumbers.map(number => <DriverChip key={number} number={number} drivers={drivers} />)}</div></>;
      break;
    case "POLE": {
      const suppliedTop = Array.isArray(event.data.top) ? event.data.top.filter((number): number is string => typeof number === "string") : event.driverNumbers;
      const time = storyLapTime(event.data.lapTime ?? event.data.time);
      contents = <><div className="to-head"><span className="to-tag">POLE POSITION{session?.meeting_name ? ` · ${session.meeting_name.toUpperCase()}` : ""}{provisional}</span><strong>{name}</strong>{time && <em className="mono">{time}</em>}</div><div className="to-list">{suppliedTop.slice(0, 2).map((number, index) => <DriverChip key={number} number={number} drivers={drivers} label={index === 0 ? "POLE" : "P2"} />)}</div></>;
      break;
    }
    case "SESSION_END": {
      const settled = event.data.settled === true || event.data.completed === true;
      contents = <><div className="to-head"><span className="to-tag">SESSION COMPLETE{provisional}</span><strong>{settled && first && drivers[first] ? <>{name} fastest</> : event.title}</strong>{!settled && event.detail && <em>{event.detail}</em>}</div>{!!event.driverNumbers.length && <div className="to-list">{event.driverNumbers.map((number, index) => <DriverChip key={number} number={number} drivers={drivers} label={settled ? `P${index + 1}` : undefined} />)}</div>}</>;
      break;
    }
    case "PHASE":
      contents = <div className="to-head"><span className="to-tag">SEGMENT CHANGE</span><strong>{event.title}</strong>{event.detail && <em>{event.detail}</em>}</div>;
      break;
    case "LEAD_CHANGE":
      contents = <><div className="to-slab" /><div className="to-head"><span className="to-tag">{description.tag}</span><strong>{name}</strong><em>{description.detail}</em></div><div className="to-list">{event.driverNumbers.slice(0, 2).map((number, index) => <DriverChip key={number} number={number} drivers={drivers} label={index === 0 ? "P1" : drivers[number]?.position != null ? `P${drivers[number].position}` : undefined} />)}</div></>;
      break;
    default:
      contents = <><div className="to-slab" /><div className="to-head"><span className="to-tag">{description.tag}{provisional}</span><strong>{name}</strong>{description.detail && <em>{description.detail}</em>}</div></>;
  }
  return <aside className={`story-moment to-card to--${kind.toLowerCase()}${flag ? ` to-flag--${flag}` : ""}${exiting ? " is-leaving" : ""}`} style={storyTeamStyle(drivers[first])} role="status" aria-live="polite" data-event-id={event.id}>{contents}</aside>;
}

type MomentFrame = { active: ActiveMoment; drivers: StoryDrivers; session?: StorySession; exiting: boolean };
type MomentProps = StoryProps & { playing?: boolean; speed?: number; reducedMotion?: boolean; enabled?: boolean };

export function StoryMoments({ story, sessionKey, generation = 0, recordingVersion, playing = true, speed = 1, reducedMotion = false, drivers = {}, session, posture = "desktop", visible = true, enabled = true }: MomentProps) {
  const [frame, setFrame] = useState<MomentFrame | null>(null);
  const [pageVisible, setPageVisible] = useState(true);
  const previous = useRef<{ sequence: number; generation: number; session?: string | null; version?: string | null; visible: boolean } | null>(null);
  const queue = useRef(new StoryMomentQueue());
  const shown = useRef<ActiveMoment | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const identity = sessionKey ?? session?.key ?? story?.events[0]?.sessionKey;
  useEffect(() => {
    const change = () => setPageVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  useEffect(() => {
    const last = previous.current;
    const sequence = story?.sequence ?? 0;
    const shownNow = visible && enabled && pageVisible;
    previous.current = { sequence, generation, session: identity, version: recordingVersion, visible: shownNow };
    if (timer.current) clearTimeout(timer.current);
    if (!last || last.generation !== generation || last.session !== identity || last.version !== recordingVersion || sequence < last.sequence || !playing || !shownNow || !last.visible) {
      queue.current.clear();
      shown.current = null;
      if (exitTimer.current) clearTimeout(exitTimer.current);
      setFrame(null);
      return;
    }
    const candidates = availableStoryEvents(story).filter(event => event.availableSequence > last.sequence);
    queue.current.offer(candidates, speed, Date.now());
    const sync = () => {
      queue.current.advance(Date.now());
      const active = queue.current.current;
      if (active !== shown.current) {
        const wasShown = shown.current;
        shown.current = active;
        if (exitTimer.current) clearTimeout(exitTimer.current);
        if (active) setFrame({ active, drivers, session, exiting: false });
        else if (wasShown && !reducedMotion) {
          setFrame(value => value && { ...value, exiting: true });
          exitTimer.current = setTimeout(() => setFrame(null), 280);
        } else setFrame(null);
      }
      const deadline = queue.current.nextDeadline();
      if (deadline != null) timer.current = setTimeout(sync, Math.max(1, deadline - Date.now()));
    };
    sync();
  }, [story, generation, recordingVersion, playing, speed, identity, drivers, session, visible, enabled, pageVisible, reducedMotion]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); if (exitTimer.current) clearTimeout(exitTimer.current); }, []);
  return <div className={`story-moments to-layer to-layer--${posture}${reducedMotion ? " story-moments--still" : ""}`} aria-label="Session moments">{frame && <StoryMomentCard key={frame.active.event.id} event={frame.active.event} drivers={frame.drivers} session={frame.session} exiting={frame.exiting} />}</div>;
}
