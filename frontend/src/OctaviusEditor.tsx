import React, {
  useCallback, useEffect, useRef, useState,
} from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import { Extension } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import { Link } from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { Play, Sparkles, AlertCircle, AlertTriangle, Info } from 'lucide-react'

import { OctaviusDocument } from './runtime/document'
import { ReferenceBlock } from './runtime/nodes/referenceBlock'
import { applySentenceCaseHeading } from './runtime/mutations'
import { OctaviusToolbar } from './components/OctaviusToolbar'
import { DocumentOutline } from './components/DocumentOutline'
import { FindingsPanel } from './components/FindingsPanel'
import { RulesPanel } from './components/RulesPanel'
import { SeverityBadge } from './components/SeverityBadge'
import type { Finding, RuleMeta, PanelTab, Zone } from './types'

// ---------------------------------------------------------------------------
// Findings decoration plugin
// ---------------------------------------------------------------------------

interface FindingsPluginState {
  decorations: DecorationSet
}

const FINDINGS_KEY = new PluginKey<FindingsPluginState>('octavius-findings')

function buildDecorations(
  doc: import('@tiptap/pm/model').Node,
  findings: Finding[],
  octDoc: OctaviusDocument,
  activeFindingId: string | null,
): DecorationSet {
  const decos: Decoration[] = []
  for (const f of findings) {
    const pmFrom = octDoc.plainPosToPm(f.start_char)
    const pmTo = octDoc.plainPosToPm(f.end_char)
    if (pmFrom !== null && pmTo !== null && pmFrom < pmTo) {
      decos.push(
        Decoration.inline(pmFrom, pmTo, {
          class: `octavius-highlight octavius-highlight-${f.severity}${f.rule_id === activeFindingId ? ' is-active' : ''}`,
          'data-finding-id': f.rule_id,
        }),
      )
    }
  }
  return DecorationSet.create(doc, decos)
}

function makeFindingsPlugin(): Plugin {
  return new Plugin<FindingsPluginState>({
    key: FINDINGS_KEY,
    state: {
      init() { return { decorations: DecorationSet.empty } },
      apply(tr, prev) {
        const meta = tr.getMeta(FINDINGS_KEY)
        if (meta !== undefined) {
          const { findings, octDoc, activeFindingId } = meta as {
            findings: Finding[]
            octDoc: OctaviusDocument
            activeFindingId: string | null
          }
          return {
            decorations: buildDecorations(tr.doc, findings, octDoc, activeFindingId),
          }
        }
        return { decorations: prev.decorations.map(tr.mapping, tr.doc) }
      },
    },
    props: {
      decorations(state) {
        return FINDINGS_KEY.getState(state)?.decorations ?? DecorationSet.empty
      },
    },
  })
}

// ---------------------------------------------------------------------------
// Word import via mammoth
// ---------------------------------------------------------------------------

async function importWordDoc(file: File): Promise<string> {
  const mammoth = await import('mammoth')
  const arrayBuffer = await file.arrayBuffer()
  const result = await mammoth.convertToHtml(
    { arrayBuffer },
    {
      styleMap: [
        "p[style-name='Heading 1'] => h1:fresh",
        "p[style-name='Heading 2'] => h2:fresh",
        "p[style-name='Heading 3'] => h3:fresh",
        "p[style-name='Heading 4'] => h4:fresh",
        "p[style-name='Heading 5'] => h5:fresh",
        "p[style-name='Heading 6'] => h6:fresh",
      ],
      convertImage: mammoth.images.imgElement((_image) =>
        Promise.resolve({ src: '' })  // strip images for prose linting
      ),
    },
  )
  return result.value
}

// ---------------------------------------------------------------------------
// Word export via docx
//
// html-to-docx uses Node.js stream polyfills incompatible with CRA webpack 5.
// `docx` is a pure-browser library with a programmatic document-builder API.
// We parse the clean HTML string into a DOMParser tree and walk it to produce
// docx Paragraph / Table nodes; this is intentionally simpler than a full
// HTML-to-docx converter — it handles the document types Octavius produces.
// ---------------------------------------------------------------------------

async function exportWordDoc(html: string, filename = 'octavius-document.docx'): Promise<void> {
  const {
    Document, Packer, Paragraph, TextRun, HeadingLevel,
    Table: DocxTable, TableRow: DocxTableRow, TableCell: DocxTableCell,
    WidthType, AlignmentType,
  } = await import('docx')

  const dom = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html')
  const body = dom.body

  function textRunsFrom(el: Element): InstanceType<typeof TextRun>[] {
    const runs: InstanceType<typeof TextRun>[] = []
    el.childNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        runs.push(new TextRun(node.textContent ?? ''))
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = (node as Element).tagName.toLowerCase()
        const childRuns = textRunsFrom(node as Element)
        const text = (node as Element).textContent ?? ''
        if (tag === 'strong' || tag === 'b') {
          runs.push(new TextRun({ text, bold: true }))
        } else if (tag === 'em' || tag === 'i') {
          runs.push(new TextRun({ text, italics: true }))
        } else if (tag === 'code') {
          runs.push(new TextRun({ text, font: 'Courier New', size: 18 }))
        } else {
          runs.push(...childRuns)
        }
      }
    })
    return runs
  }

  function headingLevel(tag: string): (typeof HeadingLevel)[keyof typeof HeadingLevel] | undefined {
    const levels: Record<string, (typeof HeadingLevel)[keyof typeof HeadingLevel]> = {
      h1: HeadingLevel.HEADING_1, h2: HeadingLevel.HEADING_2, h3: HeadingLevel.HEADING_3,
      h4: HeadingLevel.HEADING_4, h5: HeadingLevel.HEADING_5, h6: HeadingLevel.HEADING_6,
    }
    return levels[tag]
  }

  const children: (InstanceType<typeof Paragraph> | InstanceType<typeof DocxTable>)[] = []

  function walk(el: Element) {
    const tag = el.tagName.toLowerCase()
    if (/^h[1-6]$/.test(tag)) {
      children.push(new Paragraph({ heading: headingLevel(tag), children: textRunsFrom(el) }))
    } else if (tag === 'p') {
      children.push(new Paragraph({ children: textRunsFrom(el) }))
    } else if (tag === 'ul' || tag === 'ol') {
      el.querySelectorAll('li').forEach((li, i) => {
        children.push(new Paragraph({
          bullet: tag === 'ul' ? { level: 0 } : undefined,
          numbering: tag === 'ol' ? { reference: 'default-numbering', level: 0, instance: i } : undefined,
          children: textRunsFrom(li),
        }))
      })
    } else if (tag === 'blockquote') {
      el.childNodes.forEach((c) => { if (c.nodeType === Node.ELEMENT_NODE) walk(c as Element) })
    } else if (tag === 'table') {
      const rows: InstanceType<typeof DocxTableRow>[] = []
      el.querySelectorAll('tr').forEach((tr) => {
        const cells: InstanceType<typeof DocxTableCell>[] = []
        tr.querySelectorAll('td, th').forEach((td) => {
          cells.push(new DocxTableCell({
            children: [new Paragraph({ children: textRunsFrom(td) })],
          }))
        })
        rows.push(new DocxTableRow({ children: cells }))
      })
      children.push(new DocxTable({ rows, width: { size: 100, type: WidthType.PERCENTAGE } }))
    } else if (tag === 'pre') {
      const text = el.textContent ?? ''
      text.split('\n').forEach((line) => {
        children.push(new Paragraph({
          children: [new TextRun({ text: line, font: 'Courier New', size: 18 })],
        }))
      })
    } else {
      el.childNodes.forEach((c) => { if (c.nodeType === Node.ELEMENT_NODE) walk(c as Element) })
    }
  }

  body.childNodes.forEach((c) => { if (c.nodeType === Node.ELEMENT_NODE) walk(c as Element) })

  const doc = new Document({ sections: [{ children }] })
  const blob = await Packer.toBlob(doc)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// API call
// ---------------------------------------------------------------------------

async function callCheck(
  plain_text: string,
  zones: Zone[],
): Promise<Finding[]> {
  const resp = await fetch('/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: plain_text, plain_text, zones }),
  })
  if (!resp.ok) throw new Error(`/check returned ${resp.status}`)
  const data: unknown[] = await resp.json()
  return data.map((d: any) => ({
    rule_id: d.rule_id,
    message: d.message ?? d.ui_flag ?? '',
    severity: d.severity,
    start_char: d.start_char ?? d.start ?? 0,
    end_char: d.end_char ?? d.end ?? 0,
    suggestion: d.suggestion ?? null,
    mutation_class: d.mutation_class ?? null,
    taxonomy: d.taxonomy,
    ui_flag: d.ui_flag,
    rule_summary: d.rule_summary,
    source_url: d.source_url,
    document_level: d.document_level,
    grouped_rules: d.grouped_rules,
  }))
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const DEBOUNCE_MS = 400
const PLACEHOLDER = 'Paste or type your text — analysis runs automatically…'

const OctaviusEditor: React.FC = () => {
  const [findings, setFindings] = useState<Finding[]>([])
  const [rules, setRules] = useState<RuleMeta[]>([])
  const [isAnalysing, setIsAnalysing] = useState(false)
  const [activeTab, setActiveTab] = useState<PanelTab>('issues')
  const [activeFindingId, setActiveFindingId] = useState<string | null>(null)
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set())
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [octDoc, setOctDoc] = useState<OctaviusDocument>(() => OctaviusDocument.empty())

  const fileInputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const octDocRef = useRef<OctaviusDocument>(octDoc)
  const findingsRef = useRef<Finding[]>(findings)
  const activeFindingIdRef = useRef<string | null>(activeFindingId)

  // Keep refs in sync
  useEffect(() => { octDocRef.current = octDoc }, [octDoc])
  useEffect(() => { findingsRef.current = findings }, [findings])
  useEffect(() => { activeFindingIdRef.current = activeFindingId }, [activeFindingId])

  // ---------------------------------------------------------------------------
  // Tiptap editor
  // ---------------------------------------------------------------------------

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        // We use @tiptap/extension-table separately
        heading: { levels: [1, 2, 3, 4, 5, 6] },
        code: {},
        codeBlock: { languageClassPrefix: '' },
      }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      Link.configure({ openOnClick: false, autolink: true }),
      Placeholder.configure({ placeholder: PLACEHOLDER }),
      ReferenceBlock,
      // Inject the findings decoration plugin via a proper Tiptap extension.
      Extension.create({
        name: 'findingsPlugin',
        priority: 1,
        addProseMirrorPlugins() { return [makeFindingsPlugin()] },
      }),
    ],
    content: '',
    onUpdate: ({ editor: ed }) => {
      const newOctDoc = OctaviusDocument.fromPMNode(ed.state.doc)
      setOctDoc(newOctDoc)
      scheduleLint(newOctDoc)
    },
  })

  // ---------------------------------------------------------------------------
  // Findings decoration sync
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!editor) return
    const tr = editor.state.tr.setMeta(FINDINGS_KEY, {
      findings,
      octDoc,
      activeFindingId,
    })
    editor.view.dispatch(tr)
  }, [findings, octDoc, activeFindingId, editor])

  // ---------------------------------------------------------------------------
  // Linting
  // ---------------------------------------------------------------------------

  const runLint = useCallback(async (doc: OctaviusDocument) => {
    const plain_text = doc.plainText
    if (!plain_text.trim()) {
      setFindings([])
      return
    }
    setIsAnalysing(true)
    try {
      const result = await callCheck(plain_text, doc.zones)
      setFindings(result)
    } catch (err) {
      console.error('Lint failed:', err)
    } finally {
      setIsAnalysing(false)
    }
  }, [])

  const scheduleLint = useCallback((doc: OctaviusDocument, immediate = false) => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (immediate) {
      runLint(doc)
    } else {
      debounceRef.current = setTimeout(() => runLint(doc), DEBOUNCE_MS)
    }
  }, [runLint])

  // Load rules on mount
  useEffect(() => {
    fetch('/rules')
      .then((r) => r.json())
      .then((data) => {
        const r: RuleMeta[] = data.map((d: any) => ({
          id: d.rule_id ?? d.id,
          title: d.rule_summary ?? d.title ?? d.rule_id,
          severity: d.severity ?? 'info',
          category: d.taxonomy,
        }))
        setRules(r)
      })
      .catch(() => {})
  }, [])

  // ---------------------------------------------------------------------------
  // Word import
  // ---------------------------------------------------------------------------

  const handleWordImport = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !editor) return
    e.target.value = ''  // reset input
    try {
      const html = await importWordDoc(file)
      editor.commands.setContent(html)
      const newDoc = OctaviusDocument.fromPMNode(editor.state.doc)
      setOctDoc(newDoc)
      scheduleLint(newDoc, true)
    } catch (err) {
      console.error('Word import failed:', err)
    }
  }, [editor, scheduleLint])

  // ---------------------------------------------------------------------------
  // Word export
  // ---------------------------------------------------------------------------

  const handleWordExport = useCallback(async () => {
    const html = octDoc.toCleanHTML()
    await exportWordDoc(html)
  }, [octDoc])

  // ---------------------------------------------------------------------------
  // Finding actions
  // ---------------------------------------------------------------------------

  const handleApplyFinding = useCallback((finding: Finding, replacement?: string) => {
    if (!editor) return

    const isPossibleSentenceCase =
      finding.mutation_class === 'safe_replace' &&
      finding.ui_flag?.toLowerCase().includes('sentence case')

    let newDoc: OctaviusDocument
    if (isPossibleSentenceCase) {
      newDoc = applySentenceCaseHeading(octDocRef.current, finding)
    } else {
      newDoc = octDocRef.current.applyFinding(finding, replacement)
    }

    if (newDoc === octDocRef.current) return  // no-op

    // Replace editor content with the mutated document
    editor.commands.setContent(newDoc.toJSON() as any, { emitUpdate: false })
    const updated = OctaviusDocument.fromPMNode(editor.state.doc)
    setOctDoc(updated)
    setFindings([])  // clear stale findings
    scheduleLint(updated, true)  // re-check immediately
  }, [editor, scheduleLint])

  const handleAcknowledgeFinding = useCallback((finding: Finding) => {
    const key = `${finding.rule_id}-${finding.start_char}`
    setAcknowledged((prev) => new Set([...prev, key]))
  }, [])

  // ---------------------------------------------------------------------------
  // Outline navigation
  // ---------------------------------------------------------------------------

  const handleHeadingClick = useCallback((plainOffset: number) => {
    if (!editor) return
    const pmPos = octDocRef.current.plainPosToPm(plainOffset)
    if (pmPos === null) return
    editor.commands.focus()
    editor.view.dispatch(
      editor.view.state.tr.setSelection(
        // Set cursor to start of heading
        (editor.view.state.selection.constructor as any).near(
          editor.view.state.doc.resolve(pmPos)
        )
      )
    )
    const domPos = editor.view.domAtPos(pmPos)
    domPos?.node?.parentElement?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [editor])

  // ---------------------------------------------------------------------------
  // Paste handler — mammoth-style cleanup
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!editor) return
    // Tiptap's built-in HTML paste handling is used; we don't need custom cleanup
    // since StarterKit parses HTML into ProseMirror nodes automatically.
  }, [editor])

  // ---------------------------------------------------------------------------
  // Stats
  // ---------------------------------------------------------------------------

  const errors = findings.filter((f) => f.severity === 'error').length
  const warns  = findings.filter((f) => f.severity === 'warn').length
  const infos  = findings.filter((f) => f.severity === 'info').length
  const zones  = octDoc.zones

  const TABS: { id: PanelTab; label: string; count?: number }[] = [
    { id: 'issues', label: 'Issues', count: findings.length },
    { id: 'rules',  label: 'Rules',  count: rules.length   },
    { id: 'outline', label: 'Outline', count: zones.filter((z) => z.kind === 'heading').length },
  ]

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div
      className="flex flex-col bg-slate-50 rounded-2xl overflow-hidden border border-slate-200 shadow-sm"
      style={{ fontFamily: '"Plus Jakarta Sans", Inter, system-ui, sans-serif', minHeight: 560 }}
    >
      {/* ── Header ── */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-white flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm">
            <Sparkles size={14} className="text-white" />
          </div>
          <span className="text-sm font-bold text-slate-800 tracking-tight">Octavius</span>
        </div>

        <div className="flex items-center gap-2">
          {errors > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-rose-50 text-rose-600 text-xs font-semibold ring-1 ring-rose-200">
              <AlertCircle size={11} />{errors}E
            </span>
          )}
          {warns > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 text-amber-600 text-xs font-semibold ring-1 ring-amber-200">
              <AlertTriangle size={11} />{warns}W
            </span>
          )}
          {infos > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-violet-50 text-violet-600 text-xs font-semibold ring-1 ring-violet-200">
              <Info size={11} />{infos}I
            </span>
          )}

          <button
            onClick={() => scheduleLint(octDoc, true)}
            disabled={isAnalysing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700
              disabled:opacity-60 disabled:cursor-not-allowed
              text-white text-xs font-semibold shadow-sm transition-all duration-150 active:scale-95"
          >
            <Play size={12} className={isAnalysing ? 'animate-spin' : ''} />
            {isAnalysing ? 'Analysing…' : 'Analyse'}
          </button>
        </div>
      </header>

      {/* ── Toolbar ── */}
      <OctaviusToolbar
        editor={editor}
        onWordImport={handleWordImport}
        onWordExport={handleWordExport}
      />

      {/* Hidden file input for Word import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".docx"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 440 }}>

        {/* Left: Editor */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-slate-200 bg-white">
          <EditorContent
            editor={editor}
            className="flex-1 overflow-y-auto p-5 prose prose-sm max-w-none octavius-editor-tiptap custom-scroll"
          />
        </div>

        {/* Right: Findings + Rules + Outline */}
        <div className="w-80 flex-shrink-0 flex flex-col bg-white overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-slate-100 px-4 pt-2 gap-1 flex-wrap">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-t-lg
                  transition-colors duration-150 border-b-2
                  ${activeTab === tab.id
                    ? 'text-brand-700 border-brand-600 bg-brand-50/50'
                    : 'text-slate-500 border-transparent hover:text-slate-700 hover:bg-slate-50'
                  }`}
              >
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] leading-none
                    ${activeTab === tab.id ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500'}`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-hidden">
            {activeTab === 'issues' && (
              <FindingsPanel
                findings={findings}
                activeId={activeFindingId}
                onFindingClick={(f) => setActiveFindingId(f.rule_id)}
                onApply={handleApplyFinding}
                onAcknowledge={handleAcknowledgeFinding}
                acknowledged={acknowledged}
              />
            )}
            {activeTab === 'rules' && (
              <RulesPanel
                rules={rules}
                activeRuleIds={new Set(rules.map((r) => r.id))}
                onToggle={() => {}}
              />
            )}
            {activeTab === 'outline' && (
              <div className="h-full overflow-y-auto custom-scroll">
                <p className="px-4 py-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wide">
                  Headings
                </p>
                <DocumentOutline
                  zones={zones}
                  onHeadingClick={handleHeadingClick}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default OctaviusEditor
