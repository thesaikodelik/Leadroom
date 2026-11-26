// The Survey Field Book's own marks: trig points for evidence strength, the run
// traverse, and the five-step score ramp. Every mark is drawn from real data.

import { Component, type ReactNode } from 'react'
import { EVIDENCE_TEXT, type EvidenceLevel } from './evidence'

/** A trig point: outline, half or solid by evidence strength. */
export function TrigMark({ level, label }: { level: EvidenceLevel; label?: string }) {
  if (level === 0) return <span className="trig trig-none" aria-hidden="true" />
  const title = label ?? EVIDENCE_TEXT[level]
  return <svg className={`trig trig-${level}`} viewBox="0 0 16 14" role="img" aria-label={title}>
    <title>{title}</title>
    <defs><clipPath id={`trig-half-${level}`}><rect x="0" y="8.6" width="16" height="5.4" /></clipPath></defs>
    <path className="trig-fill" d="M8 1.2 14.8 12.8H1.2Z" clipPath={level === 2 ? `url(#trig-half-${level})` : undefined} />
    <path className="trig-line" d="M8 1.2 14.8 12.8H1.2Z" />
    <circle className="trig-dot" cx="8" cy="8.6" r="1.25" />
  </svg>
}

/** Lead score 0–10 on the numbered five-step evidence ramp. */
export function ScoreRamp({ score, reason }: { score: number; reason?: string }) {
  const step = Math.max(1, Math.min(5, Math.ceil((Number(score) || 0) / 2)))
  return <span className="score-ramp" title={reason || `Score ${score} of 10`}>
    <span className="score-ramp-cells" aria-hidden="true">{[1, 2, 3, 4, 5].map((cell) => <i key={cell} className={cell <= step ? `on ev-${step}` : ''} />)}</span>
    <strong className="num">{score}</strong><span className="sr-only"> out of 10</span>
  </span>
}

export type Station = { key: string; label: string; value: number; of?: number; state: 'done' | 'current' | 'pending'; note?: string }

/** The run drawn as a survey traverse: stations on a line, the current one ringed. */
export function Traverse({ stations, compact = false, label }: { stations: Station[]; compact?: boolean; label: string }) {
  const reached = Math.max(0, stations.findLastIndex((station) => station.state !== 'pending'))
  const progress = stations.length > 1 ? reached / (stations.length - 1) : 0
  return <ol className={`traverse ${compact ? 'traverse-compact' : ''}`} aria-label={label} style={{ ['--traverse-progress' as string]: progress, ['--stations' as string]: stations.length }}>
    {stations.map((station) => <li key={station.key} className={`station station-${station.state}`} aria-current={station.state === 'current' ? 'step' : undefined}>
      <span className="station-mark" aria-hidden="true"><svg viewBox="0 0 16 14"><path d="M8 1.2 14.8 12.8H1.2Z" /></svg></span>
      {!compact && <span className="station-label">{station.label}</span>}
      <span className="station-value num">{station.value}{station.of !== undefined && <small> of {station.of}</small>}</span>
      {compact && <span className="sr-only">{station.label}</span>}
      {!compact && station.note && <span className="station-note">{station.note}</span>}
    </li>)}
  </ol>
}

/** Keeps the page usable when the map cannot load or render. */
export class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <div className="leads-map leads-map-failed" role="status"><strong>The map could not be shown</strong><span>Every lead is still in the list below.</span></div>
    return this.props.children
  }
}
