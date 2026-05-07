/**
 * Tests for runtime mutation helpers.
 *
 * Covers toSentenceCase, applyFinding dispatch, and applySentenceCaseHeading
 * structural transform.
 */

import { OctaviusDocument } from '../document'
import { toSentenceCase, applyFinding, applySentenceCaseHeading } from '../mutations'
import type { Finding } from '../../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDoc(json: object): OctaviusDocument {
  return OctaviusDocument.fromJSON(json as Record<string, unknown>)
}

function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    rule_id: 'test-rule',
    message: 'Test finding',
    start: 0,
    end: 5,
    start_char: 0,
    end_char: 5,
    severity: 'error',
    document_level: false,
    mutation_class: 'safe_replace',
    suggestion: 'fixed',
    ...overrides,
  }
}

const PARAGRAPH_DOC = {
  type: 'doc',
  content: [
    { type: 'paragraph', content: [{ type: 'text', text: 'Hello world.' }] },
  ],
}

const HEADING_DOC = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'My Big Heading' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Paragraph text.' }] },
  ],
}

const TWO_PARAGRAPHS = {
  type: 'doc',
  content: [
    { type: 'paragraph', content: [{ type: 'text', text: 'First paragraph.' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Second paragraph.' }] },
  ],
}

// ---------------------------------------------------------------------------
// toSentenceCase
// ---------------------------------------------------------------------------

describe('toSentenceCase', () => {
  test('upcases first character', () => {
    expect(toSentenceCase('hello world')).toBe('Hello world')
  })

  test('lowercases subsequent words', () => {
    expect(toSentenceCase('This Is Title Case')).toBe('This is title case')
  })

  test('already sentence case is unchanged', () => {
    expect(toSentenceCase('Hello world')).toBe('Hello world')
  })

  test('preserves ALL_CAPS acronyms', () => {
    expect(toSentenceCase('Working With APS Guidelines')).toBe('Working with APS guidelines')
  })

  test('preserves multiple consecutive uppercase words as acronyms', () => {
    expect(toSentenceCase('The CEO And CFO Attended')).toBe('The CEO and CFO attended')
  })

  test('empty string returns empty string', () => {
    expect(toSentenceCase('')).toBe('')
  })

  test('single word lowercased except first', () => {
    expect(toSentenceCase('HELLO')).toBe('HELLO')
  })

  test('single character uppercased', () => {
    expect(toSentenceCase('a')).toBe('A')
  })
})

// ---------------------------------------------------------------------------
// applyFinding — mutation_class dispatch
// ---------------------------------------------------------------------------

describe('applyFinding — safe_replace', () => {
  test('replaces text at specified span with suggestion', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 0,
      end_char: 5,
      suggestion: 'Goodbye',
    })
    const newDoc = applyFinding(doc, finding)
    expect(newDoc.plainText).toContain('Goodbye')
  })

  test('replacement arg takes precedence over suggestion', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 0,
      end_char: 5,
      suggestion: 'ignored',
    })
    const newDoc = applyFinding(doc, finding, 'Custom')
    expect(newDoc.plainText).toContain('Custom')
    expect(newDoc.plainText).not.toContain('ignored')
  })

  test('returns a new OctaviusDocument instance', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({ mutation_class: 'safe_replace', start_char: 0, end_char: 5 })
    const newDoc = applyFinding(doc, finding)
    expect(newDoc).toBeInstanceOf(OctaviusDocument)
    expect(newDoc).not.toBe(doc)
  })

  test('original document unchanged', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const original = doc.plainText
    const finding = makeFinding({ mutation_class: 'safe_replace', start_char: 0, end_char: 5 })
    applyFinding(doc, finding, 'X')
    expect(doc.plainText).toBe(original)
  })

  test('zone offset invariant holds after mutation', () => {
    const doc = makeDoc(HEADING_DOC)
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 0,
      end_char: 2,
      suggestion: 'A',
    })
    const newDoc = applyFinding(doc, finding)
    for (const zone of newDoc.zones) {
      const extracted = newDoc.plainText.slice(zone.offset, zone.offset + zone.length)
      expect(extracted).toBe(zone.text)
    }
  })
})

describe('applyFinding — requires_rewrite', () => {
  test('applies user-supplied replacement text', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({
      mutation_class: 'requires_rewrite',
      start_char: 6,
      end_char: 11,
      suggestion: undefined,
    })
    const newDoc = applyFinding(doc, finding, 'planet')
    expect(newDoc.plainText).toContain('planet')
  })

  test('empty replacement deletes the span', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({
      mutation_class: 'requires_rewrite',
      start_char: 5,
      end_char: 11,
    })
    const newDoc = applyFinding(doc, finding, '')
    // ' world' removed from 'Hello world.'
    expect(newDoc.plainText).not.toContain('world')
  })
})

describe('applyFinding — human_review', () => {
  test('returns the same document instance', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({ mutation_class: 'human_review' })
    const result = applyFinding(doc, finding)
    expect(result).toBe(doc)
  })

  test('plain text unchanged', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({ mutation_class: 'human_review' })
    expect(applyFinding(doc, finding).plainText).toBe(doc.plainText)
  })
})

describe('applyFinding — null mutation_class', () => {
  test('returns the same document instance when mutation_class is null', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({ mutation_class: null as unknown as 'safe_replace' })
    const result = applyFinding(doc, finding)
    expect(result).toBe(doc)
  })
})

describe('applyFinding — out-of-range span', () => {
  test('returns same doc when start_char maps to null PM position', () => {
    const doc = makeDoc(PARAGRAPH_DOC)
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      // Offset falls on the '\n' separator — not inside any zone text
      start_char: 12,
      end_char: 13,
    })
    const result = applyFinding(doc, finding)
    // Returns unchanged doc (plainPosToPm returns null for separator positions)
    expect(result.plainText).toBe(doc.plainText)
  })
})

// ---------------------------------------------------------------------------
// applySentenceCaseHeading
// ---------------------------------------------------------------------------

describe('applySentenceCaseHeading', () => {
  test('converts heading text to sentence case', () => {
    const doc = makeDoc(HEADING_DOC)
    // Finding spanning first word of heading 'My' (offset 0, 2 chars)
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 0,
      end_char: 2,
    })
    const newDoc = applySentenceCaseHeading(doc, finding)
    const heading = newDoc.zones.find(z => z.kind === 'heading')
    expect(heading!.text).toBe('My big heading')
  })

  test('returns same doc if heading already in sentence case', () => {
    const alreadyCorrect = {
      type: 'doc',
      content: [
        { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'My heading' }] },
      ],
    }
    const doc = makeDoc(alreadyCorrect)
    const finding = makeFinding({ start_char: 0, end_char: 2 })
    const result = applySentenceCaseHeading(doc, finding)
    expect(result).toBe(doc)
  })

  test('falls back to applyFinding when no heading zone found', () => {
    const doc = makeDoc(TWO_PARAGRAPHS)
    // start_char 0, end_char 5 in first paragraph 'First'
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 0,
      end_char: 5,
      suggestion: 'Only',
    })
    const newDoc = applySentenceCaseHeading(doc, finding)
    // No heading zone → delegates to applyFinding with suggestion
    expect(newDoc.plainText).toContain('Only')
  })

  test('preserves paragraph zones after heading mutation', () => {
    const doc = makeDoc(HEADING_DOC)
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 0,
      end_char: 14,
    })
    const newDoc = applySentenceCaseHeading(doc, finding)
    const para = newDoc.zones.find(z => z.kind === 'paragraph')
    expect(para).toBeDefined()
    expect(para!.text).toBe('Paragraph text.')
    // Zone offset invariant
    const extracted = newDoc.plainText.slice(para!.offset, para!.offset + para!.length)
    expect(extracted).toBe(para!.text)
  })
})

// ---------------------------------------------------------------------------
// OctaviusDocument.applyFinding — direct method
// ---------------------------------------------------------------------------

describe('OctaviusDocument.applyFinding', () => {
  test('replaces span in first paragraph of two-paragraph doc', () => {
    const doc = makeDoc(TWO_PARAGRAPHS)
    // 'First paragraph.' is at offset 0, length 16
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 6,
      end_char: 15,
      suggestion: 'section',
    })
    const newDoc = doc.applyFinding(finding)
    expect(newDoc.plainText).toContain('First section.')
    expect(newDoc.plainText).toContain('Second paragraph.')
  })

  test('replaces span in second paragraph', () => {
    const doc = makeDoc(TWO_PARAGRAPHS)
    // 'Second paragraph.' at offset 17, length 17
    const finding = makeFinding({
      mutation_class: 'safe_replace',
      start_char: 17,      // start of 'Second'
      end_char: 23,        // end of 'Second'
      suggestion: 'Third',
    })
    const newDoc = doc.applyFinding(finding)
    expect(newDoc.plainText).toContain('Third paragraph.')
    expect(newDoc.plainText).toContain('First paragraph.')
  })
})
