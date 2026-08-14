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
        <div className="panel-title"><h2>{title}</h2><span className="eyebrow">{eyebrow}</span></div>
        {action}
      </header>
      {children}
    </section>
  );
}
