export type AvailabilityStatus = "available" | "unavailable" | "unsupported" | "stale";

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
    session_kind: SessionKind;
    layout_family: LayoutFamily;
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
  analytics?: AnalyticsSnapshot;
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

export type LapObservation = {
  sequence: number;
  occurredAt: string;
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
  pit_occurred_at: string | null;
  previous_compound: string | null;
  new_compound: string | null;
  stop_duration: number | null;
  pit_lane_duration: number | null;
  quality: "representative" | "contaminated" | "unknown";
  contamination_reasons: string[];
};

export type DriverHistory = {
  v: 1;
  sessionKey: string;
  driverNumber: string;
  available: boolean;
  observations: LapObservation[];
  pitEvents: PitEvent[];
};

export type PitEvent = {
  sequence: number;
  occurredAt: string;
  driverNumber: string;
  lap: number;
  previousCompound: string | null;
  newCompound: string | null;
  stopDuration: number | null;
  pitLaneDuration: number | null;
};

export type SessionKind = "practice_1" | "practice_2" | "practice_3" | "qualifying" | "sprint_qualifying" | "sprint" | "race" | "unknown";
export type LayoutFamily = "practice" | "qualifying" | "race" | "unsupported";

export type AnalyticsMetric<T = string | number | [number, number]> = {
  value: T | null;
  status: "OBSERVED" | "DERIVED" | "ESTIMATE" | "UNKNOWN";
  unit: string | null;
  evidenceBasis: string[];
  modelVersion: string;
  quality: string | null;
};

export type PaceSample = {
  lap: number;
  rawLapTime: number | null;
  delta: number | null;
  compound: string | null;
  tyreAge: number | null;
  stintNumber: number | null;
  quality: "representative" | "contaminated" | "unknown";
  contaminationReasons: string[];
};

// v2.1 contract vocabulary (single source of truth; mirror Python context_types.py).
export type Disposition = "PIT_EXPECTED" | "TO_FINISH" | "UNKNOWN";
export type WindowState = "ACTIVE" | "WINDOW_PASSED_EXTENDING" | "TO_FINISH" | "RESETTING" | "UNKNOWN" | "FINAL";
export type StrategyValidity = "VALID" | "RESETTING" | "RECALCULATING" | "UNAVAILABLE";
export type StrategyLifecycle = "LIVE" | "RESETTING" | "RECALCULATING" | "FINAL" | "UNAVAILABLE";
export type DryTyreRequirementState = "UNSATISFIED" | "SATISFIED" | "NOT_APPLICABLE" | "UNKNOWN";
export type HistoricalComparability = "NORMAL" | "LIMITED" | "INCOMPATIBLE";

export type HistoricalContext = {
  status: "PRESENT" | "ABSENT";
  season?: number | null;
  circuitId?: string | null;
  comparability?: HistoricalComparability;
  stopDistribution?: Record<string, number>;
  compoundSequences?: string[];
  stintLengths?: unknown;
  sourceNote?: string;
  evidenceCutoff?: string | null;
  targetSessionKey?: string | null;
  reason?: string;
};

export type OfficialPreRaceContext = {
  status: "PRESENT" | "ABSENT";
  source?: string | null;
  publishedAt?: string | null;
  retrievedAt?: string | null;
  sourceUrl?: string | null;
  expectedStopCount?: number | null;
  primarySequence?: string | null;
  alternateSequence?: string | null;
  statedPitWindows?: unknown[];
  caveats?: string[];
  providerVersion?: string | null;
  acquisition?: "MANUAL" | "AUTOMATED";
  targetSessionKey?: string | null;
  reason?: string;
};

export type ProjectionGate = {
  hardValidity: { status: string; violations: number; reason?: string };
  plausibility: { status: string; reason?: string };
  stability: { status: string; reason?: string };
};

export type NetPitLoss = {
  status: "ABSENT" | "NOT_IMPLEMENTED" | "UNKNOWN" | "PRESENT";
  blocks?: string[];
  evidenceBasis?: string[];
};

export type DryTyreRequirement = {
  state: DryTyreRequirementState;
  ruleProfile?: string;
  evidenceBasis?: string[];
};

export type StrategyAnalytics = {
  scope: "RACE" | "DRIVER";
  driverNumber?: string;
  stage: AnalyticsStage;
  changes: string[];
  likelyStopCount: AnalyticsMetric<number>;
  primaryStrategy: AnalyticsMetric<string>;
  alternateStrategy: AnalyticsMetric<string>;
  likelyNextCompound: AnalyticsMetric<string>;
  pitWindow: AnalyticsMetric<[number, number]>;
  tyreStress: AnalyticsMetric<string>;
  degradation: AnalyticsMetric<number>;
  pitLoss: AnalyticsMetric<number>;
  undercutStrength: AnalyticsMetric<string>;
  projectedRejoinPosition: AnalyticsMetric<number>;
  freeStopMargin: AnalyticsMetric<number>;
  weatherRisk: AnalyticsMetric<string>;
  rulesNote: string;
  // v2.1 §11 / §12 / §15: per-driver disposition, window state, validity, and
  // the dry-tyre requirement state. Phase C fills in real values.
  disposition?: Disposition;
  windowState?: WindowState;
  lifecycle?: StrategyLifecycle;
  terminalState?: string | null;
  strategyValidity?: StrategyValidity;
  dryTyreRequirement?: DryTyreRequirementState;
};

export type DriverAnalytics = {
  driverNumber: string;
  ahead: DriverBattleContext | null;
  behind: DriverBattleContext | null;
  pace: {
    definition: string;
    baselineVersion: string;
    samples: PaceSample[];
    currentStintBaseline: number | null;
    // v2.1 §20: SERVER-computed deterministic chart scale (median of |delta|,
    // MAD 3× retention, 0.25s floor). Client renders verbatim.
    scale?: number;
    degradation: AnalyticsMetric<number>;
  };
  pitEvents: PitEvent[];
  strategy: StrategyAnalytics;
  weekendEvidence: {
    lapCount: number;
    representativeLapCount: number;
    compounds: string[];
    status: "available" | "unavailable";
  };
};

export type DriverBattleContext = {
  relationship: "ahead" | "behind";
  driverNumber: string;
  code: string | null;
  name: string | null;
  position: number | null;
  gapSeconds: number | null;
  status: "OBSERVED" | "UNKNOWN";
};

export type BattleCandidate = {
  aheadDriverNumber: string;
  behindDriverNumber: string;
  score: number;
  gapSeconds: number;
  // v2.1 §15.2: one server-provided gap truth. gapBasis names the source
  // (interval-to-ahead); comparisonState is the eligibility verdict so a
  // non-comparable pair is explained rather than shown as an empty gap.
  gapBasis?: string;
  comparisonState?: "COMPARABLE" | "NOT_COMPARABLE";
  factors: Array<{ name: string; value: number | null; weight: number }>;
};

export type AnalyticsStage = "BASELINE_AVAILABLE" | "WEEKEND_MODEL_READY" | "LIVE_OUTLOOK";

export type AnalyticsSnapshot = {
  v: 1;
  type: "analytics.snapshot";
  schemaVersion: 1;
  modelVersion: string;
  sessionKey: string;
  sessionKind: SessionKind;
  layoutFamily: LayoutFamily;
  sequence: number;
  asOf: string | null;
  stage: AnalyticsStage;
  // v2.1 §11: race-level strategy validity (SC/VSC/Red resets this).
  strategyValidity?: StrategyValidity;
  strategyLifecycle?: StrategyLifecycle;
  // v2.1 §17.1: NetPitLoss is a derived metric; until it exists, the fields
  // that depend on it are suppressed (freeStopMargin, projectedRejoinPosition,
  // quantified undercut).
  netPitLoss?: NetPitLoss;
  // v2.1 §8.2 / §9 / §10: gate provenance for the published window.
  projectionGate?: ProjectionGate;
  // v2.1 §18: field distributions over active runners at the cursor.
  activeRunnerCount?: number;
  startingTyreDistribution?: Record<string, number>;
  stopDistribution?: Record<string, number>;
  observedSequences?: string[];
  // v2.1 §5.2 / §5.3: attributed, target-session-owned context artifacts.
  historical?: HistoricalContext;
  officialPreRace?: OfficialPreRaceContext;
  // v2.1 §5.5 / §26: data-ownership contract (target-session-owned,
  // session-scoped, cursor-keyed; M4 downstream deletion is a non-goal).
  dataOwnership: {
    owner: "target_session";
    sessionScoped: boolean;
    cursorKeyed: boolean;
    sessionKey: string;
    adminDeletion: { status: string; evidenceBasis: string[] };
    evidenceBasis: string[];
  };
  sportingRules: {
    profileVersion: string;
    mandatoryPitStops: number | null;
    dryCompoundObligation: string;
    evidenceBasis: string[];
    // v2.1 §15: rule-derived dry-tyre obligation (per-driver state in Phase C).
    dryTyreRequirement?: {
      ruleProfile?: string;
      perDriverState?: DryTyreRequirementState;
      evidenceBasis?: string[];
    };
  };
  context: {
    status: "missing" | "preparing" | "ready" | "unavailable";
    meetingKey: string;
    generatedAt: string | null;
    evidenceCutoff: string;
    modelVersion: string | null;
    sessionCount: number;
    externalIntelligence: { status: "disabled" | "available" | "unavailable"; items: unknown[] };
    error: string | null;
  };
  pitLoss: AnalyticsMetric<number>;
  raceStrategy: StrategyAnalytics;
  drivers: Record<string, DriverAnalytics>;
  battle: {
    recommended: BattleCandidate | null;
    candidates: BattleCandidate[];
    // v2.1 §20 / invariant 6: server-stabilized recommendation (session-scoped,
    // cursor-keyed hysteresis owned by AnalyticsService). The client renders
    // this verbatim and must NOT recompute it locally.
    stabilizedRecommended: BattleCandidate | null;
    heldRecommendation: BattleCandidate | null;
    hysteresis: { minimumHoldSeconds: number; switchMargin: number; owner?: string; sessionScoped?: boolean; cursorKeyed?: boolean };
    modelVersion: string;
  };
};

export type CatalogSession = {
  sessionKey: string;
  year: number;
  meetingKey: string;
  meetingName: string;
  sessionName: string;
  sessionType: string;
  sessionKind: SessionKind;
  layoutFamily: LayoutFamily;
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
    session_kind: "unknown", layout_family: "unsupported",
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
