import mark from "../../assets/brand/mark-192.png";

export function BrandMark({ className = "" }: { className?: string }) {
  return <span className={`brand-mark ${className}`} aria-hidden="true"><img src={mark} alt="" /></span>;
}

export function Kerb({ className = "" }: { className?: string }) {
  return <div className={`kerb-progress ${className}`} aria-hidden="true" />;
}

export function BrandOpening({ phase }: { phase: string }) {
  return <section className="brand-opening" role="status"><BrandMark className="brand-mark-opening" /><strong>SLIPSTREAM</strong><span>{phase}</span><Kerb /></section>;
}
