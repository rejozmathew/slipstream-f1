import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { slipstreamApi, type DownloadJob } from "../api/client";
import { connectReplaySocket, type ReplaySocket } from "../api/replaySocket";
import { shouldPollAnalytics } from "../domain/analyticsPolling.mjs";
import {
  EMPTY_RACE_STATE,
  type AnalyticsSnapshot,
  type LiveConnectionStatus,
  type LiveProductPhase,
  type RaceState,
  type ReplayCatalog,
  type ReplayCommand,
  type ReplayMetadata,
  type SourceCapabilities,
  type StateEnvelope,
  type ViewingMode,
} from "../domain/protocol";

export type TransportState = "connecting" | "stream" | "rest" | "disconnected";

const INTENT_STORAGE_KEY = "slipstream.viewing-intent.v2";
const SELECTED_SESSION_STORAGE_KEY = "slipstream.selected-session.v1";

function savedSessionKey(): string | null {
  try {
    return window.localStorage.getItem(SELECTED_SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function savedIntent(): { followLive: boolean; mode: ViewingMode } {
  try {
    const stored = JSON.parse(window.localStorage.getItem(INTENT_STORAGE_KEY) ?? "null");
    if (stored && typeof stored.followLive === "boolean" && ["live", "replay"].includes(stored.mode)) return stored;
  } catch { /* Storage can be unavailable. */ }
  return { followLive: savedSessionKey() === null, mode: "replay" };
}

function saveIntent(sessionKey: string, mode: ViewingMode, followLive: boolean) {
  try {
    window.localStorage.setItem(SELECTED_SESSION_STORAGE_KEY, sessionKey);
    window.localStorage.setItem(INTENT_STORAGE_KEY, JSON.stringify({ mode, followLive }));
  } catch { /* The current in-memory intent remains authoritative. */ }
}

export function useSlipstreamSession() {
  const [state, setState] = useState<RaceState>(EMPTY_RACE_STATE);
  const [analytics, setAnalytics] = useState<AnalyticsSnapshot | null>(null);
  const [stateHistory, setStateHistory] = useState<RaceState[]>([]);
  const [sequence, setSequence] = useState(0);
  const [metadata, setMetadata] = useState<ReplayMetadata | null>(null);
  const [capabilities, setCapabilities] = useState<SourceCapabilities | null>(null);
  const [catalog, setCatalog] = useState<ReplayCatalog | null>(null);
  const [selectedSessionKey, setSelectedSessionKey] = useState<string | null>(null);
  const [viewingMode, setViewingMode] = useState<ViewingMode>("replay");
  const [liveStatus, setLiveStatus] = useState<LiveConnectionStatus>("OFFLINE");
  const [liveDelaySeconds, setLiveDelaySeconds] = useState(0);
  const [livePositionMode, setLivePositionMode] = useState<import("../domain/protocol").PositionMode>("unavailable");
  const [livePhase, setLivePhase] = useState<LiveProductPhase>("UNAVAILABLE");
  const [playhead, setPlayhead] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [transport, setTransport] = useState<TransportState>("connecting");
  const [commandAvailable, setCommandAvailable] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [downloadJobs, setDownloadJobs] = useState<DownloadJob[]>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [downloadState, setDownloadState] = useState<"idle" | "downloading" | "error">("idle");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [libraryRevision, setLibraryRevision] = useState(0);
  const followLiveRef = useRef(savedIntent().followLive);
  const cursorRef = useRef<{ key: string; seq: number; revision: number; replayAvailable: boolean; recordingVersion?: string | null; isHandoff?: boolean } | null>(null);
  const envelopeEpochRef = useRef(0);
  const analyticsVersionRef = useRef<string | null>(null);
  const analyticsEpochRef = useRef(0);
  const pendingPublicationRef = useRef<{ key: string; revision: number } | null>(null);
  const catalogRef = useRef<ReplayCatalog | null>(null);
  const jobStatusesRef = useRef(new Map<string, DownloadJob["status"]>());
  const delayRef = useRef(0);
  const socketRef = useRef<ReplaySocket | null>(null);
  const selectedSessionKeyRef = useRef<string | null>(null);
  const viewingModeRef = useRef<ViewingMode>("replay");
  const livePhaseRef = useRef<LiveProductPhase>("UNAVAILABLE");

  const selectedCatalogSession = useMemo(
    () => catalog?.sessions.find((item) => item.sessionKey === selectedSessionKey) ?? null,
    [catalog, selectedSessionKey],
  );

  const resetSessionView = () => {
    setDownloadState("idle");
    setDownloadError(null);
    setTransport("connecting");
    setCommandAvailable(false);
    setConnectionError(null);
    setMetadata(null);
    setCapabilities(null);
    setState(EMPTY_RACE_STATE);
    setAnalytics(null);
    analyticsVersionRef.current = null;
    analyticsEpochRef.current = 0;
    setStateHistory([]);
    setSequence(0);
    setPlayhead(null);
    setIsPlaying(false);
  };

  const reopenPublishedReplay = useCallback((key: string, version?: string | null, force = false) => {
    const opened = cursorRef.current;
    if (selectedSessionKeyRef.current !== key || viewingModeRef.current !== "replay"
      || opened?.key !== key || pendingPublicationRef.current?.key === key) return;
    if (!force && opened.replayAvailable
      && (!version || version === opened.recordingVersion)) return;
    pendingPublicationRef.current = { key, revision: opened.revision };
    cursorRef.current = null;
    setCommandAvailable(false);
    setIsPlaying(false);
    setTransport("connecting");
    setLibraryRevision((value) => value + 1);
  }, []);

  const acceptCatalog = useCallback((result: ReplayCatalog) => {
    setCatalog(result);
    catalogRef.current = result;
    const published = result.sessions.find((item) => item.sessionKey === selectedSessionKeyRef.current);
    if (published?.available) reopenPublishedReplay(published.sessionKey, published.recordingVersion);
  }, [reopenPublishedReplay]);

  useEffect(() => {
    selectedSessionKeyRef.current = selectedSessionKey;
    viewingModeRef.current = viewingMode;
  }, [selectedSessionKey, viewingMode]);

  useEffect(() => {
    let active = true;
    let initialized = false;
    let pending = false;
    const refreshCatalog = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await slipstreamApi.catalog();
        if (!active) return;
        acceptCatalog(result);
        if (!initialized && result.sessions.length) {
          initialized = true;
          const intent = savedIntent();
          const persistedKey = intent.followLive ? null : savedSessionKey();
          const persistedSession = persistedKey
            ? result.sessions.find((item) => item.sessionKey === persistedKey)
            : null;
          const resolvedKey = persistedSession?.sessionKey ?? result.defaultSessionKey;
          const resolvedSession = persistedSession
            ?? result.sessions.find((item) => item.sessionKey === resolvedKey);
          resetSessionView();
          setSelectedSessionKey(resolvedKey);
          setViewingMode(intent.followLive ? (resolvedSession?.liveAvailable ? "live" : "replay") : intent.mode === "live" && !resolvedSession?.liveAvailable ? "replay" : intent.mode);
        } else if (followLiveRef.current && result.liveSessionKey && (
          viewingModeRef.current !== "live"
          || (result.liveSessionKey !== selectedSessionKeyRef.current
            && livePhaseRef.current === "UNAVAILABLE" && delayRef.current === 0)
        )) {
          resetSessionView();
          cursorRef.current = null;
          setSelectedSessionKey(result.liveSessionKey);
          setViewingMode("live");
        }
        setCatalogError(null);
      } catch (error) {
        if (active) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable");
      } finally { pending = false; }
    };
    void refreshCatalog();
    const timer = window.setInterval(() => void refreshCatalog(), 15_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [acceptCatalog]);

  useEffect(() => {
    if (!selectedSessionKey) return;
    let active = true;
    let retryTimer: number | undefined;
    let deadline: number | undefined;
    let socket: ReplaySocket | null = null;
    let attempt = 0;
    let generation = 0;
    let streamReady = false;
    let fallbackPending = false;
    let analyticsRequested = false;
    let replayAvailable = false;
    let recordingVersion: string | null | undefined;

    // Event counts belong to one recording. A catalog placeholder or a prior
    // download revision cannot supply a cursor for the newly published file.
    const canResumeCursor = () => {
      if (!cursorRef.current) return false;
      if (cursorRef.current.key !== selectedSessionKey) return false;
      if (cursorRef.current.revision !== libraryRevision) return false;
      if (!cursorRef.current.replayAvailable) return false;
      return Boolean(cursorRef.current.recordingVersion);
    };
    const resumeSequence = () => canResumeCursor() ? cursorRef.current?.seq : undefined;
    const resumeVersion = () => canResumeCursor() ? (cursorRef.current?.recordingVersion ?? undefined) : undefined;
    const applyEnvelope = (envelope: StateEnvelope) => {
      if (!active) return;
      envelopeEpochRef.current++;
      const currentEpoch = envelopeEpochRef.current;
      if (envelope.metadata) {
        replayAvailable = envelope.metadata.available;
        recordingVersion = envelope.metadata.recordingVersion;
      }
      if (envelope.handoff === "REPLAY_READY") replayAvailable = true;
      const isHandoff = envelope.handoff === "REPLAY_READY";
      cursorRef.current = {
        key: selectedSessionKey,
        seq: envelope.seq,
        revision: libraryRevision,
        replayAvailable,
        recordingVersion,
        isHandoff,
      };
      if (replayAvailable && pendingPublicationRef.current?.key === selectedSessionKey
        && libraryRevision > pendingPublicationRef.current.revision) pendingPublicationRef.current = null;
      setState(envelope.data);
      setStateHistory((current) => current.at(-1)?.updated_at === envelope.data.updated_at ? current : [...current, envelope.data].slice(-90));
      setSequence(envelope.seq);
      setPlayhead(envelope.sessionTime ?? envelope.data.updated_at);
      setIsPlaying(viewingMode === "replay" && (envelope.playback?.playing ?? false));
      if (envelope.metadata) setMetadata(envelope.metadata);
      if (envelope.capabilities) setCapabilities(envelope.capabilities);
      if (viewingMode === "live") {
        setLiveDelaySeconds(envelope.live?.delaySeconds ?? delayRef.current);
        setLivePositionMode(envelope.live?.positionMode ?? "unavailable");
        setLiveStatus(envelope.live?.status ?? "UNAVAILABLE");
        setLivePhase(envelope.live?.phase ?? "UNAVAILABLE");
        livePhaseRef.current = envelope.live?.phase ?? "UNAVAILABLE";
        if (followLiveRef.current && envelope.live?.nextSessionKey
          && envelope.live.nextSessionKey !== selectedSessionKey) {
          resetSessionView();
          cursorRef.current = null;
          setSelectedSessionKey(envelope.live.nextSessionKey);
        }
        if (envelope.mode === "replay" && envelope.handoff === "REPLAY_READY") {
          const next = followLiveRef.current ? catalogRef.current?.liveSessionKey : null;
          setCommandAvailable(false);
          setTransport("connecting");
          if (next && next !== selectedSessionKey) {
            resetSessionView();
            cursorRef.current = null;
            setSelectedSessionKey(next);
          } else setViewingMode("replay");
        }
      }
      if (envelope.analytics?.sessionKey === selectedSessionKey && envelope.analytics.sequence === envelope.seq) {
        setAnalytics(envelope.analytics);
        analyticsVersionRef.current = recordingVersion ?? null;
        analyticsEpochRef.current = currentEpoch;
      } else {
        setAnalytics((current) => {
          if (current?.sessionKey === selectedSessionKey && current.sequence === envelope.seq && analyticsVersionRef.current === (recordingVersion ?? null)) {
            return current;
          }
          return null;
        });
      }
      if (!envelope.analytics && viewingMode === "replay" && !analyticsRequested) {
        analyticsRequested = true;
        const cursor = envelope.seq;
        const targetKey = selectedSessionKey;
        const targetVersion = recordingVersion ?? null;
        const requestEpoch = currentEpoch;
        void slipstreamApi.analytics(selectedSessionKey, cursor, targetVersion ?? undefined).then((result) => {
          const matchesIdentity = result && result.sessionKey === targetKey && result.sequence === cursor
            && (result.recordingVersion == null || result.recordingVersion === targetVersion);
          const matchesState = cursorRef.current?.key === targetKey && cursorRef.current.seq === cursor
            && (cursorRef.current.recordingVersion ?? null) === targetVersion;
          const matchesEpoch = envelopeEpochRef.current === requestEpoch;
          if (active && matchesIdentity && matchesState && matchesEpoch && requestEpoch >= analyticsEpochRef.current) {
            setAnalytics(result);
            analyticsVersionRef.current = targetVersion;
            analyticsEpochRef.current = envelopeEpochRef.current;
          }
        }).catch(() => { /* Optional context retries on the next snapshot. */ }).finally(() => { analyticsRequested = false; });
      }
    };

    const refreshState = async () => {
      if (fallbackPending || streamReady || !active) return;
      fallbackPending = true;
      const requestGeneration = generation;
      const requestEpoch = envelopeEpochRef.current;
      try {
        const envelope = await slipstreamApi.state(selectedSessionKey, viewingMode, resumeSequence(), delayRef.current, resumeVersion());
        if (!active || streamReady || generation !== requestGeneration || envelopeEpochRef.current !== requestEpoch) return;
        applyEnvelope(envelope);
        setTransport("rest");
        // Keep the stream error visible while controls are disconnected.
      } catch (error) {
        if (active && !streamReady && generation === requestGeneration && envelopeEpochRef.current === requestEpoch) {
          setTransport("disconnected");
          setConnectionError(error instanceof Error ? error.message : "Timing unavailable; retrying");
        }
      } finally { fallbackPending = false; }
    };

    const connect = () => {
      if (!active) return;
      const version = ++generation;
      streamReady = false;
      socket = connectReplaySocket(slipstreamApi.streamUrl(selectedSessionKey, viewingMode, resumeSequence(), delayRef.current, resumeVersion()), {
        onOpen: () => {
          if (!active || version !== generation) return;
          if (viewingMode === "live" && delayRef.current) socket?.send({ type: "delay", seconds: delayRef.current });
        },
        onSnapshot: (envelope) => {
          if (!active || version !== generation) return;
          applyEnvelope(envelope);
          if (envelope.playbackReady && envelope.metadata && envelope.capabilities) streamReady = true;
          if (streamReady) {
            attempt = 0;
            window.clearTimeout(deadline);
            setTransport("stream");
            setCommandAvailable(true);
            setConnectionError(null);
          }
        },
        onError: (error) => {
          if (!active || version !== generation) return;
          setConnectionError(error);
          socket?.close();
        },
        onClose: () => {
          if (!active || version !== generation) return;
          streamReady = false;
          window.clearTimeout(deadline);
          setIsPlaying(false);
          setCommandAvailable(false);
          setConnectionError((current) => current ?? "Timing connection lost; reconnecting");
          void refreshState();
          retryTimer = window.setTimeout(connect, Math.min(10_000, 500 * 2 ** Math.min(attempt++, 5)));
        },
      });
      socketRef.current = socket;
      deadline = window.setTimeout(() => {
        if (active && version === generation && !streamReady) {
          setConnectionError("Timing initialization timed out; retrying");
          socket?.close();
        }
      }, 10_000);
    };
    connect();
    const pollTimer = window.setInterval(() => void refreshState(), 3000);
    return () => {
      active = false;
      socket?.close();
      if (socketRef.current === socket) socketRef.current = null;
      window.clearTimeout(retryTimer);
      window.clearTimeout(deadline);
      window.clearInterval(pollTimer);
    };
  }, [selectedSessionKey, viewingMode, libraryRevision]);

  const chooseSession = (sessionKey: string, mode?: ViewingMode) => {
    const selected = catalog?.sessions.find((item) => item.sessionKey === sessionKey);
    const resolvedMode = mode ?? (selected?.liveAvailable ? "live" : "replay");
    followLiveRef.current = false;
    saveIntent(sessionKey, resolvedMode, false);
    cursorRef.current = null;
    pendingPublicationRef.current = null;
    delayRef.current = 0;
    resetSessionView();
    setSelectedSessionKey(sessionKey);
    setViewingMode(resolvedMode);
    setLibraryRevision((value) => value + 1);
    setLiveStatus(selected?.liveStatus ?? "OFFLINE");
    setLivePhase(selected?.livePhase ?? "UNAVAILABLE");
  };

  const goLive = () => {
    if (!catalog?.liveSessionKey) return;
    chooseSession(catalog.liveSessionKey, "live");
    followLiveRef.current = true;
    saveIntent(catalog.liveSessionKey, "live", true);
  };

  const watchReplay = () => {
    if (!selectedSessionKey) return;
    chooseSession(selectedSessionKey, "replay");
  };

  const downloadReplay = async () => {
    if (!selectedSessionKey) return;
    setDownloadState("downloading");
    setDownloadError(null);
    try {
      const result = await slipstreamApi.download(selectedSessionKey);
      jobStatusesRef.current.set(result.sessionKey, result.status);
      setDownloadJobs((current) => [...current.filter((job) => job.sessionKey !== result.sessionKey), result]);
      if (result.status === "AVAILABLE") {
        setDownloadState("idle");
        reopenPublishedReplay(result.sessionKey);
        void slipstreamApi.catalog().then(acceptCatalog).catch(() => { /* Catalog polling retries. */ });
      }
    } catch (error) {
      setDownloadState("error");
      setDownloadError(error instanceof Error ? error.message : "Replay download failed");
    }
  };

  useEffect(() => {
    let active = true;
    let pending = false;
    const pollJobs = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await slipstreamApi.jobs();
        if (active) {
          setDownloadJobs(result.jobs);
          let catalogChanged = false;
          for (const job of result.jobs) {
            const previous = jobStatusesRef.current.get(job.sessionKey);
            jobStatusesRef.current.set(job.sessionKey, job.status);
            const completed = job.status === "AVAILABLE" && previous != null && previous !== "AVAILABLE";
            catalogChanged ||= job.status === "AVAILABLE" && previous !== "AVAILABLE";
            if (job.sessionKey !== selectedSessionKeyRef.current) continue;
            if (["QUEUED", "DOWNLOADING", "FINALIZING"].includes(job.status)) setDownloadState("downloading");
            else if (job.status === "FAILED") {
              setDownloadState("error");
              setDownloadError(job.error ?? "Replay download failed");
            } else {
              setDownloadState("idle");
              reopenPublishedReplay(job.sessionKey, undefined, completed);
            }
          }
          if (catalogChanged) {
            void slipstreamApi.catalog().then((catalogResult) => {
              if (active) acceptCatalog(catalogResult);
            }).catch((error) => { if (active) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
          }
        }
      } catch { /* Retry server-owned job discovery after connectivity returns. */ }
      finally { pending = false; }
    };
    void pollJobs();
    const timer = window.setInterval(() => void pollJobs(), 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [acceptCatalog, reopenPublishedReplay]);

  const sendReplayCommand = (command: ReplayCommand) => {
    const sent = commandAvailable && socketRef.current?.send(command) === true;
    if (sent && command.type === "delay") delayRef.current = command.seconds;
    if (sent && ["reset", "live"].includes(command.type)) delayRef.current = 0;
    return sent;
  };

  useEffect(() => {
    if (!selectedSessionKey || !shouldPollAnalytics(
      viewingMode,
      selectedSessionKey,
      analytics?.context.status,
      analytics?.publishedStrategy.baseline.status,
    )) return;
    let active = true;
    const timer = window.setInterval(() => {
      const targetKey = selectedSessionKey;
      const targetSeq = sequence;
      const targetVersion = cursorRef.current?.recordingVersion ?? null;
      const requestEpoch = envelopeEpochRef.current;
      void slipstreamApi.analytics(selectedSessionKey, sequence, targetVersion ?? undefined).then((result) => {
        const matchesIdentity = result && result.sessionKey === targetKey && result.sequence === targetSeq
          && (result.recordingVersion == null || result.recordingVersion === targetVersion);
        const matchesState = cursorRef.current?.key === targetKey && cursorRef.current.seq === targetSeq
          && (cursorRef.current.recordingVersion ?? null) === targetVersion;
        const matchesEpoch = envelopeEpochRef.current === requestEpoch;
        if (active && matchesIdentity && matchesState && matchesEpoch && requestEpoch >= analyticsEpochRef.current) {
          setAnalytics(result);
          analyticsVersionRef.current = targetVersion;
          analyticsEpochRef.current = envelopeEpochRef.current;
        }
      }).catch(() => {
        // Keep the last truthful context status while replay remains usable.
      });
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [analytics?.context.status, analytics?.publishedStrategy.baseline.status, selectedSessionKey, sequence, viewingMode]);

  return {
    state,
    analytics,
    stateHistory,
    sequence,
    metadata,
    capabilities,
    catalog,
    selectedSessionKey,
    selectedCatalogSession,
    viewingMode,
    liveStatus,
    livePhase,
    liveDelaySeconds,
    livePositionMode,
    playhead,
    isPlaying,
    transport,
    connectionError: connectionError ?? catalogError,
    downloadJobs,
    downloadState,
    downloadError,
    chooseSession,
    goLive,
    watchReplay,
    downloadReplay,
    commandAvailable,
    sendReplayCommand,
  };
}
