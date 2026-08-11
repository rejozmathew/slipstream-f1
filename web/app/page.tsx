import { useEffect, useMemo, useRef, useState } from "react";

type Driver = {
  number: string;
  code: string | null;
  name: string | null;
  team: string | null;
  team_colour: string | null;
  position: number | null;
  lap: number | null;
  gap_to_leader: string | null;
  interval_to_ahead: string | null;
  last_lap: string | null;
  best_lap: string | null;
  compound: string | null;
  tyre_age: number | null;
  stint_laps: number | null;
  pit_count: number;
  track_position: number | null;
  x?: number | null;
  y?: number | null;
  z?: number | null;
  status: string;
};

type RaceState = {
  updated_at: string | null;
  session: {
    key: string | null;
    name: string | null;
    meeting_name: string | null;
    session_type: string | null;
    circuit: string | null;
    location: string | null;
    started_at: string | null;
    ended_at: string | null;
    lap: number | null;
    total_laps: number | null;
    track_status: string | null;
    gmt_offset: string | null;
    local_time: string | null;
    status: string;
  };
  circuit?: {
    key: string | null;
    name: string | null;
    year: number | null;
    rotation: number | null;
    path: Array<[number, number]>;
    source: string | null;
    availability: Record<string, string>;
  };
  weather?: {
    updated_at: string | null;
    air_temperature: number | null;
    track_temperature: number | null;
    humidity: number | null;
    pressure: number | null;
    rainfall: boolean | null;
    wind_speed: number | null;
    wind_direction: number | null;
    availability: Record<string, string>;
  };
  drivers: Record<string, Driver>;
  race_control: Array<{
    occurred_at: string;
    category: string;
    message: string;
    flag: string | null;
    scope?: string | null;
    driver_number?: string | null;
  }>;
};

type DisplayPoint = { x: number; y: number };
type TrackGeometry = {
  points: DisplayPoint[];
  polyline: string;
  pointAt: (fraction: number) => DisplayPoint;
  project: (x: number, y: number) => DisplayPoint;
};

type StateEnvelope = {
  v: number;
  seq: number;
  type?: string;
  sessionTime?: string | null;
  playback?: { playing: boolean };
  data: RaceState;
};
type ReplayMetadata = {
  v: number;
  sessionKey: string;
  eventCount: number;
  startTime: string | null;
  endTime: string | null;
  durationSeconds: number;
  available: boolean;
  isLive: boolean;
  downloadable: boolean;
  positionMode: "precise_xy" | "timing_estimate" | "unavailable";
};
type CatalogSession = {
  sessionKey: string;
  year: number;
  meetingKey: string;
  meetingName: string;
  sessionName: string;
  sessionType: string;
  circuit: string | null;
  location: string | null;
  dateStart: string;
  dateEnd: string;
  available: boolean;
  isLive: boolean;
  circuitShapeAvailable: boolean;
  positionMode: "precise_xy" | "timing_estimate" | "unavailable";
};
type ReplayCatalog = {
  v: number;
  defaultSessionKey: string;
  downloadsEnabled?: boolean;
  sessions: CatalogSession[];
};

const sampleDrivers: Driver[] = [
  ["55", "SAI", "Carlos Sainz", "Ferrari", "F91536", 1, "LEADER", null, "HARD", 30, 30, 1, 0.999, "1:38.637"],
  ["4", "NOR", "Lando Norris", "McLaren", "FF8700", 2, "+1.918", "+1.918", "HARD", 30, 30, 1, 0.603, "1:38.148"],
  ["16", "LEC", "Charles Leclerc", "Ferrari", "F91536", 3, "+5.738", "+3.834", "HARD", 30, 30, 1, 0.545, "1:38.439"],
  ["63", "RUS", "George Russell", "Mercedes", "27F4D2", 4, "+10.745", "+5.051", "MEDIUM", 6, 6, 2, 0.509, "1:37.006"],
  ["44", "HAM", "Lewis Hamilton", "Mercedes", "27F4D2", 5, "+14.382", "+3.605", "MEDIUM", 6, 6, 2, 0.466, "1:36.462"],
  ["10", "GAS", "Pierre Gasly", "Alpine", "2293D1", 6, "+30.693", "+15.840", "HARD", 30, 30, 1, 0.287, "1:38.688"],
  ["81", "PIA", "Oscar Piastri", "McLaren", "FF8700", 7, "+34.447", "+3.754", "HARD", 30, 30, 1, 0.285, "1:38.832"],
  ["40", "LAW", "Liam Lawson", "AlphaTauri", "5E8FAA", 8, "+39.570", "+5.123", "HARD", 30, 30, 1, 0.21, "1:41.093"],
].map(([number, code, name, team, colour, position, gap, interval, compound, age, stint, pits, track, last]) => ({
  number: number as string,
  code: code as string,
  name: name as string,
  team: team as string,
  team_colour: colour as string,
  position: position as number,
  lap: 50,
  gap_to_leader: gap as string,
  interval_to_ahead: interval as string | null,
  last_lap: last as string,
  best_lap: null,
  compound: compound as string,
  tyre_age: age as number,
  stint_laps: stint as number,
  pit_count: pits as number,
  track_position: track as number,
  status: "RUNNING",
}));

const sampleCircuitX = [1076,843,683,530,124,-586,-1003,-1131,-943,-576,-430,-728,-1435,-2489,-3576,-5131,-6490,-7456,-8211,-8751,-9114,-9452,-9859,-10239,-10826,-11396,-11884,-12351,-13015,-13174,-12710,-12191,-11972,-11361,-10944,-10655,-10509,-10393,-10164,-9854,-9532,-9082,-8595,-7908,-6810,-5541,-4282,-3070,-2504,-2265,-1665,-793,367,1038,1162];
const sampleCircuitY = [-441,1090,2385,3311,3629,4025,3962,3480,2612,1691,875,279,153,234,320,490,1164,1780,2142,1786,1115,548,762,1236,1643,1377,501,-365,-1480,-2113,-2642,-3153,-3760,-4281,-4826,-4825,-4260,-3450,-2128,-959,-98,73,-313,-940,-1434,-1519,-1592,-1628,-1793,-2341,-2597,-2621,-2661,-2112,-974];
const sampleCircuitPath = sampleCircuitX.map(
  (x, index) => [x, sampleCircuitY[index]] as [number, number],
);

const sampleState: RaceState = {
  updated_at: "2023-09-17T13:29:59.630000+00:00",
  session: {
    key: "9165",
    name: "Race",
    meeting_name: "Singapore Grand Prix",
    session_type: "Race",
    circuit: "Marina Bay",
    location: "Singapore",
    started_at: "2023-09-17T12:00:00+00:00",
    ended_at: "2023-09-17T14:00:00+00:00",
    lap: 50,
    total_laps: 62,
    track_status: "GREEN",
    gmt_offset: "08:00:00",
    local_time: "2023-09-17T21:29:59.630000+08:00",
    status: "STARTED",
  },
  circuit: {
    key: "61",
    name: "Marina Bay Street Circuit",
    year: 2023,
    rotation: 335,
    path: sampleCircuitPath,
    source: "https://api.multiviewer.app/api/v1/circuits/61/2023",
    availability: { path: "available" },
  },
  weather: {
    updated_at: "2023-09-17T13:29:55+00:00",
    air_temperature: 29.1,
    track_temperature: 36.4,
    humidity: 75,
    pressure: 1008.6,
    rainfall: false,
    wind_speed: 2.4,
    wind_direction: 143,
    availability: {
      air_temperature: "available",
      track_temperature: "available",
      humidity: "available",
      pressure: "available",
      rainfall: "available",
      wind_speed: "available",
      wind_direction: "available",
    },
  },
  drivers: Object.fromEntries(sampleDrivers.map((driver) => [driver.number, driver])),
  race_control: [
    { occurred_at: "13:25:03", category: "DRS", message: "DRS ENABLED IN ZONE 2", flag: null },
    { occurred_at: "13:25:29", category: "CarEvent", message: "CAR 14 OFF TRACK AND CONTINUED AT TURN 14", flag: null },
    { occurred_at: "13:29:59", category: "Other", message: "PIT EXIT INCIDENT NOTED — VSC INFRINGEMENT", flag: null },
  ],
};

function buildTrackGeometry(
  sourcePath: Array<[number, number]> | undefined,
  rotation = 0,
): TrackGeometry | null {
  if (!sourcePath || sourcePath.length < 3) return null;

  const sourceCenter = sourcePath.reduce(
    (center, point) => ({ x: center.x + point[0] / sourcePath.length, y: center.y + point[1] / sourcePath.length }),
    { x: 0, y: 0 },
  );
  const angle = (rotation * Math.PI) / 180;
  const rotated = sourcePath.map(([x, y]) => {
    const dx = x - sourceCenter.x;
    const dy = y - sourceCenter.y;
    return {
      x: dx * Math.cos(angle) - dy * Math.sin(angle),
      y: dx * Math.sin(angle) + dy * Math.cos(angle),
    };
  });
  const minX = Math.min(...rotated.map((point) => point.x));
  const maxX = Math.max(...rotated.map((point) => point.x));
  const minY = Math.min(...rotated.map((point) => point.y));
  const maxY = Math.max(...rotated.map((point) => point.y));
  const width = 1000;
  const height = 650;
  const padding = 58;
  const scale = Math.min(
    (width - padding * 2) / Math.max(maxX - minX, 1),
    (height - padding * 2) / Math.max(maxY - minY, 1),
  );
  const drawnWidth = (maxX - minX) * scale;
  const drawnHeight = (maxY - minY) * scale;
  const xOffset = (width - drawnWidth) / 2;
  const yOffset = (height - drawnHeight) / 2;
  const points = rotated.map((point) => ({
    x: xOffset + (point.x - minX) * scale,
    y: yOffset + (maxY - point.y) * scale,
  }));
  const closed = [...points, points[0]];
  const distances = [0];
  for (let index = 1; index < closed.length; index += 1) {
    distances.push(
      distances[index - 1] + Math.hypot(
        closed[index].x - closed[index - 1].x,
        closed[index].y - closed[index - 1].y,
      ),
    );
  }
  const totalDistance = distances[distances.length - 1];
  const project = (x: number, y: number) => {
    const dx = x - sourceCenter.x;
    const dy = y - sourceCenter.y;
    const rotatedX = dx * Math.cos(angle) - dy * Math.sin(angle);
    const rotatedY = dx * Math.sin(angle) + dy * Math.cos(angle);
    return {
      x: xOffset + (rotatedX - minX) * scale,
      y: yOffset + (maxY - rotatedY) * scale,
    };
  };

  return {
    points,
    polyline: closed.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" "),
    pointAt: (fraction: number) => {
      const target = (((fraction % 1) + 1) % 1) * totalDistance;
      let index = distances.findIndex((distance) => distance >= target);
      if (index <= 0) index = 1;
      const start = closed[index - 1];
      const end = closed[index];
      const segmentLength = distances[index] - distances[index - 1];
      const mix = segmentLength ? (target - distances[index - 1]) / segmentLength : 0;
      return { x: start.x + (end.x - start.x) * mix, y: start.y + (end.y - start.y) * mix };
    },
    project,
  };
}

function compoundClass(compound: string | null) {
  return `compound compound-${(compound ?? "unknown").toLowerCase()}`;
}

function utcOffsetLabel(offset: string | null) {
  if (!offset) return "";
  const sign = offset.startsWith("-") || offset.startsWith("+") ? "" : "+";
  return `UTC${sign}${offset.slice(0, 6)}`;
}

function formatSessionDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value)).toUpperCase();
}

function formatDuration(seconds: number) {
  const safe = Math.max(0, Math.round(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const remainder = safe % 60;
  return hours > 0
    ? `${hours}:${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`
    : `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

function trackStatusClass(status: string | null) {
  const normalized = status?.toUpperCase() ?? "";
  if (normalized === "RED") return "is-red";
  if (normalized.includes("YELLOW") || normalized.includes("SAFETY") || normalized === "VSC") return "is-yellow";
  if (normalized === "GREEN") return "is-green";
  if (normalized === "CHEQUERED") return "is-chequered";
  return "is-neutral";
}

export default function Home() {
  const [state, setState] = useState<RaceState>(sampleState);
  const [sequence, setSequence] = useState(0);
  const [metadata, setMetadata] = useState<ReplayMetadata | null>(null);
  const [catalog, setCatalog] = useState<ReplayCatalog | null>(null);
  const [selectedSessionKey, setSelectedSessionKey] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState<string | null>(sampleState.updated_at);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(10);
  const [delaySeconds, setDelaySeconds] = useState(0);
  const [downloadState, setDownloadState] = useState<"idle" | "downloading" | "error">("idle");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [libraryRevision, setLibraryRevision] = useState(0);
  const [transport, setTransport] = useState<"stream" | "rest" | "preview">("preview");
  const socketRef = useRef<WebSocket | null>(null);
  const apiBase = (import.meta.env.VITE_SLIPSTREAM_API ?? "").replace(/\/$/, "");
  const selectedCatalogEntry = catalog?.sessions.find(
    (item) => item.sessionKey === selectedSessionKey,
  );

  useEffect(() => {
    let active = true;
    void fetch(`${apiBase}/api/v1/catalog`, { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((result: ReplayCatalog | null) => {
        if (!active || !result) return;
        setCatalog(result);
        setSelectedSessionKey((current) => current ?? result.defaultSessionKey);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [apiBase]);

  useEffect(() => {
    let active = true;
    let fallbackTimer: number | undefined;
    const query = selectedSessionKey
      ? `?session_key=${encodeURIComponent(selectedSessionKey)}`
      : "";
    const replayIsAvailable = selectedCatalogEntry?.available ?? true;

    const applyEnvelope = (envelope: StateEnvelope) => {
      if (!active) return;
      setState(envelope.data);
      setSequence(envelope.seq);
      setPlayhead(envelope.sessionTime ?? envelope.data.updated_at);
      if (envelope.playback) setIsPlaying(envelope.playback.playing);
    };

    const refresh = async () => {
      try {
        const response = await fetch(`${apiBase}/api/v1/state${query}`, { cache: "no-store" });
        if (!response.ok) return;
        const envelope = (await response.json()) as StateEnvelope;
        applyEnvelope(envelope);
        if (active) setTransport("rest");
      } catch {
        if (active) setTransport("preview");
      }
    };

    const startFallback = () => {
      if (fallbackTimer !== undefined) return;
      void refresh();
      fallbackTimer = window.setInterval(refresh, 3000);
    };

    void fetch(`${apiBase}/api/v1/replay${query}`, { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((metadata: ReplayMetadata | null) => {
        if (active && metadata) setMetadata(metadata);
      })
      .catch(() => undefined);

    if (!replayIsAvailable) {
      void refresh();
      return () => {
        active = false;
        if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer);
      };
    }

    const streamOrigin = apiBase
      ? apiBase.replace(/^http/, "ws")
      : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
    const streamUrl = `${streamOrigin}/api/v1/stream${query}`;
    const socket = new WebSocket(streamUrl);
    socketRef.current = socket;
    socket.onopen = () => {
      if (!active) return;
      setTransport("stream");
      if (fallbackTimer !== undefined) {
        window.clearInterval(fallbackTimer);
        fallbackTimer = undefined;
      }
    };
    socket.onmessage = (message) => {
      try {
        const envelope = JSON.parse(message.data) as StateEnvelope;
        if (envelope.type !== "error") applyEnvelope(envelope);
      } catch {
        // Ignore malformed frames; the next snapshot can recover.
      }
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (active) {
        setIsPlaying(false);
        startFallback();
      }
    };

    return () => {
      active = false;
      socket.close();
      socketRef.current = null;
      if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer);
    };
  }, [apiBase, selectedSessionKey, selectedCatalogEntry?.available, libraryRevision]);

  const sendReplayCommand = (command: Record<string, unknown>) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(command));
    }
  };

  const drivers = useMemo(
    () =>
      Object.values(state.drivers).sort(
        (a, b) => (a.position ?? 99) - (b.position ?? 99),
      ),
    [state.drivers],
  );
  const catalogSessions = catalog?.sessions ?? [];
  const selectedCatalogSession = selectedCatalogEntry;
  const selectedYear = selectedCatalogSession?.year
    ?? catalogSessions[catalogSessions.length - 1]?.year;
  const yearSessions = catalogSessions.filter((item) => item.year === selectedYear);
  const meetings = Array.from(
    new Map(yearSessions.map((item) => [item.meetingKey, item])).values(),
  );
  const selectedMeetingKey = selectedCatalogSession?.meetingKey ?? meetings[0]?.meetingKey;
  const meetingSessions = yearSessions.filter(
    (item) => item.meetingKey === selectedMeetingKey,
  );
  const session = state.session;
  const circuit = state.circuit;
  const trackGeometry = useMemo(
    () => buildTrackGeometry(circuit?.path, circuit?.rotation ?? 0),
    [circuit?.path, circuit?.rotation],
  );
  const weather = state.weather;
  const rainLabel = weather?.rainfall === true ? "RAIN DETECTED" : weather?.rainfall === false ? "NO RAIN" : "NO DATA";
  const recentMessages = state.race_control.slice(-3).reverse();
  const eventCount = metadata?.eventCount ?? 0;
  const startMilliseconds = metadata?.startTime ? Date.parse(metadata.startTime) : 0;
  const endMilliseconds = metadata?.endTime ? Date.parse(metadata.endTime) : startMilliseconds;
  const playheadMilliseconds = playhead ? Date.parse(playhead) : startMilliseconds;
  const durationSeconds = Math.max(0, (endMilliseconds - startMilliseconds) / 1000);
  const elapsedSeconds = Math.max(
    0,
    Math.min(durationSeconds, (playheadMilliseconds - startMilliseconds) / 1000),
  );
  const replayProgress = durationSeconds > 0
    ? Math.round((elapsedSeconds / durationSeconds) * 1000)
    : 0;
  const replayAvailable = metadata?.available ?? selectedCatalogSession?.available ?? true;
  const liveSession = metadata?.isLive ?? selectedCatalogSession?.isLive ?? false;
  const positionMode = metadata?.positionMode
    ?? selectedCatalogSession?.positionMode
    ?? "timing_estimate";
  const replayControlsEnabled = transport === "stream" && replayAvailable;
  const syncControlsEnabled = replayControlsEnabled && liveSession;
  const localSessionCount = catalogSessions.filter((item) => item.available).length;
  const hasLapTiming = drivers.some(
    (driver) => driver.lap !== null || driver.last_lap !== null,
  );
  const hasCarPositions = drivers.some((driver) => (
    positionMode === "precise_xy"
      ? driver.x !== null && driver.x !== undefined && driver.y !== null && driver.y !== undefined
      : driver.track_position !== null
  ));
  const historicalDownloadReady = Boolean(
    selectedCatalogSession
    && !selectedCatalogSession.isLive
    && selectedCatalogSession.downloadable,
  );

  const chooseSession = (sessionKey: string) => {
    setIsPlaying(false);
    setMetadata(null);
    setSequence(0);
    setDelaySeconds(0);
    setDownloadState("idle");
    setDownloadError(null);
    setSelectedSessionKey(sessionKey);
  };

  const downloadReplay = async () => {
    if (!selectedSessionKey || !historicalDownloadReady) return;
    setDownloadState("downloading");
    setDownloadError(null);
    try {
      const response = await fetch(
        `${apiBase}/api/v1/download?session_key=${encodeURIComponent(selectedSessionKey)}`,
        { method: "POST" },
      );
      const result = await response.json() as {
        detail?: string;
        catalog?: ReplayCatalog;
      };
      if (!response.ok || !result.catalog) {
        throw new Error(result.detail ?? "Replay download failed");
      }
      setCatalog(result.catalog);
      setMetadata(null);
      setDownloadState("idle");
      setLibraryRevision((value) => value + 1);
    } catch (error) {
      setDownloadState("error");
      setDownloadError(error instanceof Error ? error.message : "Replay download failed");
    }
  };

  const seekProgress = (value: number) => {
    if (!metadata?.startTime || !metadata.endTime) return;
    const target = new Date(
      startMilliseconds + ((endMilliseconds - startMilliseconds) * value) / 1000,
    ).toISOString();
    setIsPlaying(false);
    sendReplayCommand({ type: "seek", at: target });
  };

  const togglePlayback = () => {
    if (isPlaying) {
      sendReplayCommand({ type: "pause" });
      setIsPlaying(false);
      return;
    }
    sendReplayCommand({ type: "play", speed: playbackSpeed });
    setIsPlaying(true);
  };

  return (
    <main className="pitwall-shell">
      <header className="topbar">
        <div className="brand" aria-label="Slipstream F1">
          <span className="brand-mark">S</span>
          <span>SLIPSTREAM</span>
          <span className="brand-f1">F1</span>
        </div>
        <div className="session-title">
          <span className="eyebrow">{session.circuit ?? "Circuit"}</span>
          <strong>{session.meeting_name ?? "Unknown meeting"}</strong>
        </div>
        <div className="connection-block">
          <span className={`connection-dot ${transport !== "preview" ? "is-connected" : ""}`} />
          <span>{!replayAvailable ? "Catalog v1" : transport === "stream" ? `Stream v1 · seq ${sequence}` : transport === "rest" ? `REST v1 · seq ${sequence}` : "Replay preview"}</span>
        </div>
      </header>

      <section className="replay-library" aria-label="Historical replay library">
        <div className="library-title">
          <span className="eyebrow">REPLAY LIBRARY</span>
          <strong>Choose a season, weekend, and session</strong>
        </div>
        <label>
          <span>SEASON</span>
          <select
            aria-label="Season"
            value={selectedYear ?? ""}
            disabled={!catalogSessions.length}
            onChange={(event) => {
              const first = catalogSessions.find((item) => item.year === Number(event.target.value));
              if (first) chooseSession(first.sessionKey);
            }}
          >
            {Array.from(new Set(catalogSessions.map((item) => item.year))).sort((a, b) => b - a).map((year) => (
              <option value={year} key={year}>{year}</option>
            ))}
          </select>
        </label>
        <label>
          <span>WEEKEND</span>
          <select
            aria-label="Race weekend"
            value={selectedMeetingKey ?? ""}
            disabled={!meetings.length}
            onChange={(event) => {
              const first = yearSessions.find((item) => item.meetingKey === event.target.value);
              if (first) chooseSession(first.sessionKey);
            }}
          >
            {meetings.map((item) => (
              <option value={item.meetingKey} key={item.meetingKey}>{item.meetingName}</option>
            ))}
          </select>
        </label>
        <label>
          <span>SESSION</span>
          <select
            aria-label="Weekend session"
            value={selectedSessionKey ?? ""}
            disabled={!meetingSessions.length}
            onChange={(event) => chooseSession(event.target.value)}
          >
            {meetingSessions.map((item) => (
              <option value={item.sessionKey} key={item.sessionKey}>
                {item.sessionName}{item.isLive ? " · LIVE" : item.available ? " · LOCAL" : " · NOT DOWNLOADED"}
              </option>
            ))}
          </select>
        </label>
        <span className="library-count">{catalogSessions.length || 1} LISTED · {localSessionCount} LOCAL</span>
      </section>

      {!replayAvailable && (
        <section className={`availability-notice ${liveSession ? "is-live" : ""}`} role="status">
          <div>
            <strong>{liveSession ? "LIVE SESSION" : "SESSION NOT DOWNLOADED"}</strong>
            <span>
              {liveSession
                ? "This event is live, but a live timing source is not connected. The timeline ends at the current time."
                : downloadError ?? (historicalDownloadReady
                  ? "Circuit geometry is ready. Download timing, weather, and race-control data for this session."
                  : "This replay becomes downloadable after the session has finished.")}
            </span>
          </div>
          {!liveSession && historicalDownloadReady && catalog?.downloadsEnabled && (
            <button
              type="button"
              className="download-button"
              onClick={() => void downloadReplay()}
              disabled={downloadState === "downloading"}
            >
              {downloadState === "downloading" ? "DOWNLOADING…" : downloadState === "error" ? "TRY AGAIN" : "DOWNLOAD REPLAY"}
            </button>
          )}
        </section>
      )}

      <section className="session-strip" aria-label="Session status">
        <div><span>SESSION</span><strong>{session.name ?? "—"}</strong></div>
        <div><span>DATE</span><strong>{formatSessionDate(session.started_at)}</strong></div>
        <div><span>LAP</span><strong>{session.lap ?? "—"}<em>/ {session.total_laps ?? "—"}</em></strong></div>
        <div><span>TRACK STATUS</span><strong className={`track-status ${trackStatusClass(session.track_status)}`}><i />{session.track_status ?? "NO TRACK FLAG"}</strong></div>
        <div><span>MODE</span><strong className={liveSession ? "live-label" : ""}>{liveSession ? "● LIVE" : !replayAvailable ? "CATALOG" : isPlaying ? `${playbackSpeed}× PLAY` : "PAUSED"}</strong></div>
        <div><span>TRACK LOCAL</span><strong>{session.local_time?.slice(11, 19) ?? "--:--:--"}</strong></div>
        <div className="session-clock"><span>REPLAY UTC</span><strong>{playhead?.slice(11, 19) ?? "--:--:--"}</strong></div>
      </section>

      <section className="replay-controls" aria-label="Replay controls">
        <button type="button" onClick={() => { setIsPlaying(false); sendReplayCommand({ type: "reset" }); }} disabled={!replayControlsEnabled}>FROM START</button>
        <button type="button" onClick={() => { setIsPlaying(false); sendReplayCommand({ type: "seek_relative", seconds: -30 }); }} disabled={!replayControlsEnabled}>−30 SEC</button>
        <button type="button" className="play-button" onClick={togglePlayback} disabled={!replayControlsEnabled}>{isPlaying ? "PAUSE" : "PLAY"}</button>
        <label>
          <span>SESSION TIMELINE</span>
          <input
            aria-label="Replay position"
            type="range"
            min="0"
            max="1000"
            value={replayProgress}
            onChange={(event) => seekProgress(Number(event.target.value))}
            disabled={!replayControlsEnabled || durationSeconds === 0}
          />
        </label>
        <span className="replay-sequence">{formatDuration(elapsedSeconds)} / {formatDuration(durationSeconds)}</span>
        <button type="button" onClick={() => { setIsPlaying(false); sendReplayCommand({ type: "seek_relative", seconds: 30 }); }} disabled={!replayControlsEnabled}>+30 SEC</button>
        <label className="speed-control">
          <span>SPEED</span>
          <select aria-label="Replay speed" value={playbackSpeed} onChange={(event) => {
            const speed = Number(event.target.value);
            setPlaybackSpeed(speed);
            if (isPlaying) sendReplayCommand({ type: "play", speed });
          }} disabled={!replayControlsEnabled}>
            <option value="1">1×</option>
            <option value="5">5×</option>
            <option value="10">10×</option>
            <option value="30">30×</option>
            <option value="60">60×</option>
            <option value="120">120×</option>
          </select>
        </label>
        {liveSession && (
          <div className="delay-control">
            <span>TV SYNC</span>
            <input
              aria-label="Seconds behind live data"
              type="number"
              min="0"
              step="1"
              inputMode="numeric"
              value={delaySeconds}
              onChange={(event) => setDelaySeconds(Math.max(0, Number(event.target.value) || 0))}
              disabled={!syncControlsEnabled}
              title="Set this viewer's delay behind the newest live data"
            />
            <span className="delay-unit">SEC BEHIND</span>
            <button type="button" onClick={() => sendReplayCommand({ type: "delay", seconds: delaySeconds })} disabled={!syncControlsEnabled}>SYNC</button>
          </div>
        )}
      </section>

      <div className="workspace">
        <section className="timing-panel" aria-label="Timing tower">
          <div className="panel-heading">
            <div><span className="kicker">CLASSIFICATION</span><h1>Timing tower</h1></div>
            <span className="driver-count">{drivers.length} DRIVERS</span>
          </div>
          {replayAvailable && !hasLapTiming && (
            <p className="timing-availability">
              Replay synchronized — awaiting the first completed-lap timing update.
            </p>
          )}
          <div className="timing-table" role="table">
            <div className="timing-header" role="row">
              <span>P</span><span>DRIVER</span><span>INT</span><span>GAP</span><span>TYRE</span><span>AGE</span><span>LAST LAP</span><span>PIT</span>
            </div>
            {drivers.map((driver) => (
              <div className="driver-row" role="row" key={driver.number}>
                <span className="position">{driver.position ?? "—"}</span>
                <span className="driver-cell">
                  <i style={{ backgroundColor: `#${driver.team_colour ?? "77808f"}` }} />
                  <b>{driver.code ?? driver.number}</b>
                  <small>{driver.name?.split(" ").slice(-1)[0] ?? driver.team}</small>
                </span>
                <span className="metric">{driver.position === 1 ? "—" : driver.interval_to_ahead ?? "—"}</span>
                <span className="metric gap">{driver.position === 1 ? "LEADER" : driver.gap_to_leader ?? "—"}</span>
                <span><i className={compoundClass(driver.compound)}>{driver.compound?.[0] ?? "?"}</i></span>
                <span className="metric">{driver.tyre_age ?? "—"}</span>
                <span className="metric lap-time">{driver.last_lap ?? driver.best_lap ?? "—"}</span>
                <span className="metric">{driver.pit_count}</span>
              </div>
            ))}
          </div>
        </section>

        <aside className="insight-rail">
          <section className="map-panel">
            <div className="panel-heading compact">
              <div><span className="kicker">HISTORICAL CIRCUIT</span><h2>{circuit?.name ?? session.circuit ?? "Track map"}</h2></div>
              <span className="map-source">{trackGeometry ? "EXACT OUTLINE" : "UNAVAILABLE"}</span>
            </div>
            <div className="track-map" aria-label={`${circuit?.name ?? session.circuit ?? "Circuit"} historical circuit outline`}>
              {trackGeometry ? (
                <svg className="circuit-svg" viewBox="0 0 1000 650" role="img" aria-label="Historical circuit geometry">
                  <polyline className="circuit-shadow" points={trackGeometry.polyline} />
                  <polyline className="circuit-line" points={trackGeometry.polyline} />
                  <polyline className="circuit-centerline" points={trackGeometry.polyline} />
                  <circle className="start-marker" cx={trackGeometry.points[0].x} cy={trackGeometry.points[0].y} r="8" />
                </svg>
              ) : (
                <p className="map-unavailable">Historical circuit geometry is unavailable for this session.</p>
              )}
              {trackGeometry && positionMode !== "unavailable" && drivers.filter((driver) => (
                positionMode === "precise_xy"
                  ? driver.x !== null && driver.x !== undefined && driver.y !== null && driver.y !== undefined
                  : driver.track_position !== null
              )).map((driver) => {
                const point = positionMode === "precise_xy"
                  ? trackGeometry.project(driver.x ?? 0, driver.y ?? 0)
                  : trackGeometry.pointAt(driver.track_position ?? 0);
                return (
                <span
                  className="car-dot"
                  key={driver.number}
                  style={{ left: `${point.x / 10}%`, top: `${point.y / 6.5}%`, backgroundColor: `#${driver.team_colour ?? "fff"}` }}
                  title={positionMode === "precise_xy"
                    ? `${driver.code}: source historical X/Y sample`
                    : `${driver.code}: timing-derived lap fraction ${driver.track_position?.toFixed(3)}`}
                >
                  {driver.position}
                </span>
                );
              })}
              {trackGeometry && positionMode === "unavailable" && (
                <p className="map-position-note">Car positions unavailable — an enhanced/authenticated position source is not connected.</p>
              )}
              {trackGeometry && positionMode === "timing_estimate" && !hasCarPositions && (
                <p className="map-position-note">Replay synchronized — car markers appear with the first completed-lap timing update.</p>
              )}
              <div className="map-center"><strong>{session.lap ?? "—"}</strong><span>CURRENT LAP</span></div>
            </div>
            <div className="map-legend"><span><i />Circuit geometry: historical</span><span>{positionMode === "precise_xy" ? "Cars: source X/Y" : positionMode === "timing_estimate" ? "Cars: timing-derived" : "Cars: unavailable"}</span></div>
          </section>

          <section className="conditions-panel" aria-label="Track conditions">
            <div className="panel-heading compact">
              <div><span className="kicker">WEATHER FEED</span><h2>Track conditions</h2></div>
              <span className={`condition-badge ${weather?.rainfall === true ? "is-raining" : weather?.rainfall === false ? "" : "is-unavailable"}`}><i />{rainLabel}</span>
            </div>
            <div className="conditions-grid">
              <div><span>TRACK TEMP</span><strong>{weather?.track_temperature?.toFixed(1) ?? "—"}<small>°C</small></strong></div>
              <div><span>AIR TEMP</span><strong>{weather?.air_temperature?.toFixed(1) ?? "—"}<small>°C</small></strong></div>
              <div><span>HUMIDITY</span><strong>{weather?.humidity?.toFixed(0) ?? "—"}<small>%</small></strong></div>
              <div><span>PRESSURE</span><strong>{weather?.pressure?.toFixed(1) ?? "—"}<small>hPa</small></strong></div>
              <div><span>WIND</span><strong>{weather?.wind_speed?.toFixed(1) ?? "—"}<small>m/s</small></strong></div>
              <div><span>DIRECTION</span><strong>{weather?.wind_direction ?? "—"}<small>°</small></strong></div>
              <div className="local-condition-time"><span>TRACK LOCAL TIME</span><strong>{session.local_time?.slice(11, 19) ?? "--:--:--"}<small>{utcOffsetLabel(session.gmt_offset)}</small></strong></div>
            </div>
            <p className="condition-note">{weather?.updated_at ? `Weather updated ${weather.updated_at.slice(11, 19)} UTC. ` : ""}Rain sensor status only; surface moisture and grip are not available from the public feed.</p>
          </section>

          <section className="race-control-panel">
            <div className="panel-heading compact">
              <div><span className="kicker">LATEST</span><h2>Race control</h2></div>
              <span className="message-count">{state.race_control.length}</span>
            </div>
            <div className="message-list">
              {recentMessages.map((message, index) => (
                <article key={`${message.occurred_at}-${index}`}>
                  <time>{message.occurred_at.slice(11, 19) || message.occurred_at}</time>
                  <div><span>{message.flag ?? message.category}</span><p>{message.message}</p></div>
                </article>
              ))}
            </div>
          </section>
        </aside>
      </div>

      <footer className="statusbar">
        <span>Slipstream Core</span><span>Canonical RaceState v1</span><span>{eventCount.toLocaleString()} source events</span><span>One upstream · many views</span>
      </footer>
    </main>
  );
}
