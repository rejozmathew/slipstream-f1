import type { ReplayMetadata } from "../../domain/protocol";

export function ReplayRecordingNotice({ metadata }: { metadata: ReplayMetadata | null }) {
  if (!metadata?.available || metadata.complete !== false) return null;
  return <section className="replay-recording-notice" role="status">
    <strong>PARTIAL RECORDING</strong>
    <p>Session completion is not recorded. Playback shows only the updates saved in this file; timing can remain unchanged between them.</p>
  </section>;
}
