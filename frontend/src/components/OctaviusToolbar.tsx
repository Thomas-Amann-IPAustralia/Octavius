import React, { useCallback } from 'react'
import type { Editor } from '@tiptap/react'
import {
  Bold, Italic, Link2, Heading1, Heading2, Heading3,
  List, ListOrdered, Quote, Table, Type, BookOpen,
  AlignLeft, AlertCircle,
} from 'lucide-react'
import { toSentenceCase } from '../runtime'

interface Props {
  editor: Editor | null
  onWordImport: () => void
  onWordExport: () => void
}

interface ToolbarButtonProps {
  onClick: () => void
  active?: boolean
  disabled?: boolean
  title: string
  children: React.ReactNode
}

const ToolbarButton: React.FC<ToolbarButtonProps> = ({
  onClick, active, disabled, title, children
}) => (
  <button
    type="button"
    onMouseDown={(e) => { e.preventDefault(); onClick() }}
    disabled={disabled}
    title={title}
    className={`
      p-1.5 rounded text-xs transition-colors duration-100
      ${active
        ? 'bg-brand-100 text-brand-700 ring-1 ring-brand-300'
        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
      }
      ${disabled ? 'opacity-40 cursor-not-allowed' : ''}
    `}
  >
    {children}
  </button>
)

const Divider: React.FC = () => (
  <div className="w-px h-5 bg-slate-200 mx-0.5" />
)

export const OctaviusToolbar: React.FC<Props> = ({ editor, onWordImport, onWordExport }) => {
  const applySentenceCase = useCallback(() => {
    if (!editor) return
    const { selection, doc } = editor.state
    const { $from } = selection

    // Find the parent heading
    const heading = $from.node($from.depth)
    if (!heading || heading.type.name !== 'heading') return

    const currentText = heading.textContent
    const corrected = toSentenceCase(currentText)
    if (corrected === currentText) return

    // Replace entire heading content
    const from = $from.start($from.depth)
    const to = $from.end($from.depth)
    editor.chain().focus().deleteRange({ from, to }).insertContentAt(from, corrected).run()
  }, [editor])

  const setLink = useCallback(() => {
    if (!editor) return
    const prev = editor.getAttributes('link').href ?? ''
    const url = window.prompt('URL', prev)
    if (url === null) return
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetMark('link').run()
    } else {
      editor.chain().focus().extendMarkRange('link').setMark('link', { href: url }).run()
    }
  }, [editor])

  const insertTable = useCallback(() => {
    if (!editor) return
    editor.chain().focus().insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run()
  }, [editor])

  const insertReferenceBlock = useCallback(() => {
    if (!editor) return
    editor.chain().focus().insertReferenceBlock().run()
  }, [editor])

  if (!editor) return null

  return (
    <div className="flex items-center gap-0.5 px-3 py-1.5 border-b border-slate-100 bg-white flex-wrap">
      {/* Structure */}
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        active={editor.isActive('heading', { level: 1 })}
        title="Heading 1"
      >
        <Heading1 size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        active={editor.isActive('heading', { level: 2 })}
        title="Heading 2"
      >
        <Heading2 size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        active={editor.isActive('heading', { level: 3 })}
        title="Heading 3"
      >
        <Heading3 size={14} />
      </ToolbarButton>

      <Divider />

      {/* Lists */}
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        active={editor.isActive('bulletList')}
        title="Bullet list"
      >
        <List size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        active={editor.isActive('orderedList')}
        title="Numbered list"
      >
        <ListOrdered size={14} />
      </ToolbarButton>

      <Divider />

      {/* Blocks */}
      <ToolbarButton
        onClick={insertTable}
        title="Insert 2×2 table"
      >
        <Table size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        active={editor.isActive('blockquote')}
        title="Blockquote"
      >
        <Quote size={14} />
      </ToolbarButton>

      <Divider />

      {/* Inline */}
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBold().run()}
        active={editor.isActive('bold')}
        title="Bold"
      >
        <Bold size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleItalic().run()}
        active={editor.isActive('italic')}
        title="Italic"
      >
        <Italic size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={setLink}
        active={editor.isActive('link')}
        title="Insert link"
      >
        <Link2 size={14} />
      </ToolbarButton>

      <Divider />

      {/* Octavius extensions */}
      <ToolbarButton
        onClick={applySentenceCase}
        disabled={!editor.isActive('heading')}
        title="Convert heading to sentence case"
      >
        <Type size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={insertReferenceBlock}
        title="Insert reference block"
      >
        <BookOpen size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => {}}
        disabled
        title="Accessible Table — coming soon"
      >
        <AlignLeft size={14} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => {}}
        disabled
        title="Plain Language Block — coming soon"
      >
        <AlertCircle size={14} />
      </ToolbarButton>

      <Divider />

      {/* Document actions */}
      <button
        type="button"
        onClick={onWordImport}
        className="flex items-center gap-1 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded transition-colors"
        title="Open Word document (.docx)"
      >
        Open .docx
      </button>
      <button
        type="button"
        onClick={onWordExport}
        className="flex items-center gap-1 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded transition-colors"
        title="Export to Word (.docx)"
      >
        Export .docx
      </button>
    </div>
  )
}
