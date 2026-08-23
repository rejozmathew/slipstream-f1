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

  const selectedCatalogSession = useMemo(
    () => catalog?.sessions.find((item) => item.sessionKey === selectedSessionKey) ?? null,
    [catalog, selectedSessionKey],
  );

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
          const defaultSession = result.sessions.find((item) => item.sessionKey === result.defaultSessionKey);
          setSelectedSessionKey(result.defaultSessionKey);
          setViewingMode(defaultSession?.liveAvailable ? "live" : "replay");
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

    void Promise.all([
      slipstreamApi.replay(selectedSessionKey),
      slipstreamApi.state(selectedSessionKey, viewingMode),
      slipstreamApi.capabilities(selectedSessionKey),
    ]).then(([replay, envelope, sourceCapabilities]) => {
      if (!active) return;
      setMetadata(replay);
      setCapabilities(sourceCapabilities);
      applyEnvelope(envelope);
      if (viewingMode === "replay" && !envelope.analytics) {
        void slipstreamApi.analytics(selectedSessionKey, envelope.seq).then((result) => {
          if (active) setAnalytics(result);
        }).catch(() => {
          // Factual replay remains usable when analytics are unavailable.
        });
      }
      const streamAvailable = viewingMode === "live" ? replay.liveAvailable : replay.replayAvailable;
      if (!streamAvailable) {
        setTransport("rest");
        setCommandAvailable(false);
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
    }).catch((error: unknown) => {
      if (!active) return;
      setTransport("disconnected");
      setConnectionError(error instanceof Error ? error.message : "Session unavailable");
    });

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
