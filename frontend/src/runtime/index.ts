/**
 * Octavius document runtime — public entry point.
 *
 * Core exports (schema, document, serialisers, mutations) have no React,
 * Tiptap, or DOM dependencies and are safe to use in Node.js / headless
 * environments.
 *
 * The Tiptap binding layer (nodes/referenceBlock) is imported only by
 * OctaviusEditor.tsx and other UI-layer files.
 */

export { octaviusSchema } from './schema'
export type { OctaviusSchema } from './schema'

export { OctaviusDocument } from './document'
export type { Zone } from './serialisers'
export type { InternalZone, ZoneKind } from './serialisers'

export {
  toPlainText,
  toZones,
  toInternalZones,
  serialiseDoc,
  toCleanHTML,
  plainPosToPm,
} from './serialisers'

export {
  applyFinding,
  applySentenceCaseHeading,
  toSentenceCase,
} from './mutations'
