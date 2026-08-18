import * as Tooltip from '@radix-ui/react-tooltip';
import type { ButtonHTMLAttributes, ComponentPropsWithoutRef, ReactNode } from 'react';

export function PaperPanel({ children, tone = 'default', className = '', ...props }: ComponentPropsWithoutRef<'section'> & { tone?: 'default' | 'focus' | 'archive' | 'floating' }) {
  return <section {...props} className={`paper-panel-ui paper-panel-${tone} ${className}`}>{children}</section>;
}

export function SectionHeading({ index, children, note }: { index?: string; children: ReactNode; note?: string }) {
  return <header className="section-heading">{index && <small>{index}</small>}<h2>{children}</h2>{note && <span>{note}</span>}</header>;
}

export function StatusMark({ tone = 'neutral', children }: { tone?: 'neutral' | 'action' | 'warning' | 'danger' | 'complete'; children: ReactNode }) {
  return <span className={`status-mark status-mark-${tone}`}>{children}</span>;
}

export function ActionSealButton({ priority = 'secondary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { priority?: 'primary' | 'secondary' | 'danger' | 'ghost' }) {
  return <button {...props} className={`action-seal action-seal-${priority} ${className}`.trim()} />;
}

export function ListRow({ title, meta, status, children }: { title: ReactNode; meta?: ReactNode; status?: ReactNode; children?: ReactNode }) {
  return <article className="ledger-row"><div><strong>{title}</strong>{meta && <small>{meta}</small>}</div>{status && <div>{status}</div>}{children}</article>;
}

export function MetricChip({ icon, label, value, trend }: { icon: ReactNode; label: string; value: number | string; trend?: 'up' | 'down' | 'steady' }) {
  return <Tooltip.Root delayDuration={240}><Tooltip.Trigger asChild><button type="button" className="metric-chip" aria-label={`${label}：${value}`}>{icon}<strong>{value}</strong>{trend && <i className={`metric-trend metric-trend-${trend}`} aria-hidden="true" />}</button></Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="game-tooltip" sideOffset={7}>{label}：{value}<Tooltip.Arrow className="game-tooltip-arrow" /></Tooltip.Content></Tooltip.Portal></Tooltip.Root>;
}

export function MetricLedger({ children }: { children: ReactNode }) {
  return <div className="metric-ledger" aria-label="国政指标"><Tooltip.Provider>{children}</Tooltip.Provider></div>;
}

export function AppFrame({ title, eyebrow, back, actions, children, className = '' }: { title: ReactNode; eyebrow?: ReactNode; back?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return <div className={`app-frame ${className}`.trim()}><header className="app-frame-header">{back && <div className="app-frame-back">{back}</div>}<div className="app-frame-title">{eyebrow && <small>{eyebrow}</small>}<h1>{title}</h1></div>{actions && <div className="app-frame-actions">{actions}</div>}</header>{children}</div>;
}
