import { useCallback, useEffect, useRef, useState } from 'react'
import { Streamlit } from 'streamlit-component-lib'
import type { Finding, RuleMeta } from '../types'

type StreamlitValue = { text: string; activeRuleIds: string[] }

const DEBOUNCE_MS = 1000

export interface OctaviusStateHookResult {
  activeRuleIds: Set<string>
  activeFindingId: string | null
  localText: string
  isAnalysing: boolean
  effectiveFindings: Finding[]
  handleTextChange: (newText: string) => void
  handleAnalyse: () => void
  handleFindingClick: (finding: Finding) => void
  handleToggleRule: (ruleId: string) => void
}

export function useOctaviusState(
  text: string,
  findings: Finding[],
  rules: RuleMeta[]
): OctaviusStateHookResult {
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

  const [activeFindingId, setActiveFindingId] = useState<string | null>(null)
  const [localText, setLocalText] = useState<string>(text)
  const [isAnalysing, setIsAnalysing] = useState(false)

  // Track the last text we sent to Python for analysis
  const lastSentTextRef = useRef<string>(text)

  // Sync incoming text prop — only if it matches what we last sent
  // (prevents overwriting user's in-progress edits during round-trip)
  useEffect(() => {
    if (text === lastSentTextRef.current) {
      setLocalText(text)
    }
  }, [text])

  // Debounced auto-analysis: send to Streamlit 1s after typing stops
  useEffect(() => {
    if (!localText.trim() || localText === lastSentTextRef.current) return
    const timer = setTimeout(() => {
      lastSentTextRef.current = localText
      setIsAnalysing(true)
      const value: StreamlitValue = {
        text: localText,
        activeRuleIds: Array.from(activeRuleIds),
      }
      Streamlit.setComponentValue(value)
      setTimeout(() => setIsAnalysing(false), 600)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [localText, activeRuleIds])

  const handleTextChange = useCallback((newText: string) => {
    setLocalText(newText)
  }, [])

  // Manual Analyse button — force immediate analysis
  const handleAnalyse = useCallback(() => {
    lastSentTextRef.current = localText
    setIsAnalysing(true)
    const value: StreamlitValue = {
      text: localText,
      activeRuleIds: Array.from(activeRuleIds),
    }
    Streamlit.setComponentValue(value)
    setTimeout(() => setIsAnalysing(false), 600)
  }, [localText, activeRuleIds])

  const handleFindingClick = useCallback((finding: Finding) => {
    setActiveFindingId(finding.rule_id)
  }, [])

  const handleToggleRule = useCallback((ruleId: string) => {
    setActiveRuleIds(prev => {
      const next = new Set(prev)
      next.has(ruleId) ? next.delete(ruleId) : next.add(ruleId)
      return next
    })
  }, [])

  // Only show findings when text matches what was analyzed (not stale)
  const effectiveFindings = localText === lastSentTextRef.current ? findings : []

  return {
    activeRuleIds,
    activeFindingId,
    localText,
    isAnalysing,
    effectiveFindings,
    handleTextChange,
    handleAnalyse,
    handleFindingClick,
    handleToggleRule,
  }
}
