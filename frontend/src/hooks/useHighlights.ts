import { useMemo } from 'react'
import type { Finding, TextSegment } from '../types'

/**
 * Slices `text` into plain and highlighted segments based on `findings`.
 *
 * - Findings are sorted by start_char ascending (engine already does this,
 *   but we sort defensively here).
 * - Overlapping findings: only the first is used; later overlaps are skipped
 *   to avoid corrupted highlight spans.
 */
export function useHighlights(text: string, findings: Finding[]): TextSegment[] {
  return useMemo(() => {
    if (!text) return []
    if (!findings.length) return [{ text, finding: null, index: 0 }]

    const sorted = [...findings].sort((a, b) => a.start_char - b.start_char)
    const segments: TextSegment[] = []
    let cursor = 0
    let idx = 0

    for (const finding of sorted) {
      const start = Math.max(0, Math.min(finding.start_char, text.length))
      const end   = Math.max(start, Math.min(finding.end_char, text.length))

      // Skip if this finding starts before our cursor (overlap with previous)
      if (start < cursor) continue

      // Plain text before this finding
      if (start > cursor) {
        segments.push({ text: text.slice(cursor, start), finding: null, index: idx++ })
      }

      // Highlighted text
      segments.push({ text: text.slice(start, end), finding, index: idx++ })
      cursor = end
    }

    // Remaining plain text after the last finding
    if (cursor < text.length) {
      segments.push({ text: text.slice(cursor), finding: null, index: idx++ })
    }

    return segments
  }, [text, findings])
}
