import React from 'react'
import type { Zone } from '../types'

interface Props {
  zones: Zone[]
  onHeadingClick: (offset: number) => void
}

export const DocumentOutline: React.FC<Props> = ({ zones, onHeadingClick }) => {
  const headings = zones.filter((z) => z.kind === 'heading')

  if (headings.length === 0) {
    return (
      <div className="px-4 py-3 text-xs text-slate-400 italic">
        No headings yet
      </div>
    )
  }

  return (
    <div className="flex flex-col py-1">
      {headings.map((h, i) => {
        // Infer level from the heading's ancestors — level 1 if no ancestor headings,
        // otherwise count heading ancestors + 1.  Fallback to 1.
        const level = Math.min(
          (h.ancestors.filter((a) => a === 'heading').length + 1),
          3
        )
        const indent = (level - 1) * 12

        return (
          <button
            key={i}
            onClick={() => onHeadingClick(h.offset)}
            className="flex items-start gap-1 px-3 py-1 text-left hover:bg-slate-50 transition-colors group w-full"
            style={{ paddingLeft: 12 + indent }}
            title={h.text}
          >
            <span className="text-[10px] text-slate-400 font-mono mt-0.5 flex-shrink-0">
              H{level}
            </span>
            <span className="text-xs text-slate-600 group-hover:text-slate-800 truncate leading-relaxed">
              {h.text}
            </span>
          </button>
        )
      })}
    </div>
  )
}
