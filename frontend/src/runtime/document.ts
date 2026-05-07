/**
 * OctaviusDocument — the canonical document runtime.
 *
 * NO React, Tiptap, or DOM imports in this file.  The core methods work in
 * any JavaScript environment including Node.js.
 *
 * The AST (ProseMirror Node) is the single source of truth.  `plainText` and
 * `zones` are derived projections, cached against the current document version.
 *
 * Mutations produce new OctaviusDocument instances (immutable pattern).
 */

import { Node as PMNode, Schema } from '@tiptap/pm/model'
import { EditorState } from '@tiptap/pm/state'
import { octaviusSchema } from './schema'
import {
  toPlainText,
  toZones,
  toInternalZones,
  toCleanHTML,
  plainPosToPm,
  type Zone,
  type InternalZone,
} from './serialisers'
import type { Finding } from '../types'

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export type { Zone }

export class OctaviusDocument {
  private readonly _doc: PMNode
  // Lazy cache — populated on first access
  private _plainText: string | null = null
  private _zones: Zone[] | null = null
  private _internalZones: InternalZone[] | null = null

  /** @internal Use the static factory methods. */
  constructor(doc: PMNode) {
    this._doc = doc
  }

  // ── Factory methods ────────────────────────────────────────────────────────

  /** Create an empty document with a single empty paragraph. */
  static empty(): OctaviusDocument {
    const doc = octaviusSchema.node('doc', null, [
      octaviusSchema.node('paragraph'),
    ])
    return new OctaviusDocument(doc)
  }

  /**
   * Create a document from ProseMirror JSON.
   *
   * Uses `octaviusSchema`; compatible with Tiptap's JSON output when both
   * use the same node names.
   */
  static fromJSON(json: Record<string, unknown>): OctaviusDocument {
    const doc = octaviusSchema.nodeFromJSON(json)
    return new OctaviusDocument(doc)
  }

  /**
   * Create a document from an existing ProseMirror Node.
   *
   * Used by the Tiptap binding layer to wrap the live editor doc.
   */
  static fromPMNode(node: PMNode): OctaviusDocument {
    return new OctaviusDocument(node)
  }

  /**
   * Create a document from HTML.
   *
   * Requires a DOM environment (browser or jsdom).  Throws in Node.js unless
   * a global `document` / `DOMParser` is available.
   */
  static fromHTML(html: string): OctaviusDocument {
    if (typeof document === 'undefined') {
      throw new Error(
        'OctaviusDocument.fromHTML() requires a DOM environment. ' +
        'Use OctaviusDocument.fromJSON() in Node.js / headless contexts.'
      )
    }
    const { DOMParser: PmDOMParser } = require('@tiptap/pm/model')
    const container = document.createElement('div')
    container.innerHTML = html
    const doc = PmDOMParser.fromSchema(octaviusSchema).parse(container)
    return new OctaviusDocument(doc)
  }

  // ── Projections ────────────────────────────────────────────────────────────

  /** Memoised plain-text projection. */
  get plainText(): string {
    if (this._plainText === null) {
      this._plainText = toPlainText(this._doc)
    }
    return this._plainText
  }

  /** Memoised zone projection. */
  get zones(): Zone[] {
    if (this._zones === null) {
      this._zones = toZones(this._doc)
    }
    return this._zones
  }

  /** Internal zones (includes ProseMirror positions). */
  get internalZones(): InternalZone[] {
    if (this._internalZones === null) {
      this._internalZones = toInternalZones(this._doc)
    }
    return this._internalZones
  }

  /** The raw ProseMirror AST. */
  get ast(): PMNode {
    return this._doc
  }

  // ── Serialisation ──────────────────────────────────────────────────────────

  /** ProseMirror JSON — round-trips through fromJSON(). */
  toJSON(): Record<string, unknown> {
    return this._doc.toJSON()
  }

  /** Clean semantic HTML without decorations or Tiptap internals. */
  toCleanHTML(): string {
    return toCleanHTML(this._doc)
  }

  // ── Position mapping ───────────────────────────────────────────────────────

  /**
   * Map a plain-text character offset to the corresponding ProseMirror
   * position in this document.
   *
   * Returns null when the offset falls on a zone separator or outside the
   * document's text content.
   */
  plainPosToPm(plainPos: number): number | null {
    return plainPosToPm(this.internalZones, plainPos)
  }

  // ── Mutations ──────────────────────────────────────────────────────────────

  /**
   * Apply a ProseMirror transaction and return a new document.
   *
   * Used by the Tiptap binding layer.
   */
  applyTransaction(tr: import('@tiptap/pm/state').Transaction): OctaviusDocument {
    return new OctaviusDocument(tr.doc)
  }

  /**
   * Apply a finding replacement and return a new document.
   *
   * Supported mutation_class values:
   * - `safe_replace`: Replace the spanned text with `replacement` (or
   *   `finding.suggestion`).
   * - `requires_rewrite`: Same mechanics as safe_replace; caller supplies the
   *   user's rewrite text via `replacement`.
   * - `human_review` / null: No text mutation; returns this document unchanged.
   */
  applyFinding(finding: Finding, replacement?: string): OctaviusDocument {
    const mc = finding.mutation_class
    if (mc !== 'safe_replace' && mc !== 'requires_rewrite') {
      return this
    }

    const rep = replacement ?? finding.suggestion ?? ''

    const pmFrom = this.plainPosToPm(finding.start_char)
    const pmTo = this.plainPosToPm(finding.end_char)

    if (pmFrom === null || pmTo === null || pmFrom > pmTo) {
      return this
    }

    const state = EditorState.create({
      doc: this._doc,
      schema: this._doc.type.schema,
    })
    const tr = state.tr.insertText(rep, pmFrom, pmTo)
    return new OctaviusDocument(tr.doc)
  }
}
