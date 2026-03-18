"""Shared React component declaration for Octavius.

Declaring the component in a static utility module (rather than directly in
app.py or a pages/ file) ensures that ``inspect.getmodule()`` inside
``streamlit.components.v1.declare_component`` always receives a valid module
reference.  Calling ``declare_component`` from a dynamically-loaded pages/
file causes a ``RuntimeError: module is None`` on some Streamlit deployments
because the page runner has not fully registered the module before the call.
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"

_octavius_editor = components.declare_component(
    "octavius_editor",
    path=str(_BUILD_DIR),
)


def st_octavius_editor(
    text: str,
    findings: list,
    rules: list,
    key: str | None = None,
) -> dict | None:
    """Render the React visual editor and return the latest value dict."""
    return _octavius_editor(
        text=text,
        findings=findings,
        rules=rules,
        key=key,
        default=None,
    )
