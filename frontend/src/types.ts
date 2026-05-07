// ── Domain types matching the Python backend schema ──────────────────────────

export type Severity = 'error' | 'warn' | 'info'

export type MutationClass = 'safe_replace' | 'requires_rewrite' | 'human_review'

export interface Finding {
  // Position in plain text
  start_char: number
  end_char: number
  /** @deprecated use start_char */
  start?: number
  /** @deprecated use end_char */
  end?: number

  rule_id: string
  message: string
  severity: Severity
  suggestion: string | null
  mutation_class: MutationClass | null

  // Extra metadata from the backend
  taxonomy?: string
  ui_flag?: string
  rule_summary?: string
  source_url?: string
  document_level?: boolean
  grouped_rules?: string[] | null
}

export interface RuleMeta {
  id: string
  title: string
  severity: Severity
  category?: string   // e.g. "Grammar", "Punctuation" — used for grouping
}

// ── Streamlit component args (kept for backward compatibility) ────────────────

export interface ComponentArgs {
  text: string
  findings: Finding[]
  rules: RuleMeta[]
}

// ── Internal UI state ─────────────────────────────────────────────────────────

export type PanelTab = 'issues' | 'rules' | 'outline'

export type SeverityFilter = 'all' | Severity

// A text segment produced by useHighlights (legacy, kept for reference)
export interface TextSegment {
  text: string
  finding: Finding | null  // null = plain text
  index: number            // segment index (for keys)
}

// ── API request/response ──────────────────────────────────────────────────────

export interface Zone {
  kind: string
  text: string
  offset: number
  length: number
  ancestors: string[]
  lintable: boolean
}

export interface CheckRequest {
  text: string
  plain_text?: string
  zones?: Zone[]
  disabled_rule_ids?: string[]
  disabled_taxonomies?: string[]
}
