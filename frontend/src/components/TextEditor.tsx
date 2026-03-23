import React, { useCallback, useLayoutEffect, useRef } from 'react'
import type { Finding } from '../types'
import { useHighlights } from '../hooks/useHighlights'

interface Props {
  text: string
  findings: Finding[]
  activeId: string | null
  onTextChange: (text: string) => void
  onFindingClick: (finding: Finding) => void
}

const HIGHLIGHT_CLASS: Record<string, string> = {
  error: 'highlight-error',
  warn:  'highlight-warn',
  info:  'highlight-info',
}

const PLACEHOLDER = 'Paste your text here — analysis runs automatically after you stop typing…'

export const TextEditor: React.FC<Props> = ({
  text,
  findings,
  activeId,
  onTextChange,
  onFindingClick,
}) => {
  const segments = useHighlights(text, findings)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const backdropRef = useRef<HTMLDivElement>(null)

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onTextChange(e.target.value)
    },
    [onTextChange]
  )

  // Sync scroll position from textarea to backdrop
  const handleScroll = useCallback(() => {
    if (textareaRef.current && backdropRef.current) {
      backdropRef.current.scrollTop = textareaRef.current.scrollTop
      backdropRef.current.scrollLeft = textareaRef.current.scrollLeft
    }
  }, [])

  // Auto-resize textarea to fit content
  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.max(el.scrollHeight, 200)}px`
  }, [text])

  // Detect which finding the cursor is in on click, for panel highlighting
  const handleClick = useCallback(() => {
    const el = textareaRef.current
    if (!el || !findings.length) return
    const pos = el.selectionStart
    const hit = findings.find(f => pos >= f.start_char && pos <= f.end_char)
    if (hit) onFindingClick(hit)
  }, [findings, onFindingClick])

  return (
    <div className="relative h-full flex flex-col">
      <div className="octavius-editor-container flex-1">
        {/* Backdrop: highlighted text (visual only, behind textarea) */}
        <div
          ref={backdropRef}
          className="octavius-editor-backdrop"
          aria-hidden="true"
        >
          {segments.map((seg) => {
            if (!seg.finding) {
              return <span key={seg.index}>{seg.text}</span>
            }

            const f = seg.finding
            const isActive = activeId === f.rule_id
            const cls = `${HIGHLIGHT_CLASS[f.severity] ?? 'highlight-info'} ${isActive ? 'is-active' : ''}`

            return (
              <span key={seg.index} className={cls}>
                {seg.text}
              </span>
            )
          })}
        </div>

        {/* Textarea: actual input layer (transparent text, visible caret) */}
        <textarea
          ref={textareaRef}
          className="octavius-editor-textarea"
          value={text}
          onChange={handleChange}
          onScroll={handleScroll}
          onClick={handleClick}
          placeholder={PLACEHOLDER}
          spellCheck={false}
        />
      </div>
    </div>
  )
}
