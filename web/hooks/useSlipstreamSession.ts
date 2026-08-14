import { useEffect, useMemo, useRef, useState } from "react";

import { slipstreamApi } from "../api/client";
import { connectReplaySocket, type ReplaySocket } from "../api/replaySocket";
import {
  EMPTY_RACE_STATE,
  type RaceState,
  type ReplayCatalog,
  type ReplayCommand,
  type ReplayMetadata,
  type SourceCapabilities,
  type StateEnvelope,
} from "../domain/protocol";

export type TransportState = "connecting" | "stream" | "rest" | "disconnected";

export function useSlipstreamSession() {
  const [state, setState] = useState<RaceState>(EMPTY_RACE_STATE);
  const [stateHistory, setStateHistory] = useState<RaceState[]>([]);
  const [sequence, setSequence] = useState(0);
  const [metadata, setMetadata] = useState<ReplayMetadata | null>(null);
  const [capabilities, setCapabilities] = useState<SourceCapabilities | null>(null);
  const [catalog, setCatalog] = useState<ReplayCatalog | null>(null);
  const [selectedSessionKey, setSelectedSessionKey] = useState<string | null>(null);
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
    void slipstreamApi.catalog()
      .then((result) => {
        if (!active) return;
        setCatalog(result);
        setSelectedSessionKey((current) => current ?? result.defaultSessionKey);
        setConnectionError(null);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setTransport("disconnected");
        setConnectionError(error instanceof Error ? error.message : "Slipstream service unavailable");
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedSessionKey || !selectedCatalogSession) return;
    let active = true;
    let pollTimer: number | undefined;
    let socket: ReplaySocket | null = null;

    const applyEnvelope = (envelope: StateEnvelope) => {
      if (!active) return;
      setState(envelope.data);
      setStateHistory((current) => current.at(-1)?.updated_at === envelope.data.updated_at ? current : [...current, envelope.data].slice(-90));
      setSequence(envelope.seq);
      setPlayhead(envelope.sessionTime ?? envelope.data.updated_at);
      setIsPlaying(envelope.playback?.playing ?? false);
    };

    const refreshState = async () => {
      try {
        const envelope = await slipstreamApi.state(selectedSessionKey);
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
      slipstreamApi.state(selectedSessionKey),
      slipstreamApi.capabilities(selectedSessionKey),
    ]).then(([replay, envelope, sourceCapabilities]) => {
      if (!active) return;
      setMetadata(replay);
      setCapabilities(sourceCapabilities);
      applyEnvelope(envelope);
      if (!replay.available) {
        setTransport("rest");
        return;
      }
      socket = connectReplaySocket(slipstreamApi.streamUrl(selectedSessionKey), {
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
  }, [selectedSessionKey, selectedCatalogSession, libraryRevision]);

  const chooseSession = (sessionKey: string) => {
    setDownloadState("idle");
    setDownloadError(null);
    setTransport("connecting");
    setCommandAvailable(false);
    setConnectionError(null);
    setMetadata(null);
    setCapabilities(null);
    setState(EMPTY_RACE_STATE);
    setStateHistory([]);
    setSequence(0);
    setPlayhead(null);
    setIsPlaying(false);
    setSelectedSessionKey(sessionKey);
  };

  const downloadReplay = async () => {
    if (!selectedSessionKey) return;
    setDownloadState("downloading");
    setDownloadError(null);
    try {
      const result = await slipstreamApi.download(selectedSessionKey);
      setCatalog(result.catalog);
      setDownloadState("idle");
      setTransport("connecting");
      setCommandAvailable(false);
      setConnectionError(null);
      setMetadata(null);
      setCapabilities(null);
      setState(EMPTY_RACE_STATE);
      setStateHistory([]);
      setSequence(0);
      setPlayhead(null);
      setIsPlaying(false);
      setLibraryRevision((value) => value + 1);
    } catch (error) {
      setDownloadState("error");
      setDownloadError(error instanceof Error ? error.message : "Replay download failed");
    }
  };

  const sendReplayCommand = (command: ReplayCommand) =>
    commandAvailable && socketRef.current?.send(command) === true;

  return {
    state,
    stateHistory,
    sequence,
    metadata,
    capabilities,
    catalog,
    selectedSessionKey,
    selectedCatalogSession,
    playhead,
    isPlaying,
    transport,
    connectionError,
    downloadState,
    downloadError,
    chooseSession,
    downloadReplay,
    commandAvailable,
    sendReplayCommand,
  };
}
