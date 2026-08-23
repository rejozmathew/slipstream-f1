import { useEffect, useMemo, useRef, useState } from "react";

import { slipstreamApi } from "../api/client";
import { connectReplaySocket, type ReplaySocket } from "../api/replaySocket";
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

const SELECTED_SESSION_STORAGE_KEY = "slipstream.selected-session.v1";

function savedSessionKey(): string | null {
  try {
    return window.localStorage.getItem(SELECTED_SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function saveSessionKey(sessionKey: string) {
  try {
    window.localStorage.setItem(SELECTED_SESSION_STORAGE_KEY, sessionKey);
  } catch {
    // Selection persistence is an enhancement; the current in-memory selection remains authoritative.
  }
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
  const [livePhase, setLivePhase] = useState<LiveProductPhase>("UNAVAILABLE");
  const [playhead, setPlayhead] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [transport, setTransport] = useState<TransportState>("connecting");
  const [commandAvailable, setCommandAvailable] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [downloadState, setDownloadState] = useState<"idle" | "downloading" | "error">("idle");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [libraryRevision, setLibraryRevision] = useState(0);
  const socketRef = useRef<ReplaySocket | null>(null);
  const selectedSessionKeyRef = useRef<string | null>(null);
  const viewingModeRef = useRef<ViewingMode>("replay");

  const selectedCatalogSession = useMemo(
    () => catalog?.sessions.find((item) => item.sessionKey === selectedSessionKey) ?? null,
    [catalog, selectedSessionKey],
  );

  useEffect(() => {
    selectedSessionKeyRef.current = selectedSessionKey;
    viewingModeRef.current = viewingMode;
  }, [selectedSessionKey, viewingMode]);

  useEffect(() => {
    let active = true;
    let initialized = false;
    const refreshCatalog = async () => {
      try {
        const result = await slipstreamApi.catalog();
        if (!active) return;
        setCatalog(result);
        if (!initialized) {
          initialized = true;
          const persistedKey = savedSessionKey();
          const persistedSession = persistedKey
            ? result.sessions.find((item) => item.sessionKey === persistedKey)
            : null;
          const resolvedKey = persistedSession?.sessionKey ?? result.defaultSessionKey;
          const resolvedSession = persistedSession
            ?? result.sessions.find((item) => item.sessionKey === resolvedKey);
          setSelectedSessionKey(resolvedKey);
          setViewingMode(resolvedSession?.liveAvailable ? "live" : "replay");
        } else if (viewingModeRef.current === "live") {
          const currentSession = result.sessions.find(
            (item) => item.sessionKey === selectedSessionKeyRef.current,
          );
          if (currentSession?.replayReady && !currentSession.liveAvailable) {
            setViewingMode("replay");
          }
        }
        setConnectionError(null);
      } catch (error) {
        if (!active) return;
        setTransport("disconnected");
        setConnectionError(error instanceof Error ? error.message : "Slipstream service unavailable");
      }
    };
    void refreshCatalog();
    const timer = window.setInterval(() => void refreshCatalog(), 15_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selectedSessionKey) return;
    let active = true;
    let pollTimer: number | undefined;
    let socket: ReplaySocket | null = null;

    const applyEnvelope = (envelope: StateEnvelope) => {
      if (!active) return;
      setState(envelope.data);
      setStateHistory((current) => current.at(-1)?.updated_at === envelope.data.updated_at ? current : [...current, envelope.data].slice(-90));
      setSequence(envelope.seq);
      setPlayhead(envelope.sessionTime ?? envelope.data.updated_at);
      setIsPlaying(viewingMode === "replay" && (envelope.playback?.playing ?? false));
      if (viewingMode === "live") {
        setLiveStatus(envelope.live?.status ?? "UNAVAILABLE");
        setLivePhase(envelope.live?.phase ?? "UNAVAILABLE");
        if (envelope.mode === "replay" && envelope.handoff === "REPLAY_READY") {
          setViewingMode("replay");
        }
      }
      if (envelope.analytics) {
        setAnalytics(envelope.analytics);
      }
    };

    const refreshState = async () => {
      try {
        const envelope = await slipstreamApi.state(selectedSessionKey, viewingMode);
        applyEnvelope(envelope);
        if (active) {
          setTransport("rest");
          setConnectionError(null);
        }
      } catch (error) {
        if (!active) return;
        setTransport("disconnected");
        setConnectionError(error instanceof Error ? error.message : "State unavailable");
      }
    };

    const startPolling = () => {
      if (pollTimer !== undefined) return;
      void refreshState();
      pollTimer = window.setInterval(() => void refreshState(), 3000);
    };

    const bootstrap = async () => {
      let envelope: StateEnvelope;
      try {
        // Canonical state is the bootstrap authority. Auxiliary metadata must
        // never blank a valid Live or Replay state.
        envelope = await slipstreamApi.state(selectedSessionKey, viewingMode);
      } catch (error) {
        if (!active) return;
        setTransport("disconnected");
        setConnectionError(error instanceof Error ? error.message : "State unavailable");
        return;
      }
      if (!active) return;
      applyEnvelope(envelope);
      setTransport("rest");
      setConnectionError(null);

      if (viewingMode === "replay" && !envelope.analytics) {
        void slipstreamApi.analytics(selectedSessionKey, envelope.seq).then((result) => {
          if (active) setAnalytics(result);
        }).catch(() => {
          // Factual replay remains usable when analytics are unavailable.
        });
      }

      const [replayResult, capabilityResult] = await Promise.allSettled([
        slipstreamApi.replay(selectedSessionKey),
        slipstreamApi.capabilities(selectedSessionKey),
      ]);
      if (!active) return;
      const replay = replayResult.status === "fulfilled" ? replayResult.value : null;
      const sourceCapabilities = capabilityResult.status === "fulfilled" ? capabilityResult.value : null;
      if (replay) setMetadata(replay);
      if (sourceCapabilities) setCapabilities(sourceCapabilities);

      const streamAvailable = viewingMode === "live"
        ? replay?.liveAvailable ?? sourceCapabilities?.liveAvailable ?? false
        : replay?.replayAvailable ?? sourceCapabilities?.replayAvailable ?? false;
      if (!streamAvailable) {
        setCommandAvailable(false);
        startPolling();
        return;
      }
      socket = connectReplaySocket(slipstreamApi.streamUrl(selectedSessionKey, viewingMode), {
        onOpen: () => {
          if (!active) return;
          setTransport("stream");
          setCommandAvailable(true);
          setConnectionError(null);
          if (pollTimer !== undefined) {
            window.clearInterval(pollTimer);
            pollTimer = undefined;
          }
        },
        onSnapshot: applyEnvelope,
        onClose: () => {
          if (!active) return;
          setIsPlaying(false);
          setCommandAvailable(false);
          startPolling();
        },
      });
      socketRef.current = socket;
    };
    void bootstrap();

    return () => {
      active = false;
      socket?.close();
      if (socketRef.current === socket) socketRef.current = null;
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
    };
  }, [selectedSessionKey, viewingMode, libraryRevision]);

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
    setStateHistory([]);
    setSequence(0);
    setPlayhead(null);
    setIsPlaying(false);
  };

  const chooseSession = (sessionKey: string, mode?: ViewingMode) => {
    const selected = catalog?.sessions.find((item) => item.sessionKey === sessionKey);
    saveSessionKey(sessionKey);
    resetSessionView();
    setSelectedSessionKey(sessionKey);
    setViewingMode(mode ?? (selected?.liveAvailable ? "live" : "replay"));
    setLiveStatus(selected?.liveStatus ?? "OFFLINE");
    setLivePhase(selected?.livePhase ?? "UNAVAILABLE");
  };

  const goLive = () => {
    if (!catalog?.liveSessionKey) return;
    chooseSession(catalog.liveSessionKey, "live");
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
      setCatalog(result.catalog);
      setDownloadState("idle");
      resetSessionView();
      setViewingMode("replay");
      setLibraryRevision((value) => value + 1);
    } catch (error) {
      setDownloadState("error");
      setDownloadError(error instanceof Error ? error.message : "Replay download failed");
    }
  };

  const sendReplayCommand = (command: ReplayCommand) =>
    commandAvailable && socketRef.current?.send(command) === true;

  useEffect(() => {
    if (viewingMode !== "replay" || !selectedSessionKey || analytics?.context.status !== "preparing") return;
    let active = true;
    const timer = window.setInterval(() => {
      void slipstreamApi.analytics(selectedSessionKey, sequence).then((result) => {
        if (active) setAnalytics(result);
      }).catch(() => {
        // Keep the last truthful context status while replay remains usable.
      });
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [analytics?.context.status, selectedSessionKey, sequence, viewingMode]);

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
    playhead,
    isPlaying,
    transport,
    connectionError,
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
