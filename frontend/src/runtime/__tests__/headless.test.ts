/**
 * @jest-environment node
 *
 * Headless runtime tests — no jsdom, no React, no Tiptap extensions.
 *
 * These tests verify that the core runtime can be imported and exercised in a
 * plain Node.js environment.  They exist to prevent accidental DOM / browser
 * dependencies from creeping into the runtime core.
 */

import { OctaviusDocument } from '../document'
import { octaviusSchema } from '../schema'
import {
  toPlainText,
  toZones,
  toInternalZones,
  serialiseDoc,
  toCleanHTML,
  plainPosToPm,
} from '../serialisers'
import { toSentenceCase, applyFinding, applySentenceCaseHeading } from '../mutations'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDoc(json: object): OctaviusDocument {
  return OctaviusDocument.fromJSON(json as Record<string, unknown>)
}

const PARA_JSON = {
  type: 'doc',
  content: [
    { type: 'paragraph', content: [{ type: 'text', text: 'Hello from Node.' }] },
  ],
}

const HEADING_JSON = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'Node Heading' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Node paragraph.' }] },
  ],
}

// ---------------------------------------------------------------------------
// Schema — headless construction
// ---------------------------------------------------------------------------

describe('octaviusSchema in Node.js', () => {
  test('schema object is defined', () => {
    expect(octaviusSchema).toBeDefined()
  })

  test('schema has expected node types', () => {
    expect(octaviusSchema.nodes.doc).toBeDefined()
    expect(octaviusSchema.nodes.paragraph).toBeDefined()
    expect(octaviusSchema.nodes.heading).toBeDefined()
    expect(octaviusSchema.nodes.bullet_list).toBeDefined()
    expect(octaviusSchema.nodes.code_block).toBeDefined()
    expect(octaviusSchema.nodes.table).toBeDefined()
    expect(octaviusSchema.nodes.reference_block).toBeDefined()
  })

  test('schema has expected mark types', () => {
    expect(octaviusSchema.marks.bold).toBeDefined()
    expect(octaviusSchema.marks.italic).toBeDefined()
    expect(octaviusSchema.marks.code).toBeDefined()
    expect(octaviusSchema.marks.link).toBeDefined()
  })

  test('can create a doc node programmatically', () => {
    const doc = octaviusSchema.node('doc', null, [
      octaviusSchema.node('paragraph', null, [
        octaviusSchema.text('Direct construction'),
      ]),
    ])
    expect(doc.type.name).toBe('doc')
    expect(doc.firstChild!.type.name).toBe('paragraph')
  })
})

// ---------------------------------------------------------------------------
// OctaviusDocument — construction
// ---------------------------------------------------------------------------

describe('OctaviusDocument in Node.js', () => {
  test('fromJSON creates a valid document', () => {
    const doc = makeDoc(PARA_JSON)
    expect(doc).toBeInstanceOf(OctaviusDocument)
  })

  test('empty() creates a valid document', () => {
    const doc = OctaviusDocument.empty()
    expect(doc).toBeInstanceOf(OctaviusDocument)
  })

  test('fromPMNode wraps a PM node', () => {
    const pmNode = octaviusSchema.nodeFromJSON(PARA_JSON)
    const doc = OctaviusDocument.fromPMNode(pmNode)
    expect(doc.ast).toBe(pmNode)
  })

  test('fromHTML throws in Node.js environment', () => {
    expect(() => OctaviusDocument.fromHTML('<p>test</p>')).toThrow(
      /DOM environment/
    )
  })
})

// ---------------------------------------------------------------------------
// Projections
// ---------------------------------------------------------------------------

describe('plainText projection in Node.js', () => {
  test('produces correct plain text', () => {
    const doc = makeDoc(PARA_JSON)
    expect(doc.plainText).toBe('Hello from Node.\n')
  })

  test('result is memoised (same reference)', () => {
    const doc = makeDoc(PARA_JSON)
    const first = doc.plainText
    const second = doc.plainText
    expect(first).toBe(second)
  })

  test('heading and paragraph produce two lines', () => {
    const doc = makeDoc(HEADING_JSON)
    const lines = doc.plainText.split('\n').filter(Boolean)
    expect(lines).toHaveLength(2)
    expect(lines[0]).toBe('Node Heading')
    expect(lines[1]).toBe('Node paragraph.')
  })
})

describe('zones projection in Node.js', () => {
  test('zones is an array', () => {
    const doc = makeDoc(PARA_JSON)
    expect(Array.isArray(doc.zones)).toBe(true)
  })

  test('zones is memoised (same reference)', () => {
    const doc = makeDoc(PARA_JSON)
    expect(doc.zones).toBe(doc.zones)
  })

  test('zone offset invariant holds in Node.js', () => {
    const doc = makeDoc(HEADING_JSON)
    for (const zone of doc.zones) {
      const extracted = doc.plainText.slice(zone.offset, zone.offset + zone.length)
      expect(extracted).toBe(zone.text)
    }
  })

  test('heading zone has kind=heading', () => {
    const doc = makeDoc(HEADING_JSON)
    expect(doc.zones.some(z => z.kind === 'heading')).toBe(true)
  })
})

describe('toJSON round-trip', () => {
  test('fromJSON → toJSON is idempotent', () => {
    const doc = makeDoc(PARA_JSON)
    const json = doc.toJSON()
    const doc2 = OctaviusDocument.fromJSON(json)
    expect(doc2.plainText).toBe(doc.plainText)
  })
})

// ---------------------------------------------------------------------------
// Serialiser functions directly in Node.js
// ---------------------------------------------------------------------------

describe('serialiser functions in Node.js', () => {
  test('toPlainText works on PM node', () => {
    const pmNode = octaviusSchema.nodeFromJSON(PARA_JSON)
    expect(toPlainText(pmNode)).toBe('Hello from Node.\n')
  })

  test('toZones produces zones without pmStart/pmEnd', () => {
    const pmNode = octaviusSchema.nodeFromJSON(PARA_JSON)
    const zones = toZones(pmNode)
    expect(zones.length).toBeGreaterThan(0)
    expect((zones[0] as any).pmStart).toBeUndefined()
  })

  test('toInternalZones includes pmStart/pmEnd', () => {
    const pmNode = octaviusSchema.nodeFromJSON(PARA_JSON)
    const zones = toInternalZones(pmNode)
    expect(zones[0].pmStart).toBeDefined()
    expect(zones[0].pmEnd).toBeDefined()
  })

  test('serialiseDoc produces both projections in one call', () => {
    const pmNode = octaviusSchema.nodeFromJSON(HEADING_JSON)
    const { plainText, zones } = serialiseDoc(pmNode)
    expect(plainText).toBe('Node Heading\nNode paragraph.\n')
    for (const z of zones) {
      expect(plainText.slice(z.offset, z.offset + z.length)).toBe(z.text)
    }
  })

  test('toCleanHTML produces valid HTML strings', () => {
    const pmNode = octaviusSchema.nodeFromJSON(HEADING_JSON)
    const html = toCleanHTML(pmNode)
    expect(html).toContain('<h1>')
    expect(html).toContain('<p>')
    expect(html).toContain('Node Heading')
  })

  test('plainPosToPm maps offset within zone', () => {
    const pmNode = octaviusSchema.nodeFromJSON(PARA_JSON)
    const internalZones = toInternalZones(pmNode)
    // Offset 0 is the start of 'Hello from Node.'
    const pmPos = plainPosToPm(internalZones, 0)
    expect(pmPos).not.toBeNull()
    expect(typeof pmPos).toBe('number')
  })

  test('plainPosToPm returns null for separator newline', () => {
    const pmNode = octaviusSchema.nodeFromJSON(PARA_JSON)
    const internalZones = toInternalZones(pmNode)
    // The '\n' after 'Hello from Node.' is at offset 16, which is position
    // zone.offset + zone.length — not inside any zone's text span.
    const para = internalZones.find(z => z.kind === 'paragraph')!
    const sepOffset = para.offset + para.length  // position of the '\n'
    const pmPos = plainPosToPm(internalZones, sepOffset)
    expect(pmPos).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Mutations in Node.js
// ---------------------------------------------------------------------------

describe('mutations in Node.js', () => {
  test('toSentenceCase available in Node.js', () => {
    expect(toSentenceCase('Title Case Heading')).toBe('Title case heading')
  })

  test('applyFinding safe_replace in Node.js', () => {
    const doc = makeDoc(PARA_JSON)
    const finding = {
      rule_id: 'test',
      message: 'test',
      start: 0,
      end: 5,
      start_char: 0,
      end_char: 5,
      severity: 'error' as const,
      document_level: false,
      mutation_class: 'safe_replace' as const,
      suggestion: 'Howdy',
    }
    const newDoc = applyFinding(doc, finding)
    expect(newDoc.plainText).toContain('Howdy')
  })

  test('applyFinding human_review returns same doc', () => {
    const doc = makeDoc(PARA_JSON)
    const finding = {
      rule_id: 'test',
      message: 'test',
      start: 0,
      end: 5,
      start_char: 0,
      end_char: 5,
      severity: 'error' as const,
      document_level: false,
      mutation_class: 'human_review' as const,
    }
    expect(applyFinding(doc, finding)).toBe(doc)
  })

  test('applySentenceCaseHeading works in Node.js', () => {
    const doc = makeDoc(HEADING_JSON)
    const finding = {
      rule_id: 'heading-case',
      message: 'Heading not in sentence case',
      start: 0,
      end: 4,
      start_char: 0,
      end_char: 4,
      severity: 'warn' as const,
      document_level: false,
      mutation_class: 'safe_replace' as const,
    }
    const newDoc = applySentenceCaseHeading(doc, finding)
    const heading = newDoc.zones.find(z => z.kind === 'heading')
    expect(heading!.text).toBe('Node heading')
  })
})

// ---------------------------------------------------------------------------
// No React / DOM dependencies imported
// ---------------------------------------------------------------------------

describe('no DOM globals required', () => {
  test('document global is undefined in Node.js environment', () => {
    // This test runs under @jest-environment node, so document must not exist
    expect(typeof document).toBe('undefined')
  })

  test('window global is undefined in Node.js environment', () => {
    expect(typeof window).toBe('undefined')
  })

  test('runtime modules load without referencing DOM globals', () => {
    // If any of the imports above caused an error due to missing DOM globals,
    // the test file would have failed to load.  Reaching this line means
    // all imports succeeded in the Node.js environment.
    expect(true).toBe(true)
  })
})
