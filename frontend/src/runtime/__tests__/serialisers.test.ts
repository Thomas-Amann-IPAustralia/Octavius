/**
 * Zone offset invariant tests for the single-pass serialiser.
 *
 * For every zone produced by toZones():
 *   plainText.slice(zone.offset, zone.offset + zone.length) === zone.text
 */

import { OctaviusDocument } from '../document'
import { toPlainText, toZones, toInternalZones, serialiseDoc, toCleanHTML } from '../serialisers'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function docFromJSON(json: object): ReturnType<typeof OctaviusDocument.fromJSON> {
  return OctaviusDocument.fromJSON(json as Record<string, unknown>)
}

/** Assert zone offset invariant for every zone in the document. */
function assertOffsetInvariant(plainText: string, zones: ReturnType<typeof toZones>): void {
  for (const zone of zones) {
    const extracted = plainText.slice(zone.offset, zone.offset + zone.length)
    expect(extracted).toBe(zone.text)
  }
}

// ---------------------------------------------------------------------------
// Fixture documents
// ---------------------------------------------------------------------------

const SINGLE_PARAGRAPH = {
  type: 'doc',
  content: [
    { type: 'paragraph', content: [{ type: 'text', text: 'Hello world.' }] },
  ],
}

const HEADING_AND_PARAGRAPH = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'My Heading' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Following paragraph.' }] },
  ],
}

const BULLET_LIST = {
  type: 'doc',
  content: [
    {
      type: 'bullet_list',
      content: [
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'First item' }] }] },
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Second item' }] }] },
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Third item' }] }] },
      ],
    },
  ],
}

const ORDERED_LIST = {
  type: 'doc',
  content: [
    {
      type: 'ordered_list',
      attrs: { start: 1 },
      content: [
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Alpha' }] }] },
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Beta' }] }] },
      ],
    },
  ],
}

const CODE_BLOCK = {
  type: 'doc',
  content: [
    { type: 'code_block', content: [{ type: 'text', text: 'print("hello")' }] },
  ],
}

const MULTIPLE_HEADINGS = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'Title' }] },
    { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'Section One' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Prose here.' }] },
    { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'Section Two' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'More prose.' }] },
  ],
}

const MIXED_CONTENT = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'Document Title' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Introduction paragraph with some text.' }] },
    {
      type: 'bullet_list',
      content: [
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Item A' }] }] },
        { type: 'list_item', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Item B' }] }] },
      ],
    },
    { type: 'code_block', content: [{ type: 'text', text: 'const x = 1' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Conclusion.' }] },
  ],
}

const BLOCKQUOTE = {
  type: 'doc',
  content: [
    {
      type: 'blockquote',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'Quoted text.' }] },
      ],
    },
    { type: 'paragraph', content: [{ type: 'text', text: 'After quote.' }] },
  ],
}

const INLINE_CODE = {
  type: 'doc',
  content: [
    {
      type: 'paragraph',
      content: [
        { type: 'text', text: 'Use ' },
        { type: 'text', text: 'myFunc()', marks: [{ type: 'code' }] },
        { type: 'text', text: ' here.' },
      ],
    },
  ],
}

const EMPTY_DOC = {
  type: 'doc',
  content: [
    { type: 'paragraph' },
  ],
}

// ---------------------------------------------------------------------------
// Zone offset invariant — parametrised
// ---------------------------------------------------------------------------

const FIXTURES: Array<[string, object]> = [
  ['single paragraph', SINGLE_PARAGRAPH],
  ['heading and paragraph', HEADING_AND_PARAGRAPH],
  ['bullet list', BULLET_LIST],
  ['ordered list', ORDERED_LIST],
  ['code block', CODE_BLOCK],
  ['multiple headings', MULTIPLE_HEADINGS],
  ['mixed content', MIXED_CONTENT],
  ['blockquote', BLOCKQUOTE],
  ['inline code', INLINE_CODE],
  ['empty doc', EMPTY_DOC],
]

describe('zone offset invariant', () => {
  test.each(FIXTURES)('%s', (_label, json) => {
    const octDoc = docFromJSON(json)
    assertOffsetInvariant(octDoc.plainText, octDoc.zones)
  })
})

// ---------------------------------------------------------------------------
// Specific zone content assertions
// ---------------------------------------------------------------------------

describe('toPlainText', () => {
  test('single paragraph produces text with trailing newline', () => {
    const octDoc = docFromJSON(SINGLE_PARAGRAPH)
    expect(octDoc.plainText).toBe('Hello world.\n')
  })

  test('heading and paragraph separated by newlines', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    expect(octDoc.plainText).toBe('My Heading\nFollowing paragraph.\n')
  })

  test('list items each get their own line', () => {
    const octDoc = docFromJSON(BULLET_LIST)
    expect(octDoc.plainText).toBe('First item\nSecond item\nThird item\n')
  })

  test('code block text preserved verbatim', () => {
    const octDoc = docFromJSON(CODE_BLOCK)
    expect(octDoc.plainText).toBe('print("hello")\n')
  })
})

// ---------------------------------------------------------------------------
// Zone kind assertions
// ---------------------------------------------------------------------------

describe('toZones kinds', () => {
  test('paragraph node produces paragraph zone', () => {
    const octDoc = docFromJSON(SINGLE_PARAGRAPH)
    const kinds = octDoc.zones.map(z => z.kind)
    expect(kinds).toContain('paragraph')
  })

  test('heading node produces heading zone', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    const kinds = octDoc.zones.map(z => z.kind)
    expect(kinds).toContain('heading')
  })

  test('bullet list paragraphs become list_bullet zones', () => {
    const octDoc = docFromJSON(BULLET_LIST)
    const kinds = octDoc.zones.map(z => z.kind)
    expect(kinds.every(k => k === 'list_bullet')).toBe(true)
    expect(kinds).toHaveLength(3)
  })

  test('ordered list paragraphs become list_numbered zones', () => {
    const octDoc = docFromJSON(ORDERED_LIST)
    const kinds = octDoc.zones.map(z => z.kind)
    expect(kinds.every(k => k === 'list_numbered')).toBe(true)
  })

  test('code_block node produces code_fence zone with lintable=false', () => {
    const octDoc = docFromJSON(CODE_BLOCK)
    const zone = octDoc.zones.find(z => z.kind === 'code_fence')
    expect(zone).toBeDefined()
    expect(zone!.lintable).toBe(false)
  })

  test('blockquote paragraph zones have blockquote ancestor', () => {
    const octDoc = docFromJSON(BLOCKQUOTE)
    const quoted = octDoc.zones.find(z => z.text === 'Quoted text.')
    expect(quoted).toBeDefined()
    expect(quoted!.ancestors).toContain('blockquote')
  })

  test('text outside blockquote has no blockquote ancestor', () => {
    const octDoc = docFromJSON(BLOCKQUOTE)
    const after = octDoc.zones.find(z => z.text === 'After quote.')
    expect(after).toBeDefined()
    expect(after!.ancestors).not.toContain('blockquote')
  })

  test('inline code mark produces inline_code zone', () => {
    const octDoc = docFromJSON(INLINE_CODE)
    const codeZones = octDoc.zones.filter(z => z.kind === 'inline_code')
    expect(codeZones).toHaveLength(1)
    expect(codeZones[0].text).toBe('myFunc()')
    expect(codeZones[0].lintable).toBe(false)
  })

  test('paragraph surrounding inline code is lintable', () => {
    const octDoc = docFromJSON(INLINE_CODE)
    const para = octDoc.zones.find(z => z.kind === 'paragraph')
    expect(para).toBeDefined()
    expect(para!.lintable).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Zone text content assertions
// ---------------------------------------------------------------------------

describe('zone text content', () => {
  test('heading zone text excludes trailing newline', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    const heading = octDoc.zones.find(z => z.kind === 'heading')
    expect(heading!.text).toBe('My Heading')
    expect(heading!.text).not.toMatch(/\n/)
  })

  test('paragraph zone text excludes trailing newline', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    const para = octDoc.zones.find(z => z.kind === 'paragraph')
    expect(para!.text).toBe('Following paragraph.')
    expect(para!.text).not.toMatch(/\n/)
  })

  test('zones have correct offsets in mixed document', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    const zones = octDoc.zones
    const heading = zones.find(z => z.kind === 'heading')!
    const para = zones.find(z => z.kind === 'paragraph')!
    // Heading offset is 0
    expect(heading.offset).toBe(0)
    // Paragraph follows: heading.text + '\n'
    expect(para.offset).toBe(heading.text.length + 1)
  })
})

// ---------------------------------------------------------------------------
// serialiseDoc — single call producing both projections
// ---------------------------------------------------------------------------

describe('serialiseDoc', () => {
  test('produces consistent plainText and zones in one call', () => {
    const octDoc = docFromJSON(MIXED_CONTENT)
    const ast = octDoc.ast
    const { plainText, zones } = require('../serialisers').serialiseDoc(ast)
    assertOffsetInvariant(plainText, zones)
  })
})

// ---------------------------------------------------------------------------
// toInternalZones — ProseMirror position tracking
// ---------------------------------------------------------------------------

describe('toInternalZones', () => {
  test('pmStart and pmEnd are positive integers', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    const zones = toInternalZones(octDoc.ast)
    for (const z of zones) {
      expect(z.pmStart).toBeGreaterThanOrEqual(0)
      expect(z.pmEnd).toBeGreaterThan(z.pmStart)
    }
  })

  test('pmEnd - pmStart equals zone text length for leaf blocks', () => {
    const octDoc = docFromJSON(SINGLE_PARAGRAPH)
    const zones = toInternalZones(octDoc.ast)
    const para = zones.find(z => z.kind === 'paragraph')!
    expect(para.pmEnd - para.pmStart).toBe(para.text.length)
  })
})

// ---------------------------------------------------------------------------
// toCleanHTML — no DOM required
// ---------------------------------------------------------------------------

describe('toCleanHTML', () => {
  test('paragraph produces <p> tag', () => {
    const octDoc = docFromJSON(SINGLE_PARAGRAPH)
    const html = toCleanHTML(octDoc.ast)
    expect(html).toContain('<p>Hello world.</p>')
  })

  test('heading produces correct heading tag', () => {
    const octDoc = docFromJSON(HEADING_AND_PARAGRAPH)
    const html = toCleanHTML(octDoc.ast)
    expect(html).toContain('<h1>My Heading</h1>')
  })

  test('bullet list produces ul/li tags', () => {
    const octDoc = docFromJSON(BULLET_LIST)
    const html = toCleanHTML(octDoc.ast)
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>')
  })

  test('code block produces pre/code tags', () => {
    const octDoc = docFromJSON(CODE_BLOCK)
    const html = toCleanHTML(octDoc.ast)
    expect(html).toContain('<pre><code>')
  })
})
