/**
 * Runtime mutation helpers.
 *
 * NO React, Tiptap, or DOM imports.  Safe in Node.js / headless environments.
 */

import { OctaviusDocument } from './document'
import type { Finding } from '../types'

// ---------------------------------------------------------------------------
// Structural transform — heading sentence case
// ---------------------------------------------------------------------------

/**
 * Convert a heading's text to sentence case.
 *
 * Sentence case: first character uppercase, rest lowercase.
 * Acronyms (2+ uppercase letters) are preserved.
 */
export function toSentenceCase(text: string): string {
  if (!text) return text
  const first = text.charAt(0).toUpperCase()
  const rest = text.slice(1).replace(/\b([A-Z]{2,})\b/g, (m) => m)
    .replace(/\b([A-Z][a-z]*)\b/g, (m) => m.toLowerCase())
  return first + rest
}

// ---------------------------------------------------------------------------
// applyFinding — dispatch to correct mutation kind
// ---------------------------------------------------------------------------

/**
 * Apply a finding to the document and return a new document.
 *
 * Behaviour by mutation_class:
 * - `safe_replace`:     Apply textual replacement at [start_char, end_char].
 * - `requires_rewrite`: Apply user-supplied text at [start_char, end_char].
 * - `human_review`:     No mutation — return doc unchanged.
 * - null / undefined:   No mutation — return doc unchanged.
 *
 * For headings with a sentence-case structural transform, the caller should
 * use `applySentenceCaseHeading` instead.
 */
export function applyFinding(
  doc: OctaviusDocument,
  finding: Finding,
  replacement?: string,
): OctaviusDocument {
  return doc.applyFinding(finding, replacement)
}

/**
 * Apply sentence-case conversion to the heading that contains the given
 * plain-text offset range.
 *
 * This is the structural transform for heading-case findings.  It converts
 * the heading's full text to sentence case, replacing the spanned range
 * with the corrected text.
 */
export function applySentenceCaseHeading(
  doc: OctaviusDocument,
  finding: Finding,
): OctaviusDocument {
  const zone = doc.internalZones.find(
    (z) =>
      z.kind === 'heading' &&
      z.offset <= finding.start_char &&
      z.offset + z.length >= finding.end_char,
  )
  if (!zone) return doc.applyFinding(finding)

  const corrected = toSentenceCase(zone.text)
  if (corrected === zone.text) return doc

  // Replace the full heading text with the sentence-cased version.
  const headingFinding: Finding = {
    ...finding,
    start_char: zone.offset,
    end_char: zone.offset + zone.length,
    mutation_class: 'safe_replace',
    suggestion: corrected,
  }
  return doc.applyFinding(headingFinding, corrected)
}
