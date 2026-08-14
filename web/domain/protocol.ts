export type AvailabilityStatus = "available" | "unavailable" | "unsupported" | "stale";

export type LapQuality = "representative" | "contaminated" | "unknown";

export type LapObservation = {
  lap: number;
  started_at: string;
  duration: number | null;
  sector_1: number | null;
  sector_2: number | null;
  sector_3: number | null;
  compound: string | null;
  stint_number: number | null;
  tyre_age: number | null;
  pit_in: boolean | null;
  pit_out: boolean | null;
  quality: LapQuality;
  contamination_reasons: string[];
};

export type Driver = {
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
  x: number | null;
  y: number | null;
  z: number | null;
  sector_1: number | null;
  sector_2: number | null;
  sector_3: number | null;
  lap_history: LapObservation[];
  availability: Record<string, AvailabilityStatus>;
  status: string;
};

export type RaceState = {
  schema_version: number;
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
  circuit: {
    key: string | null;
    name: string | null;
    year: number | null;
    rotation: number | null;
    path: Array<[number, number]>;
    source: string | null;
    availability: Record<string, AvailabilityStatus>;
  };
  weather: {
    updated_at: string | null;
    air_temperature: number | null;
    track_temperature: number | null;
    humidity: number | null;
    pressure: number | null;
    rainfall: boolean | null;
    wind_speed: number | null;
    wind_direction: number | null;
    availability: Record<string, AvailabilityStatus>;
  };
  drivers: Record<string, Driver>;
  race_control: Array<{
    occurred_at: string;
    category: string;
    message: string;
    flag: string | null;
    scope: string | null;
    driver_number: string | null;
    sector: number | null;
    lap: number | null;
  }>;
};

export type StateEnvelope = {
  v: 1;
  seq: number;
  type: "state.snapshot" | "error";
  sessionTime: string | null;
  sourceTime: string | null;
  playback: { playing: boolean };
  data: RaceState;
  error?: string;
};

export type PositionMode = "precise_xy" | "timing_estimate" | "unavailable";

export type SourceCapabilities = {
  v: 1;
  source: string;
  capabilities: Record<string, boolean>;
  replayAvailable: boolean;
  isLive: boolean;
  positionMode: PositionMode;
};

export type ReplayMetadata = {
  v: 1;
  sessionKey: string;
  eventCount: number;
  startTime: string | null;
  endTime: string | null;
  durationSeconds: number;
  available: boolean;
  isLive: boolean;
  positionMode: PositionMode;
};

export type CatalogSession = {
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
  downloadable: boolean;
  circuitShapeAvailable: boolean;
  positionMode: PositionMode;
};

export type ReplayCatalog = {
  v: 1;
  defaultSessionKey: string;
  downloadsEnabled: boolean;
  sessions: CatalogSession[];
};

export const EMPTY_RACE_STATE: RaceState = {
  schema_version: 1,
  updated_at: null,
  session: {
    key: null, name: null, meeting_name: null, session_type: null,
    circuit: null, location: null, started_at: null, ended_at: null,
    lap: null, total_laps: null, track_status: null, gmt_offset: null,
    local_time: null, status: "UNAVAILABLE",
  },
  circuit: {
    key: null, name: null, year: null, rotation: null, path: [], source: null,
    availability: { path: "unavailable" },
  },
  weather: {
    updated_at: null, air_temperature: null, track_temperature: null,
    humidity: null, pressure: null, rainfall: null, wind_speed: null,
    wind_direction: null, availability: {},
  },
  drivers: {},
  race_control: [],
};

export type ReplayCommand =
  | { type: "snapshot" | "pause" | "step" | "reset" }
  | { type: "play"; speed: number }
  | { type: "seek"; at: string }
  | { type: "seek"; seq: number }
  | { type: "seek_relative"; seconds: number }
  | { type: "delay"; seconds: number };