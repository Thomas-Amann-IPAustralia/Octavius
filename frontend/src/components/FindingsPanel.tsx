import React, { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import type { Finding, SeverityFilter } from '../types'
import { FindingCard } from './FindingCard'

interface Props {
  findings: Finding[]
  activeId: string | null
  onFindingClick: (finding: Finding) => void
  onApply?: (finding: Finding, replacement?: string) => void
  onAcknowledge?: (finding: Finding) => void
  acknowledged?: Set<string>
}

const FILTERS: { label: string; value: SeverityFilter }[] = [
  { label: 'All',   value: 'all'   },
  { label: 'Error', value: 'error' },
  { label: 'Warn',  value: 'warn'  },
  { label: 'Info',  value: 'info'  },
]

export const FindingsPanel: React.FC<Props> = ({
  findings, activeId, onFindingClick,
  onApply, onAcknowledge, acknowledged = new Set(),
}) => {
  const [filter, setFilter] = useState<SeverityFilter>('all')

  const visible = filter === 'all' ? findings : findings.filter(f => f.severity === filter)

  return (
    <div className="flex flex-col h-full">
      {/* Filter pills */}
      <div className="flex items-center gap-1.5 px-4 py-3 border-b border-slate-100 flex-wrap">
        {FILTERS.map(({ label, value }) => {
          const count = value === 'all' ? findings.length : findings.filter(f => f.severity === value).length
          const isActive = filter === value
          return (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-150
                ${isActive
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                }`}
            >
              {label}
              {count > 0 && (
                <span className={`ml-1 ${isActive ? 'opacity-80' : 'opacity-60'}`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Cards list */}
      <div className="flex-1 overflow-y-auto custom-scroll p-4 space-y-3">
        {visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <CheckCircle2 size={36} className="text-emerald-300 mb-3" />
            <p className="text-sm font-medium text-slate-500">
              {findings.length === 0 ? 'No issues found' : 'No issues for this filter'}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {findings.length === 0
                ? 'Type or paste text to analyse'
                : `${findings.length} issue${findings.length > 1 ? 's' : ''} hidden by filter`}
            </p>
          </div>
        ) : (
          visible.map((f, i) => (
            <FindingCard
              key={`${f.rule_id}-${f.start_char}`}
              finding={f}
              index={i}
              isActive={f.rule_id === activeId}
              onClick={() => onFindingClick(f)}
              onApply={onApply}
              onAcknowledge={onAcknowledge}
              acknowledged={acknowledged.has(`${f.rule_id}-${f.start_char}`)}
            />
          ))
        )}
      </div>
    </div>
  )
}
