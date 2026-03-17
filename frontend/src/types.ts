// ── Domain types matching the Python backend schema ──────────────────────────

export type Severity = 'error' | 'warn' | 'info'

export interface Finding {
  start_char: number
  end_char: number
  rule_id: string
  message: string
  severity: Severity
  suggestion: string | null
}

export interface RuleMeta {
  id: string
  title: string
  severity: Severity
  category?: string   // e.g. "Grammar", "Punctuation" — used for grouping
}

// ── Streamlit component args ──────────────────────────────────────────────────

export interface ComponentArgs {
  text: string
  findings: Finding[]
  rules: RuleMeta[]
}

// ── Internal UI state ─────────────────────────────────────────────────────────

export type PanelTab = 'issues' | 'rules'

export type SeverityFilter = 'all' | Severity

// A text segment produced by useHighlights
export interface TextSegment {
  text: string
  finding: Finding | null  // null = plain text
  index: number            // segment index (for keys)
}
