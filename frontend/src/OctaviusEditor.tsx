import {
  Streamlit,
  StreamlitComponentBase,
  withStreamlitConnection,
} from "streamlit-component-lib"
import React, { ReactNode } from "react"

interface State {
  text: string
}

class OctaviusEditor extends StreamlitComponentBase<State> {
  public state = { text: "" }

  render() {
    // 1. Get data passed from Python
    const text = this.props.args["text"] || ""
    const highlights = this.props.args["highlights"] || []

    // 2. Render the text with highlights
    return (
      <div style={{ fontFamily: "sans-serif", padding: "10px" }}>
        <h3>Octavius Editor</h3>
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

  // Helper to slice text and wrap errors in red spans
  renderHighlightedText = (text: string, highlights: any[]): ReactNode[] => {
    if (!highlights || highlights.length === 0) return [text]

    let lastIndex = 0
    const nodes: ReactNode[] = []

    // Sort highlights by start position
    const sorted = [...highlights].sort((a, b) => a.start - b.start)

    sorted.forEach((h, i) => {
      // Push text before the error
      if (h.start > lastIndex) {
        nodes.push(text.slice(lastIndex, h.start))
      }

      // Push the error text (wrapped in style)
      nodes.push(
        <span
          key={i}
          style={{
            borderBottom: "2px solid #ff4b4b",
            backgroundColor: "rgba(255, 75, 75, 0.1)",
            cursor: "pointer"
          }}
          title={h.message} // Simple tooltip
        >
          {text.slice(h.start, h.end)}
        </span>
      )

      lastIndex = h.end
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

export default withStreamlitConnection(OctaviusEditor)
