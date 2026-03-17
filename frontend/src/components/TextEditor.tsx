import React, { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { Finding } from '../types'
import { useHighlights } from '../hooks/useHighlights'
import { Tooltip } from './Tooltip'

interface Props {
  text: string
  findings: Finding[]
  activeId: string | null           // rule_id of the active finding
  onTextChange: (text: string) => void
  onFindingClick: (finding: Finding) => void
}

const HIGHLIGHT_CLASS: Record<string, string> = {
  error: 'highlight-error',
  warn:  'highlight-warn',
  info:  'highlight-info',
}

const PLACEHOLDER = 'Paste your text here and click Analyse to check for style issues…'

export const TextEditor: React.FC<Props> = ({
  text,
  findings,
  activeId,
  onTextChange,
  onFindingClick,
}) => {
  const segments = useHighlights(text, findings)
  const editorRef = useRef<HTMLDivElement>(null)

  const [tooltipFinding, setTooltipFinding] = useState<Finding | null>(null)
  const [tooltipAnchor, setTooltipAnchor] = useState<HTMLElement | null>(null)

  // When findings are present, React renders highlighted segments as <span>
  // elements inside the contentEditable div. However, the browser's native
  // text nodes from the paste/input operation remain in the DOM alongside
  // React's rendered spans, causing the text to appear duplicated.
  // Remove those stale text nodes after React has rendered the segments.
  const hasHighlights = segments.some(s => s.finding !== null)
  useLayoutEffect(() => {
    const el = editorRef.current
    if (!el || !hasHighlights) return

    for (let i = el.childNodes.length - 1; i >= 0; i--) {
      if (el.childNodes[i].nodeType === Node.TEXT_NODE) {
        el.removeChild(el.childNodes[i])
      }
    }
  }, [segments, hasHighlights])

  // Send updated plain text back to Streamlit on each input event
  const handleInput = useCallback(() => {
    if (editorRef.current) {
      onTextChange(editorRef.current.innerText)
    }
  }, [onTextChange])

  const handleHighlightMouseEnter = useCallback(
    (finding: Finding, el: HTMLElement) => {
      setTooltipFinding(finding)
      setTooltipAnchor(el)
    },
    []
  )

  const handleHighlightMouseLeave = useCallback(() => {
    setTooltipFinding(null)
    setTooltipAnchor(null)
  }, [])

  return (
    <div className="relative h-full flex flex-col">
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        data-placeholder={PLACEHOLDER}
        className="octavius-editor-content flex-1 px-5 py-4 text-slate-800 text-sm"
        onInput={handleInput}
      >
        {segments.map((seg) => {
          if (!seg.finding) {
            return <span key={seg.index}>{seg.text}</span>
          }

          const f = seg.finding
          const isActive = activeId === f.rule_id
          const cls = `${HIGHLIGHT_CLASS[f.severity] ?? 'highlight-info'} ${isActive ? 'is-active' : ''}`

          return (
            <span
              key={seg.index}
              className={cls}
              data-rule-id={f.rule_id}
              onClick={() => onFindingClick(f)}
              onMouseEnter={(e) => handleHighlightMouseEnter(f, e.currentTarget)}
              onMouseLeave={handleHighlightMouseLeave}
            >
              {seg.text}
            </span>
          )
        })}
      </div>

      {tooltipFinding && (
        <Tooltip finding={tooltipFinding} anchorEl={tooltipAnchor} />
      )}
    </div>
  )
}
