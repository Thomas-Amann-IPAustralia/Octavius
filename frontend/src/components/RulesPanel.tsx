import React, { useState, useMemo } from 'react'
import { Search, ChevronDown, ChevronRight, ToggleLeft, ToggleRight, Layers } from 'lucide-react'
import type { RuleMeta, Severity } from '../types'
import { SeverityBadge } from './SeverityBadge'

interface Props {
  rules: RuleMeta[]
  activeRuleIds: Set<string>
  onToggle: (ruleId: string) => void
}

export const RulesPanel: React.FC<Props> = ({ rules, activeRuleIds, onToggle }) => {
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  // Group rules by category
  const groups = useMemo(() => {
    const filtered = rules.filter(r =>
      !query ||
      r.title.toLowerCase().includes(query.toLowerCase()) ||
      r.id.toLowerCase().includes(query.toLowerCase())
    )
    const map = new Map<string, RuleMeta[]>()
    for (const rule of filtered) {
      const cat = rule.category ?? 'General'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(rule)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [rules, query])

  const toggleGroup = (cat: string) => {
    setCollapsed(prev => {
      const next = new Set(prev)
      next.has(cat) ? next.delete(cat) : next.add(cat)
      return next
    })
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="px-4 py-3 border-b border-slate-100">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search rules…"
            className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-slate-200 bg-slate-50
              focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-transparent
              placeholder-slate-400 text-slate-700"
          />
        </div>
      </div>

      {/* Groups */}
      <div className="flex-1 overflow-y-auto custom-scroll p-4 space-y-3">
        {groups.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <Layers size={32} className="text-slate-200 mb-3" />
            <p className="text-sm text-slate-400">No rules match your search</p>
          </div>
        )}

        {groups.map(([category, catRules]) => {
          const isCollapsed = collapsed.has(category)
          const enabledCount = catRules.filter(r => activeRuleIds.has(r.id)).length

          return (
            <div key={category} className="rounded-xl border border-slate-200 overflow-hidden bg-white shadow-card">
              {/* Group header */}
              <button
                onClick={() => toggleGroup(category)}
                className="w-full flex items-center justify-between px-4 py-3
                  hover:bg-slate-50 transition-colors text-left"
              >
                <div className="flex items-center gap-2">
                  {isCollapsed
                    ? <ChevronRight size={14} className="text-slate-400" />
                    : <ChevronDown  size={14} className="text-violet-500" />}
                  <span className="text-xs font-semibold text-slate-700">{category}</span>
                </div>
                <span className="text-[10px] text-slate-400 font-medium">
                  {enabledCount}/{catRules.length} active
                </span>
              </button>

              {/* Rules in group */}
              {!isCollapsed && (
                <div className="border-t border-slate-100 divide-y divide-slate-50">
                  {catRules.map(rule => {
                    const enabled = activeRuleIds.has(rule.id)
                    return (
                      <div
                        key={rule.id}
                        className={`flex items-center justify-between px-4 py-3 transition-colors
                          ${enabled ? 'bg-white' : 'bg-slate-50/50'}`}
                      >
                        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <SeverityBadge severity={rule.severity as Severity} />
                            <span className={`text-xs font-medium truncate ${enabled ? 'text-slate-700' : 'text-slate-400'}`}>
                              {rule.title}
                            </span>
                          </div>
                          <span className="font-mono text-[10px] text-slate-400 mt-0.5">{rule.id}</span>
                        </div>

                        <button
                          onClick={() => onToggle(rule.id)}
                          className={`ml-3 flex-shrink-0 transition-colors ${enabled ? 'text-violet-500 hover:text-violet-700' : 'text-slate-300 hover:text-slate-400'}`}
                          title={enabled ? 'Disable rule' : 'Enable rule'}
                        >
                          {enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
