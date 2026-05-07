/**
 * Serialisers for the Octavius document runtime.
 *
 * NO React, Tiptap, or DOM imports.  Safe to use in Node.js / headless
 * environments.
 *
 * Offset invariant
 * ----------------
 * For every zone produced by toZones():
 *   plainText.slice(zone.offset, zone.offset + zone.length) === zone.text
 *
 * This is enforced by using a single-pass walk shared by both projections.
 */

import type { Node as PMNode, Mark } from '@tiptap/pm/model'

// ---------------------------------------------------------------------------
// Public Zone type
// ---------------------------------------------------------------------------

export type ZoneKind =
  | 'heading'
  | 'paragraph'
  | 'list_bullet'
  | 'list_numbered'
  | 'table_cell'
  | 'blockquote'
  | 'code_fence'
  | 'inline_code'
  | 'footnote'
  | 'reference_list'

export interface Zone {
  kind: ZoneKind
  text: string
  offset: number  // start position in plainText
  length: number  // character length in plainText
  ancestors: string[]  // outermost → immediate parent kind
  lintable: boolean
}

// Internal zone extended with ProseMirror position for mutation support.
export interface InternalZone extends Zone {
  pmStart: number  // PM position of zone.text[0]
  pmEnd: number    // PM position of zone.text[zone.text.length-1] + 1
}

// ---------------------------------------------------------------------------
// Internal serialise state
// ---------------------------------------------------------------------------

interface SerialiseState {
  text: string
  zones: InternalZone[]
}

// ---------------------------------------------------------------------------
// Zone kind helpers
// ---------------------------------------------------------------------------

const NON_LINTABLE_KINDS = new Set<ZoneKind>(['code_fence', 'inline_code'])

function lintableKind(kind: ZoneKind): boolean {
  return !NON_LINTABLE_KINDS.has(kind)
}

/** Resolve the lintable zone kind for a paragraph based on its ancestors. */
function paragraphKind(ancestors: string[]): ZoneKind {
  for (let i = ancestors.length - 1; i >= 0; i--) {
    if (ancestors[i] === 'list_bullet') return 'list_bullet'
    if (ancestors[i] === 'list_numbered') return 'list_numbered'
  }
  return 'paragraph'
}

/** Ancestors to attach to a paragraph zone (strip list markers — they become the kind). */
function paragraphAncestors(ancestors: string[]): string[] {
  return ancestors.filter(a => a !== 'list_bullet' && a !== 'list_numbered')
}

// ---------------------------------------------------------------------------
// Inline content extractor (handles text nodes + code marks)
// ---------------------------------------------------------------------------

interface InlineResult {
  text: string
  inlineZones: InternalZone[]
}

function extractInlineContent(
  node: PMNode,
  pmContentStart: number,
  plainStart: number,
  parentKind: ZoneKind,
): InlineResult {
  let text = ''
  const inlineZones: InternalZone[] = []

  node.forEach((child, offset) => {
    if (child.isText) {
      const childText = child.text ?? ''
      const hasCode = child.marks.some((m: Mark) => m.type.name === 'code')

      if (hasCode) {
        const inlineOffset = plainStart + text.length
        const inlinePmStart = pmContentStart + offset
        inlineZones.push({
          kind: 'inline_code',
          text: childText,
          offset: inlineOffset,
          length: childText.length,
          ancestors: [parentKind],
          lintable: false,
          pmStart: inlinePmStart,
          pmEnd: inlinePmStart + child.nodeSize,
        })
      }
      text += childText
    } else if (child.type.name === 'hard_break') {
      text += '\n'
    }
    // Ignore other inline node types
  })

  return { text, inlineZones }
}

// ---------------------------------------------------------------------------
// Block node walker
// ---------------------------------------------------------------------------

function emitBlockZone(
  node: PMNode,
  pmOpeningTagPos: number,
  kind: ZoneKind,
  ancestors: string[],
  state: SerialiseState,
): void {
  const pmContentStart = pmOpeningTagPos + 1
  const plainStart = state.text.length

  const { text: nodeText, inlineZones } = extractInlineContent(
    node,
    pmContentStart,
    plainStart,
    kind,
  )

  state.text += nodeText + '\n'

  const zone: InternalZone = {
    kind,
    text: nodeText,
    offset: plainStart,
    length: nodeText.length,
    ancestors: [...ancestors],
    lintable: lintableKind(kind),
    pmStart: pmContentStart,
    pmEnd: pmContentStart + node.content.size,
  }

  state.zones.push(zone)
  state.zones.push(...inlineZones)
}

function walkChildren(
  node: PMNode,
  pmContentStart: number,
  ancestors: string[],
  state: SerialiseState,
): void {
  node.forEach((child, offset) => {
    walkNode(child, pmContentStart + offset, ancestors, state)
  })
}

function walkNode(
  node: PMNode,
  pmOpeningTagPos: number,
  ancestors: string[],
  state: SerialiseState,
): void {
  const pmContentStart = pmOpeningTagPos + 1

  switch (node.type.name) {
    case 'paragraph': {
      const kind = paragraphKind(ancestors)
      const zoneAncestors = paragraphAncestors(ancestors)
      emitBlockZone(node, pmOpeningTagPos, kind, zoneAncestors, state)
      break
    }

    case 'heading':
      emitBlockZone(node, pmOpeningTagPos, 'heading', ancestors, state)
      break

    case 'code_block':
      emitBlockZone(node, pmOpeningTagPos, 'code_fence', ancestors, state)
      break

    case 'blockquote':
      walkChildren(node, pmContentStart, [...ancestors, 'blockquote'], state)
      break

    case 'bullet_list':
      walkChildren(node, pmContentStart, [...ancestors, 'list_bullet'], state)
      break

    case 'ordered_list':
      walkChildren(node, pmContentStart, [...ancestors, 'list_numbered'], state)
      break

    case 'list_item':
      // Pass ancestors through; the paragraph inside will pick up the list kind.
      walkChildren(node, pmContentStart, ancestors, state)
      break

    case 'table':
      walkChildren(node, pmContentStart, [...ancestors, 'table'], state)
      break

    case 'table_row':
      walkChildren(node, pmContentStart, ancestors, state)
      break

    case 'table_cell':
    case 'table_header':
      emitBlockZone(node, pmOpeningTagPos, 'table_cell', ancestors, state)
      break

    case 'reference_block':
      emitBlockZone(node, pmOpeningTagPos, 'reference_list', ancestors, state)
      break

    default:
      // Unknown block — recurse into children to avoid losing text.
      if (!node.isLeaf) {
        walkChildren(node, pmContentStart, ancestors, state)
      }
      break
  }
}

// ---------------------------------------------------------------------------
// Single-pass serialiser
// ---------------------------------------------------------------------------

function serialise(doc: PMNode): { plainText: string; zones: InternalZone[] } {
  const state: SerialiseState = { text: '', zones: [] }

  // The doc node's content starts at position 0 (doc has no opening-tag cost).
  let offset = 0
  doc.forEach((child) => {
    walkNode(child, offset, [], state)
    offset += child.nodeSize
  })

  return { plainText: state.text, zones: state.zones }
}

// ---------------------------------------------------------------------------
// Public serialiser functions
// ---------------------------------------------------------------------------

/** Plain text projection of the document. */
export function toPlainText(doc: PMNode): string {
  return serialise(doc).plainText
}

/** Zone list projection, with offsets valid into toPlainText(). */
export function toZones(doc: PMNode): Zone[] {
  return serialise(doc).zones.map(({ pmStart, pmEnd, ...z }) => z)
}

/** Internal zones including ProseMirror positions (for mutation support). */
export function toInternalZones(doc: PMNode): InternalZone[] {
  return serialise(doc).zones
}

/** Complete both projections in one pass. */
export function serialiseDoc(doc: PMNode): { plainText: string; zones: Zone[] } {
  const { plainText, zones } = serialise(doc)
  return {
    plainText,
    zones: zones.map(({ pmStart, pmEnd, ...z }) => z),
  }
}

// ---------------------------------------------------------------------------
// plainText offset → ProseMirror position mapping
// ---------------------------------------------------------------------------

/**
 * Map a plain-text character offset to the corresponding ProseMirror position.
 *
 * Returns null when the offset falls on a separator "\n" between zones or
 * outside the document's text content.
 */
export function plainPosToPm(internalZones: InternalZone[], plainPos: number): number | null {
  for (const zone of internalZones) {
    if (plainPos >= zone.offset && plainPos < zone.offset + zone.length) {
      return zone.pmStart + (plainPos - zone.offset)
    }
    // Check inline zones too
  }
  return null
}

// ---------------------------------------------------------------------------
// Clean HTML serialiser (no DOM required)
// ---------------------------------------------------------------------------

function escapeHTML(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function wrapWithMark(text: string, mark: Mark): string {
  switch (mark.type.name) {
    case 'bold': return `<strong>${text}</strong>`
    case 'italic': return `<em>${text}</em>`
    case 'code': return `<code>${text}</code>`
    case 'strikethrough': return `<s>${text}</s>`
    case 'link': {
      const href = escapeHTML(mark.attrs.href ?? '')
      const title = mark.attrs.title ? ` title="${escapeHTML(mark.attrs.title)}"` : ''
      return `<a href="${href}"${title}>${text}</a>`
    }
    default: return text
  }
}

function serializeInlineNode(node: PMNode): string {
  if (node.isText) {
    let text = escapeHTML(node.text ?? '')
    // Apply marks innermost-first (marks are sorted by the schema)
    for (const mark of node.marks) {
      text = wrapWithMark(text, mark)
    }
    return text
  }
  if (node.type.name === 'hard_break') return '<br>'
  return ''
}

function serializeChildren(node: PMNode): string {
  let out = ''
  node.forEach((child) => {
    out += serializeNode(child)
  })
  return out
}

function serializeNode(node: PMNode): string {
  if (node.isText) return serializeInlineNode(node)

  const inner = serializeChildren(node)

  switch (node.type.name) {
    case 'doc': return inner
    case 'paragraph': return `<p>${inner}</p>\n`
    case 'heading': return `<h${node.attrs.level}>${inner}</h${node.attrs.level}>\n`
    case 'blockquote': return `<blockquote>\n${inner}</blockquote>\n`
    case 'code_block': return `<pre><code>${inner}</code></pre>\n`
    case 'bullet_list': return `<ul>\n${inner}</ul>\n`
    case 'ordered_list': return `<ol>\n${inner}</ol>\n`
    case 'list_item': return `<li>${inner}</li>\n`
    case 'hard_break': return '<br>'
    case 'table': return `<table>\n<tbody>\n${inner}</tbody>\n</table>\n`
    case 'table_row': return `<tr>\n${inner}</tr>\n`
    case 'table_cell': return `<td>${inner}</td>\n`
    case 'table_header': return `<th>${inner}</th>\n`
    case 'reference_block': return `<div class="reference">\n${inner}</div>\n`
    default: return inner
  }
}

/**
 * Produce clean semantic HTML from the document AST.
 *
 * No decorations, data-* attributes, or React/Tiptap internals.  Safe to
 * pipe directly into html-to-docx for Word export.
 */
export function toCleanHTML(doc: PMNode): string {
  return serializeNode(doc)
}
