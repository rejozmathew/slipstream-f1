import type { ReplayCommand, StateEnvelope } from "../domain/protocol";

export type ReplaySocketHandlers = {
  onOpen: () => void;
  onSnapshot: (envelope: StateEnvelope) => void;
  onClose: () => void;
};

export function connectReplaySocket(url: string, handlers: ReplaySocketHandlers) {
  const socket = new WebSocket(url);
  socket.onopen = handlers.onOpen;
  socket.onmessage = (message) => {
    try {
      const envelope = JSON.parse(message.data as string) as StateEnvelope;
      if (envelope.type !== "error") handlers.onSnapshot(envelope);
    } catch {
      // A later state snapshot can recover from one malformed frame.
    }
  };
  socket.onerror = () => socket.close();
  socket.onclose = handlers.onClose;
  return {
    close: () => socket.close(),
    send(command: ReplayCommand) {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(command));
    },
  };
}

export type ReplaySocket = ReturnType<typeof connectReplaySocket>;