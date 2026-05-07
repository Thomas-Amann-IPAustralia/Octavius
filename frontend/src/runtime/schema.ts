/**
 * ProseMirror schema for Octavius documents.
 *
 * This module has NO React, Tiptap, or DOM imports.  It is safe to import
 * in Node.js / headless environments.  `parseDOM`/`toDOM` specs are defined
 * for Tiptap compatibility but are only invoked when a DOM is present.
 */

import { Schema } from '@tiptap/pm/model'

export const octaviusSchema = new Schema({
  nodes: {
    doc: { content: 'block+' },

    paragraph: {
      content: 'inline*',
      group: 'block',
      parseDOM: [{ tag: 'p' }],
      toDOM: () => ['p', 0] as const,
    },

    heading: {
      content: 'inline*',
      group: 'block',
      attrs: { level: { default: 1 } },
      defining: true,
      parseDOM: ([1, 2, 3, 4, 5, 6] as const).map(i => ({
        tag: `h${i}`,
        attrs: { level: i },
      })),
      toDOM: (node) => [`h${node.attrs.level}`, 0] as const,
    },

    blockquote: {
      content: 'block+',
      group: 'block',
      defining: true,
      parseDOM: [{ tag: 'blockquote' }],
      toDOM: () => ['blockquote', 0] as const,
    },

    code_block: {
      content: 'text*',
      group: 'block',
      code: true,
      defining: true,
      marks: '',
      parseDOM: [{ tag: 'pre', preserveWhitespace: 'full' as const }],
      toDOM: () => ['pre', ['code', 0]] as const,
    },

    bullet_list: {
      content: 'list_item+',
      group: 'block',
      parseDOM: [{ tag: 'ul' }],
      toDOM: () => ['ul', 0] as const,
    },

    ordered_list: {
      content: 'list_item+',
      group: 'block',
      attrs: { order: { default: 1 } },
      parseDOM: [{ tag: 'ol', getAttrs: (dom) => ({ order: parseInt((dom as HTMLElement).getAttribute('start') || '1', 10) }) }],
      toDOM: (node) => node.attrs.order === 1 ? ['ol', 0] as const : ['ol', { start: String(node.attrs.order) }, 0] as const,
    },

    list_item: {
      content: 'paragraph block*',
      defining: true,
      parseDOM: [{ tag: 'li' }],
      toDOM: () => ['li', 0] as const,
    },

    table: {
      content: 'table_row+',
      group: 'block',
      tableRole: 'table',
      parseDOM: [{ tag: 'table' }],
      toDOM: () => ['table', ['tbody', 0]] as const,
    },

    table_row: {
      content: '(table_cell | table_header)*',
      tableRole: 'row',
      parseDOM: [{ tag: 'tr' }],
      toDOM: () => ['tr', 0] as const,
    },

    table_cell: {
      content: 'inline*',
      attrs: { colspan: { default: 1 }, rowspan: { default: 1 } },
      tableRole: 'cell',
      parseDOM: [{
        tag: 'td',
        getAttrs: (dom) => ({
          colspan: (dom as HTMLTableCellElement).colSpan,
          rowspan: (dom as HTMLTableCellElement).rowSpan,
        }),
      }],
      toDOM: (node) => {
        const attrs: Record<string, string> = {}
        if (node.attrs.colspan !== 1) attrs.colspan = String(node.attrs.colspan)
        if (node.attrs.rowspan !== 1) attrs.rowspan = String(node.attrs.rowspan)
        return ['td', attrs, 0] as const
      },
    },

    table_header: {
      content: 'inline*',
      attrs: { colspan: { default: 1 }, rowspan: { default: 1 } },
      tableRole: 'header_cell',
      parseDOM: [{
        tag: 'th',
        getAttrs: (dom) => ({
          colspan: (dom as HTMLTableCellElement).colSpan,
          rowspan: (dom as HTMLTableCellElement).rowSpan,
        }),
      }],
      toDOM: (node) => {
        const attrs: Record<string, string> = {}
        if (node.attrs.colspan !== 1) attrs.colspan = String(node.attrs.colspan)
        if (node.attrs.rowspan !== 1) attrs.rowspan = String(node.attrs.rowspan)
        return ['th', attrs, 0] as const
      },
    },

    reference_block: {
      content: 'inline*',
      group: 'block',
      attrs: { 'data-type': { default: 'reference-block' } },
      parseDOM: [{ tag: 'div[data-type="reference-block"]' }],
      toDOM: () => ['div', { 'data-type': 'reference-block', class: 'octavius-reference-block' }, 0] as const,
    },

    text: { group: 'inline' },

    hard_break: {
      inline: true,
      group: 'inline',
      selectable: false,
      linebreakReplacement: true,
      parseDOM: [{ tag: 'br' }],
      toDOM: () => ['br'] as const,
    },
  },

  marks: {
    bold: {
      parseDOM: [{ tag: 'strong' }, { tag: 'b' }],
      toDOM: () => ['strong', 0] as const,
    },
    italic: {
      parseDOM: [{ tag: 'em' }, { tag: 'i' }],
      toDOM: () => ['em', 0] as const,
    },
    code: {
      parseDOM: [{ tag: 'code' }],
      toDOM: () => ['code', 0] as const,
    },
    strikethrough: {
      parseDOM: [{ tag: 's' }, { tag: 'del' }],
      toDOM: () => ['s', 0] as const,
    },
    link: {
      attrs: {
        href: {},
        title: { default: null },
        target: { default: '_blank' },
      },
      inclusive: false,
      parseDOM: [{
        tag: 'a[href]',
        getAttrs: (dom) => ({
          href: (dom as HTMLAnchorElement).getAttribute('href'),
          title: (dom as HTMLAnchorElement).getAttribute('title'),
          target: (dom as HTMLAnchorElement).getAttribute('target'),
        }),
      }],
      toDOM: (mark) => ['a', {
        href: mark.attrs.href,
        title: mark.attrs.title,
        target: mark.attrs.target,
        rel: 'noopener noreferrer',
      }, 0] as const,
    },
  },
})

export type OctaviusSchema = typeof octaviusSchema
