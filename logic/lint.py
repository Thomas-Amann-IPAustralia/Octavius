# logic/lint.py
import re
import spacy
from typing import List, Dict, Any, Pattern
from spacy.tokens import Doc
from spacy.matcher import Matcher
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

# --- Helper Functions ---

def _add_finding(findings: List[Dict], start: int, end: int, rule_id: str, message: str, severity: str, suggestion: str = None):
    """Adds a finding to the list, deduping based on exact character overlap."""
    for f in findings:
        if f['start'] == start and f['end'] == end and f['ruleId'] == rule_id:
            return

    finding = {
        "start": start,
        "end": end,
        "ruleId": rule_id,
        "message": message,
        "severity": severity,
        "suggestion": suggestion
    }
    findings.append(finding)

# --- Heuristic Checks ---

def check_passive_voice(doc: Doc) -> List[Dict[str, Any]]:
    """Flags passive voice. Returns list of dicts with 'start', 'end', 'text'."""
    results = []
    for token in doc:
        # Check for the auxiliary verb in a passive construction (e.g., 'was' in 'was submitted')
        if token.dep_ == "auxpass":
            # 1. Flag the auxiliary itself ("was")
            results.append({"start": token.idx, "end": token.idx + len(token.text), "text": token.text})
            
            # 2. Flag the main verb ("submitted"), which is the parent (head) of the auxiliary
            head = token.head
            results.append({"start": head.idx, "end": head.idx + len(head.text), "text": head.text})
            
    return results

# Map of Heuristic IDs to Functions
HEURISTIC_FUNCTIONS = {
    "APS-GPC-Partsofsentences-H-009": check_passive_voice,
}

# --- Main Linting Function ---

def lint_text(text: str, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    The main entry point for the Web App.
    Args:
        text: The raw string to audit.
        rules: The list of rule dictionaries loaded from Trinity.json.
    Returns:
        A list of findings with 'start', 'end', 'message', etc.
    """
    findings = []
    
    if not nlp:
        return [{"message": "System Error: Language model not loaded.", "severity": "error", "start": 0, "end": 0}]

    doc = nlp(text)

    for rule in rules:
        rule_id = rule.get("id")
        severity = rule.get("severity", "info")
        message = rule.get("message", "Style violation found.")
        category = rule.get("category")

        if category == "regex":
            pattern = rule.get("pattern")
            if pattern:
                try:
                    flags = re.MULTILINE
                    if "(?i)" not in pattern:
                        flags |= re.IGNORECASE
                    
                    for match in re.finditer(pattern, text, flags):
                        _add_finding(findings, match.start(), match.end(), rule_id, message, severity)
                except re.error:
                    continue 

        elif category == "heuristic":
            if rule_id in HEURISTIC_FUNCTIONS:
                logic_function = HEURISTIC_FUNCTIONS[rule_id]
                results = logic_function(doc)
                
                for res in results:
                    _add_finding(findings, res['start'], res['end'], rule_id, message, severity)

    return sorted(findings, key=lambda x: x['start'])
