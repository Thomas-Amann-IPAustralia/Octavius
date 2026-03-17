import React, { useCallback, useEffect, useState } from 'react'
import { Streamlit, withStreamlitConnection, ComponentProps } from 'streamlit-component-lib'
import { FileText, Sliders } from 'lucide-react'
import type { Finding, PanelTab, ComponentArgs } from './types'
import { StatsHeader } from './components/StatsHeader'
import { TextEditor } from './components/TextEditor'
import { FindingsPanel } from './components/FindingsPanel'
import { RulesPanel } from './components/RulesPanel'

type StreamlitValue = { text: string; activeRuleIds: string[] }

const OctaviusEditor: React.FC<ComponentProps> = (props) => {
  const { text = '', findings = [], rules = [] } = (props.args ?? {}) as ComponentArgs

  // Active rule IDs — initialised to all rules enabled
  const [activeRuleIds, setActiveRuleIds] = useState<Set<string>>(
    () => new Set(rules.map((r) => r.id))
  )

  // Keep activeRuleIds in sync if rules list changes (e.g., new rules added)
  useEffect(() => {
    setActiveRuleIds(prev => {
      const next = new Set(prev)
      rules.forEach(r => { if (!next.has(r.id)) next.add(r.id) })
      return next
    })
  }, [rules])

  const [activeTab, setActiveTab] = useState<PanelTab>('issues')
  const [activeFindingId, setActiveFindingId] = useState<string | null>(null)
  const [localText, setLocalText] = useState<string>(text)
  const [isAnalysing, setIsAnalysing] = useState(false)

  // Sync incoming text prop changes
  useEffect(() => { setLocalText(text) }, [text])

  // Adjust Streamlit frame height to fit content
  useEffect(() => { Streamlit.setFrameHeight() })

  const handleTextChange = useCallback((newText: string) => {
    setLocalText(newText)
    // Don't send to Streamlit on every keystroke to avoid excessive re-renders.
    // The Analyse button triggers the actual audit.
  }, [])

  const handleAnalyse = useCallback(() => {
    setIsAnalysing(true)
    const value: StreamlitValue = {
      text: localText,
      activeRuleIds: Array.from(activeRuleIds),
    }
    Streamlit.setComponentValue(value)
    // Reset after short delay (Streamlit will re-render with new findings)
    setTimeout(() => setIsAnalysing(false), 600)
  }, [localText, activeRuleIds])

  const handleFindingClick = useCallback((finding: Finding) => {
    setActiveFindingId(finding.rule_id)
    setActiveTab('issues')
  }, [])

  const handleToggleRule = useCallback((ruleId: string) => {
    setActiveRuleIds(prev => {
      const next = new Set(prev)
      next.has(ruleId) ? next.delete(ruleId) : next.add(ruleId)
      return next
    })
  }, [])

  const TABS: { id: PanelTab; label: string; icon: React.ReactNode; count?: number }[] = [
    {
      id: 'issues',
      label: 'Issues',
      icon: <FileText size={13} />,
      count: findings.length,
    },
    {
      id: 'rules',
      label: 'Rules',
      icon: <Sliders size={13} />,
      count: rules.length,
    },
  ]

  return (
    <div
      className="flex flex-col bg-slate-50 rounded-2xl overflow-hidden border border-slate-200 shadow-sm"
      style={{ fontFamily: '"Plus Jakarta Sans", Inter, system-ui, sans-serif', minHeight: 480 }}
    >
      {/* ── Header ──────────────────────────────────────────────── */}
      <StatsHeader
        findings={findings}
        isAnalysing={isAnalysing}
        onAnalyse={handleAnalyse}
      />

      {/* ── Two-column body ──────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 420 }}>

        {/* Left: Text editor */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-slate-200 bg-white">
          <TextEditor
            text={localText}
            findings={findings}
            activeId={activeFindingId}
            onTextChange={handleTextChange}
            onFindingClick={handleFindingClick}
          />
        </div>

        {/* Right: Findings + Rules panel */}
        <div className="w-80 flex-shrink-0 flex flex-col bg-white overflow-hidden">
          {/* Tab bar */}
          <div className="flex border-b border-slate-100 px-4 pt-2 gap-1">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-t-lg
                  transition-colors duration-150 border-b-2
                  ${activeTab === tab.id
                    ? 'text-brand-700 border-brand-600 bg-brand-50/50'
                    : 'text-slate-500 border-transparent hover:text-slate-700 hover:bg-slate-50'
                  }`}
              >
                {tab.icon}
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] leading-none
                    ${activeTab === tab.id ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500'}`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'issues' ? (
              <FindingsPanel
                findings={findings}
                activeId={activeFindingId}
                onFindingClick={handleFindingClick}
              />
            ) : (
              <RulesPanel
                rules={rules}
                activeRuleIds={activeRuleIds}
                onToggle={handleToggleRule}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default withStreamlitConnection(OctaviusEditor)
