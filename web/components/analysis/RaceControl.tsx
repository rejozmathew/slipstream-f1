import type { RaceState } from "../../domain/protocol";
import { Panel } from "../shared/Panel";

export function RaceControl({ messages }: { messages: RaceState["race_control"] }) {
  const recent = messages.slice(-5).reverse();
  return (
    <Panel eyebrow="LATEST" title="Race control" action={<span className="panel-badge">{messages.length}</span>} className="race-control-panel">
      {recent.length === 0 ? <div className="panel-empty">NO MESSAGES AT THIS SESSION TIME</div> : <div className="message-list">
        {recent.map((message, index) => <article key={`${message.occurred_at}-${index}`}>
          <time>{message.occurred_at.slice(11, 19) || message.occurred_at}</time>
          <div><span>{message.flag ?? message.category}</span><p>{message.message}</p></div>
        </article>)}
      </div>}
    </Panel>
  );
}