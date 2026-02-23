# logic/lint.py
import re
import spacy
from typing import List, Dict, Any, Optional, TypedDict
from spacy.tokens import Doc
from spacy.symbols import ORTH

# --- Global Logic Variables ---
try:
    nlp = spacy.load("en_core_web_sm")

    # Add semantic placeholders to tokenizer to prevent splitting them
    placeholder_texts = [
        "__SEMANTIC_ITALIC_START__", "__SEMANTIC_ITALIC_END__",
        "__SEMANTIC_BOLD_START__", "__SEMANTIC_BOLD_END__",
        "__SEMANTIC_CAPTION_START__", "__SEMANTIC_CAPTION_END__"
    ]
    for i in range(1, 7):
        placeholder_texts.append(f"__SEMANTIC_H{i}_START__")
        placeholder_texts.append(f"__SEMANTIC_H{i}_END__")

    for text in placeholder_texts:
        nlp.tokenizer.add_special_case(text, [{ORTH: text}])

except OSError:
    print("⚠️ Warning: spaCy model 'en_core_web_sm' not found. Run 'python -m spacy download en_core_web_sm'")
    nlp = None

def get_spacy_status() -> bool:
    """Returns True if the spaCy model is loaded."""
    return nlp is not None

class Finding(TypedDict):
    start_char: int
    end_char: int
    rule_id: str
    message: str
    severity: str
    suggestion: Optional[str]

# --- Helper Functions ---

def _add_finding(
    findings: List[Finding],
    start: int,
    end: int,
    rule_id: str,
    message: str,
    severity: str,
    suggestion: str = None
):
    """Adds a finding to the list, deduping based on exact character overlap."""
    for f in findings:
        if (
            f.get("start_char") == start
            and f.get("end_char") == end
            and f.get("rule_id") == rule_id
        ):
            return

    finding = {
        "start_char": start,
        "end_char": end,
        "rule_id": rule_id,
        "message": message,
        "severity": severity,
        "suggestion": suggestion
    }
    findings.append(finding)


# --- Heuristic Checks ---

def check_passive_voice(doc: Doc) -> List[Dict[str, Any]]:
    """
    Flags passive voice.
    Returns list of intermediate dicts with 'start_char', 'end_char', 'text'.
    """
    results: List[Dict[str, Any]] = []
    for token in doc:
        # Check for the auxiliary verb in a passive construction
        if token.dep_ == "auxpass":
            head = token.head

            # Combine the auxiliary token and its head verb into a single continuous span
            start_idx = min(token.idx, head.idx)
            end_idx = max(token.idx + len(token.text), head.idx + len(head.text))

            # Extract the actual text for the combined phrase
            phrase_text = doc.text[start_idx:end_idx]

            results.append({
                "start_char": start_idx,
                "end_char": end_idx,
                "text": phrase_text
            })

    return results


# Map of Heuristic IDs to Functions
HEURISTIC_FUNCTIONS = {
    "APS-GPC-Partsofsentences-H-009": check_passive_voice,
}


# --- Main Linting Function ---

def lint_text(text: str, rules: List[Dict[str, Any]]) -> List[Finding]:
    """
    The main entry point for the Web App.

    Args:
        text: The raw string to audit.
        rules: The list of rule dictionaries loaded from Trinity.json.

    Returns:
        list[Finding]: Findings in canonical format.
    """
    findings: List[Finding] = []

    if not nlp:
        return [{
            "start_char": 0,
            "end_char": 0,
            "rule_id": "SYSTEM-SPACY-NOT-LOADED",
            "message": "System Error: Language model not loaded.",
            "severity": "error",
            "suggestion": "Install spaCy model: python -m spacy download en_core_web_sm"
        }]

    doc = nlp(text)

    for rule in rules:
        rule_id = rule.get("id")
        severity = rule.get("severity", "info")
        message = rule.get("message", "Style violation found.")
        suggestion = rule.get("suggestion")
        category = rule.get("category")

        if category == "regex":
            pattern = rule.get("pattern")
            if pattern:
                try:
                    flags = re.MULTILINE
                    # Support both explicit (?i) and default case-insensitivity
                    if "(?i)" not in pattern:
                        flags |= re.IGNORECASE

                    for match in re.finditer(pattern, text, flags):
                        _add_finding(
                            findings,
                            match.start(),
                            match.end(),
                            rule_id,
                            message,
                            severity,
                            suggestion
                        )
                except re.error as e:
                    _add_finding(
                        findings,
                        0,
                        0,
                        f"SYS-REGEX-ERROR-{rule_id}",
                        f"Invalid regex pattern in rule {rule_id}: {e}",
                        "error",
                        "Check the 'pattern' field in Trinity.json for this rule."
                    )

        elif category == "heuristic":
            if rule_id in HEURISTIC_FUNCTIONS:
                logic_function = HEURISTIC_FUNCTIONS[rule_id]
                results = logic_function(doc)

                for res in results:
                    _add_finding(
                        findings,
                        res["start_char"],
                        res["end_char"],
                        rule_id,
                        message,
                        severity,
                        suggestion
                    )

    return sorted(findings, key=lambda x: x.get("start_char", 0))
