import {
  Streamlit,
  StreamlitComponentBase,
  withStreamlitConnection,
} from "streamlit-component-lib"
import React, { ReactNode } from "react"

interface State {
  text: string
}

interface Finding {
  start_char: number
  end_char: number
  rule_id?: string
  message: string
  severity?: string
  suggestion?: string | null
}

class editor extends StreamlitComponentBase<State> {
  public state = { text: "" }

  render() {
    // 1. Get data passed from Python
    const text = this.props.args["text"] || ""
    const highlights = this.props.args["highlights"] || []

    // 2. Render the text with highlights
    return (
      <div style={{ fontFamily: "sans-serif", padding: "10px" }}>
        <h3>Octavius editor</h3>
        <div
          contentEditable={true}
          suppressContentEditableWarning={true}
          onInput={this.onTextInput}
          style={{
            border: "1px solid #ccc",
            padding: "15px",
            minHeight: "200px",
            borderRadius: "5px",
            whiteSpace: "pre-wrap",
            lineHeight: "1.6"
          }}
        >
          {this.renderHighlightedText(text, highlights)}
        </div>
      </div>
    )
  }

  // Helper to slice text and wrap findings in styled spans
  renderHighlightedText = (text: string, highlights: Finding[]): ReactNode[] => {
    if (!highlights || highlights.length === 0) return [text]

    let lastIndex = 0
    const nodes: ReactNode[] = []

    // Sort highlights by start position (Python schema uses start_char/end_char)
    const sorted = [...highlights].sort((a, b) => a.start_char - b.start_char)

    sorted.forEach((h, i) => {
      // Clamp ranges for safety
      const start = Math.max(0, Math.min(h.start_char, text.length))
      const end = Math.max(start, Math.min(h.end_char, text.length))

      // Push text before the finding
      if (start > lastIndex) {
        nodes.push(text.slice(lastIndex, start))
      }

      // Push the finding text (wrapped in style)
      nodes.push(
        <span
          key={i}
          style={{
            borderBottom: "2px solid #ff4b4b",
            backgroundColor: "rgba(255, 75, 75, 0.1)",
            cursor: "pointer"
          }}
          title={h.message}
        >
          {text.slice(start, end)}
        </span>
      )

      lastIndex = end
    })

    // Push remaining text
    if (lastIndex < text.length) {
      nodes.push(text.slice(lastIndex))
    }

    return nodes
  }

  // 3. Send updates back to Python when user types
  onTextInput = (e: any) => {
    const newText = e.target.innerText
    Streamlit.setComponentValue(newText)
  }
}

export default withStreamlitConnection(editor)
