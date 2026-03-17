import React from 'react'
import { Sparkles, Play, AlertCircle, AlertTriangle, Info } from 'lucide-react'
import type { Finding } from '../types'

interface Props {
  findings: Finding[]
  isAnalysing: boolean
  onAnalyse: () => void
}

export const StatsHeader: React.FC<Props> = ({ findings, isAnalysing, onAnalyse }) => {
  const errors = findings.filter(f => f.severity === 'error').length
  const warns  = findings.filter(f => f.severity === 'warn').length
  const infos  = findings.filter(f => f.severity === 'info').length
  const total  = findings.length

  return (
    <header className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-white flex-wrap gap-3">
      {/* Logo */}
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm">
          <Sparkles size={14} className="text-white" />
        </div>
        <span className="text-sm font-bold text-slate-800 tracking-tight">Octavius</span>
      </div>

      {/* Stats chips */}
      {total > 0 && (
        <div className="flex items-center gap-2">
          {errors > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-rose-50 text-rose-600 text-xs font-semibold ring-1 ring-rose-200">
              <AlertCircle size={11} />
              {errors}E
            </span>
          )}
          {warns > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 text-amber-600 text-xs font-semibold ring-1 ring-amber-200">
              <AlertTriangle size={11} />
              {warns}W
            </span>
          )}
          {infos > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-violet-50 text-violet-600 text-xs font-semibold ring-1 ring-violet-200">
              <Info size={11} />
              {infos}I
            </span>
          )}
        </div>
      )}

      {/* Analyse button */}
      <button
        onClick={onAnalyse}
        disabled={isAnalysing}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700
          disabled:opacity-60 disabled:cursor-not-allowed
          text-white text-xs font-semibold shadow-sm transition-all duration-150
          active:scale-95"
      >
        <Play size={12} className={isAnalysing ? 'animate-spin' : ''} />
        {isAnalysing ? 'Analysing…' : 'Analyse'}
      </button>
    </header>
  )
}
