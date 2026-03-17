import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { Finding } from '../types'
import { SeverityBadge } from './SeverityBadge'

interface Position { top: number; left: number }

interface Props {
  finding: Finding
  anchorEl: HTMLElement | null
}

export const Tooltip: React.FC<Props> = ({ finding, anchorEl }) => {
  const [pos, setPos] = useState<Position | null>(null)

  useEffect(() => {
    if (!anchorEl) { setPos(null); return }

    const rect = anchorEl.getBoundingClientRect()
    const TOOLTIP_WIDTH = 280
    const TOOLTIP_OFFSET = 8

    let left = rect.left
    // Keep tooltip within viewport
    if (left + TOOLTIP_WIDTH > window.innerWidth - 8) {
      left = window.innerWidth - TOOLTIP_WIDTH - 8
    }

    setPos({
      top: rect.bottom + TOOLTIP_OFFSET + window.scrollY,
      left: Math.max(8, left + window.scrollX),
    })
  }, [anchorEl])

  if (!pos || !anchorEl) return null

  return createPortal(
    <div
      className="octavius-tooltip"
      style={{ top: pos.top, left: pos.left, width: 280 }}
    >
      <div className="bg-white rounded-xl shadow-lg ring-1 ring-black/10 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          <span className="text-[10px] font-mono text-slate-400 truncate">
            {finding.rule_id}
          </span>
        </div>
        <p className="text-xs text-slate-700 leading-relaxed">{finding.message}</p>
        {finding.suggestion && (
          <p className="text-xs text-violet-600 leading-relaxed border-t border-violet-100 pt-2">
            {finding.suggestion}
          </p>
        )}
      </div>
    </div>,
    document.body
  )
}
