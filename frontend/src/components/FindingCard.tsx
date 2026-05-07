import React, { useEffect, useRef, useState } from 'react'
import { Copy, Check, ChevronRight, Pencil, CheckCheck } from 'lucide-react'
import type { Finding } from '../types'
import { SeverityBadge } from './SeverityBadge'

interface Props {
  finding: Finding
  index: number
  isActive: boolean
  onClick: () => void
  onApply?: (finding: Finding, replacement?: string) => void
  onAcknowledge?: (finding: Finding) => void
  acknowledged?: boolean
}

export const FindingCard: React.FC<Props> = ({
  finding, index, isActive, onClick,
  onApply, onAcknowledge, acknowledged = false,
}) => {
  const ref = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)
  const [rewriteOpen, setRewriteOpen] = useState(false)
  const [rewriteText, setRewriteText] = useState(finding.suggestion ?? '')

  useEffect(() => {
    if (isActive && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [isActive])

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (finding.suggestion) {
      navigator.clipboard.writeText(finding.suggestion).then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      })
    }
  }

  const handleApply = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onApply) onApply(finding)
  }

  const handleRewriteSubmit = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onApply && rewriteText.trim()) {
      onApply(finding, rewriteText.trim())
      setRewriteOpen(false)
    }
  }

  const handleAcknowledge = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onAcknowledge) onAcknowledge(finding)
  }

  const mc = finding.mutation_class

  return (
    <div
      ref={ref}
      className={`finding-card animate-slide-in rounded-xl border bg-white p-4 cursor-pointer
        transition-all duration-150 shadow-card hover:shadow-card-hover
        ${isActive ? 'is-active border-violet-300' : 'border-slate-200'}
        ${acknowledged ? 'opacity-50' : ''}
      `}
      style={{ animationDelay: `${index * 40}ms` }}
      onClick={onClick}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <SeverityBadge severity={finding.severity} />
          <span className="font-mono text-[10px] text-slate-400">{finding.rule_id}</span>
        </div>
        <ChevronRight
          size={14}
          className={`text-slate-300 flex-shrink-0 transition-transform duration-150 ${isActive ? 'rotate-90 text-violet-400' : ''}`}
        />
      </div>

      {/* Message */}
      <p className="text-xs text-slate-700 leading-relaxed">{finding.message}</p>

      {/* Suggestion */}
      {finding.suggestion && (
        <div className="mt-3 flex items-start justify-between gap-2 rounded-lg bg-violet-50 border border-violet-100 px-3 py-2">
          <p className="text-xs text-violet-700 leading-relaxed flex-1">{finding.suggestion}</p>
          <button
            onClick={handleCopy}
            className="flex-shrink-0 text-violet-400 hover:text-violet-600 transition-colors"
            title="Copy suggestion"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
        </div>
      )}

      {/* Rewrite textarea */}
      {rewriteOpen && (
        <div className="mt-2" onClick={(e) => e.stopPropagation()}>
          <textarea
            className="w-full text-xs border border-slate-200 rounded-lg p-2 resize-none focus:outline-none focus:ring-1 focus:ring-brand-400"
            rows={3}
            value={rewriteText}
            onChange={(e) => setRewriteText(e.target.value)}
            placeholder="Enter your rewrite…"
          />
          <div className="flex gap-2 mt-1">
            <button
              onClick={handleRewriteSubmit}
              className="px-2 py-1 text-xs bg-brand-600 text-white rounded hover:bg-brand-700 transition-colors"
            >
              Apply rewrite
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setRewriteOpen(false) }}
              className="px-2 py-1 text-xs text-slate-500 hover:text-slate-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {isActive && !acknowledged && (
        <div className="mt-3 flex gap-2 flex-wrap" onClick={(e) => e.stopPropagation()}>
          {mc === 'safe_replace' && onApply && (
            <button
              onClick={handleApply}
              className="flex items-center gap-1 px-2.5 py-1 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors"
            >
              <Check size={11} /> Apply fix
            </button>
          )}

          {mc === 'requires_rewrite' && onApply && !rewriteOpen && (
            <button
              onClick={(e) => { e.stopPropagation(); setRewriteOpen(true) }}
              className="flex items-center gap-1 px-2.5 py-1 text-xs bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
            >
              <Pencil size={11} /> Rewrite
            </button>
          )}

          {(mc === 'human_review' || mc === null || mc === undefined) && onAcknowledge && (
            <button
              onClick={handleAcknowledge}
              className="flex items-center gap-1 px-2.5 py-1 text-xs bg-slate-200 text-slate-600 rounded-lg hover:bg-slate-300 transition-colors"
            >
              <CheckCheck size={11} /> Acknowledge
            </button>
          )}
        </div>
      )}
    </div>
  )
}
