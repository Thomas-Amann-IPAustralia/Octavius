"""Shared Streamlit custom component declaration for Octavius editor.

Declared here (not inside pages/) so that inspect.getmodule() always
finds a properly registered module, avoiding the 'module is None' error
that occurs when components.declare_component() is called from a
dynamically-loaded pages/ file.
"""

from pathlib import Path
import streamlit.components.v1 as components

_BUILD_DIR = Path(__file__).parent / "frontend" / "build"

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
    return _octavius_editor(
        text=text,
        findings=findings,
        rules=rules,
        key=key,
        default=None,
    )
