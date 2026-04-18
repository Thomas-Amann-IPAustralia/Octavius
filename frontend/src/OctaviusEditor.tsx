import React, { useCallback, useEffect, useState } from 'react'
import { Streamlit, withStreamlitConnection, ComponentProps } from 'streamlit-component-lib'
import { FileText, Sliders } from 'lucide-react'
import type { Finding, PanelTab, ComponentArgs } from './types'
import { useOctaviusState } from './hooks/useOctaviusState'
import { StatsHeader } from './components/StatsHeader'
import { TextEditor } from './components/TextEditor'
import { FindingsPanel } from './components/FindingsPanel'
import { RulesPanel } from './components/RulesPanel'

const OctaviusEditor: React.FC<ComponentProps> = (props) => {
  const { text = '', findings = [], rules = [] } = (props.args ?? {}) as ComponentArgs

  const state = useOctaviusState(text, findings, rules)
  const { handleFindingClick: stateHandleFindingClick } = state

  const [activeTab, setActiveTab] = useState<PanelTab>('issues')

  // Adjust Streamlit frame height to fit content
  useEffect(() => { Streamlit.setFrameHeight() })

  // Switch to issues tab when a finding is clicked
  const handleFindingClick = useCallback((finding: Finding) => {
    stateHandleFindingClick(finding)
    setActiveTab('issues')
  }, [stateHandleFindingClick])

  const TABS: { id: PanelTab; label: string; icon: React.ReactNode; count?: number }[] = [
    {
      id: 'issues',
      label: 'Issues',
      icon: <FileText size={13} />,
      count: state.effectiveFindings.length,
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
      <StatsHeader
        findings={state.effectiveFindings}
        isAnalysing={state.isAnalysing}
        onAnalyse={state.handleAnalyse}
      />

      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 420 }}>

        {/* Left: Text editor */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-slate-200 bg-white">
          <TextEditor
            text={state.localText}
            findings={state.effectiveFindings}
            activeId={state.activeFindingId}
            onTextChange={state.handleTextChange}
            onFindingClick={handleFindingClick}
          />
        </div>

        {/* Right: Findings + Rules panel */}
        <div className="w-80 flex-shrink-0 flex flex-col bg-white overflow-hidden">
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

          <div className="flex-1 overflow-hidden">
            {activeTab === 'issues' ? (
              <FindingsPanel
                findings={state.effectiveFindings}
                activeId={state.activeFindingId}
                onFindingClick={handleFindingClick}
              />
            ) : (
              <RulesPanel
                rules={rules}
                activeRuleIds={state.activeRuleIds}
                onToggle={state.handleToggleRule}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default withStreamlitConnection(OctaviusEditor)
