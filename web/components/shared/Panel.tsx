import type { ReactNode } from "react";

type PanelProps = {
  eyebrow: string;
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
};

export function Panel({ eyebrow, title, action, className = "", children }: PanelProps) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header className="panel-heading">
        <div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>
        {action}
      </header>
      {children}
    </section>
  );
}