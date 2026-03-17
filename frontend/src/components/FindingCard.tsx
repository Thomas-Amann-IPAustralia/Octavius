import React, { useEffect, useRef, useState } from 'react'
import { Copy, Check, ChevronRight } from 'lucide-react'
import type { Finding } from '../types'
import { SeverityBadge } from './SeverityBadge'

interface Props {
  finding: Finding
  index: number
  isActive: boolean
  onClick: () => void
}

export const FindingCard: React.FC<Props> = ({ finding, index, isActive, onClick }) => {
  const ref = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)

  // Scroll into view when this card becomes active
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

  return (
    <div
      ref={ref}
      className={`finding-card animate-slide-in rounded-xl border bg-white p-4 cursor-pointer
        transition-all duration-150 shadow-card hover:shadow-card-hover
        ${isActive ? 'is-active border-violet-300' : 'border-slate-200'}
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
    </div>
  )
}
