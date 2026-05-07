/**
 * ReferenceBlock — Tiptap extension for the reference_block custom node.
 *
 * This is the Tiptap binding layer for the `reference_block` node defined in
 * schema.ts.  It is the only file in runtime/nodes/ that imports from Tiptap.
 */

import { Node as TiptapNode, mergeAttributes } from '@tiptap/core'

export const ReferenceBlock = TiptapNode.create({
  name: 'referenceBlock',
  group: 'block',
  content: 'inline*',
  defining: true,

  addAttributes() {
    return {
      'data-type': {
        default: 'reference-block',
        rendered: true,
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="reference-block"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, {
        'data-type': 'reference-block',
        class: 'octavius-reference-block',
      }),
      0,
    ]
  },

  addCommands() {
    return {
      toggleReferenceBlock:
        () =>
        ({ commands }) => {
          return commands.toggleWrap(this.name)
        },
      insertReferenceBlock:
        () =>
        ({ commands }) => {
          return commands.setNode(this.name)
        },
    }
  },
})

// Augment Tiptap's Commands interface so TypeScript knows about the new commands.
declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    referenceBlock: {
      toggleReferenceBlock: () => ReturnType
      insertReferenceBlock: () => ReturnType
    }
  }
}
