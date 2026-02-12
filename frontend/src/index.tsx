import React from "react"
import ReactDOM from "react-dom/client"
import OctaviusEditor from "./Editor"

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement)
root.render(
  <React.StrictMode>
    <OctaviusEditor />
  </React.StrictMode>
)
