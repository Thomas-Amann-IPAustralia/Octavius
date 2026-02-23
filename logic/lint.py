# logic/lint.py
import re
import spacy
from typing import List, Dict, Any, Optional, TypedDict, Callable
from spacy.tokens import Doc, Span, Token
from spacy.matcher import Matcher
from spacy.symbols import ORTH

# --- Global Logic Variables ---
nlp = None
matcher_for_example = None
matcher_parliamentary = None
matcher_acronym_def = None
matcher_list_intro = None

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

    # Initialize Global Matchers
    matcher_for_example = Matcher(nlp.vocab)
    matcher_for_example.add("FOR_EXAMPLE", [[{"LOWER": "for"}, {"LOWER": "example"}]])

    matcher_parliamentary = Matcher(nlp.vocab)
    formal_names = {
        "FORMAL_PH": [{"LOWER": "parliament"}, {"LOWER": "house"}],
        "FORMAL_PL": [{"LOWER": "parliamentary"}, {"LOWER": "library"}],
        "FORMAL_S": [{"LOWER": "the"}, {"LOWER": "senate"}],
        "FORMAL_HR": [{"LOWER": "the"}, {"LOWER": "house"}, {"LOWER": "of"}, {"LOWER": "representatives"}],
    }
    generic_terms = {
        "GENERIC_PP": [{"TEXT": "Parliamentary"}, {"TEXT": "Procedures"}],
        "GENERIC_MP": [{"TEXT": "Member"}, {"TEXT": "of"}, {"TEXT": "Parliament"}],
        "GENERIC_HP": [{"TEXT": "Houses"}, {"TEXT": "of"}, {"TEXT": "Parliament"}],
    }
    for key, pattern in formal_names.items():
        matcher_parliamentary.add(key, [pattern])
    for key, pattern in generic_terms.items():
        matcher_parliamentary.add(key, [pattern])

    matcher_acronym_def = Matcher(nlp.vocab)
    matcher_acronym_def.add("ACRONYM_DEF", [[{"POS": "PROPN", "OP": "+"}, {"TEXT": "("}, {"IS_UPPER": True, "LENGTH": {">=": 2}}, {"TEXT": ")"}]])

    matcher_list_intro = Matcher(nlp.vocab)
    matcher_list_intro.add("LIST_INTRO", [[{"LOWER": "such"}, {"LOWER": "as"}], [{"LOWER": "for"}, {"LOWER": "example"}], [{"LOWER": "including"}]])

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

# --- Global Constants ---
MONTHS = {
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
}
AU_STATE_SHORT_FORMS = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}
SPELLED_NUMS_GT_ONE = {
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty"
}

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
    """Flags passive voice (Rule: APS-GPC-Partsofsentences-H-009)."""
    results: List[Dict[str, Any]] = []
    for token in doc:
        if token.dep_ == "auxpass":
            head = token.head
            start_idx = min(token.idx, head.idx)
            end_idx = max(token.idx + len(token.text), head.idx + len(head.text))
            results.append({
                "start_char": start_idx,
                "end_char": end_idx,
                "text": doc.text[start_idx:end_idx]
            })
    return results

def check_complete_sentence(doc: Doc) -> List[Dict[str, Any]]:
    """Heuristic to check for potential sentence fragments (Rule: APS-GPC-Partsofsentences-H-001)."""
    results = []
    for sent in doc.sents:
        has_root = any(token.dep_ == "ROOT" for token in sent)
        has_subject = any("subj" in token.dep_ for token in sent)
        if not (has_root and has_subject) and len(sent.text.strip().split()) > 3:
            results.append({
                "start_char": sent.start_char,
                "end_char": sent.end_char,
                "text": sent.text
            })
    return results

def check_collective_noun_agreement(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for plural verbs with typically singular collective nouns (Rule: APS-GPC-Nouns-R-004)."""
    results = []
    collective_nouns = {"government", "committee", "crowd", "team", "family", "group", "staff"}
    plural_verbs = {"are", "were", "have", "do"}
    for token in doc:
        if token.lemma_.lower() in collective_nouns:
            verb = token.head
            if verb.text.lower() in plural_verbs:
                results.append({
                    "start_char": token.idx,
                    "end_char": verb.idx + len(verb.text),
                    "text": f"{token.text} {verb.text}"
                })
            else:
                for child in verb.children:
                    if child.dep_ in ("aux", "auxpass") and child.text.lower() in plural_verbs:
                        results.append({
                            "start_char": token.idx,
                            "end_char": child.idx + len(child.text),
                            "text": f"{token.text} {child.text}"
                        })
                        break
    return results

def check_hyphenated_modifier(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for unhyphenated compound modifiers before a noun (Rule: APS-GPC-Adjectives-H-002)."""
    results = []
    for i in range(len(doc) - 2):
        token1, token2, token3 = doc[i], doc[i+1], doc[i+2]
        is_potential_compound = (token1.pos_ in ['ADJ', 'ADV']) and (token2.pos_ in ['NOUN', 'ADJ', 'VERB'])
        is_before_noun = token3.pos_ == 'NOUN'
        if is_potential_compound and is_before_noun and token2.head == token3 and token1.head == token2:
            results.append({
                "start_char": token1.idx,
                "end_char": token2.idx + len(token2.text),
                "text": f"{token1.text} {token2.text}"
            })
    return results

def check_that_vs_which(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for 'which' without a preceding comma (Rule: APS-GPC-Pronouns-H-005)."""
    results = []
    for i, token in enumerate(doc):
        if token.text.lower() == 'which' and i > 0 and doc[i-1].text != ',':
            if token.dep_ == 'relcl':
                results.append({
                    "start_char": token.idx,
                    "end_char": token.idx + len(token.text),
                    "text": token.text
                })
    return results

def check_missing_determiner(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for singular countable nouns used as subjects missing a determiner (Rule: APS-GPC-Nouns-H-001)."""
    results = []
    for token in doc:
        if token.pos_ == 'NOUN' and token.tag_ == 'NN' and 'subj' in token.dep_:
            children_deps = {child.dep_ for child in token.children}
            if 'det' not in children_deps and 'poss' not in children_deps:
                results.append({
                    "start_char": token.idx,
                    "end_char": token.idx + len(token.text),
                    "text": token.text
                })
    return results

def check_exclamation_marks(doc: Doc) -> List[Dict[str, Any]]:
    """Flags any use of exclamation marks in formal text (Rule: APS-GPC-Exclamationmarks-H-001)."""
    results = []
    for token in doc:
        if token.text == '!':
            results.append({
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "text": token.text
            })
    return results

def check_matched_correlatives(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for mismatched correlative conjunctions (Rule: APS-GPC-Conjunctions-H-001)."""
    results = []
    text = doc.text.lower()
    if ('either' in text and 'nor' in text) or ('neither' in text and 'or' in text):
        for sent in doc.sents:
            sent_text = sent.text.lower()
            if ('either' in sent_text and 'nor' in sent_text) or ('neither' in sent_text and 'or' in sent_text):
                results.append({
                    "start_char": sent.start_char,
                    "end_char": sent.end_char,
                    "text": sent.text
                })
    return results

def check_prefer_english_forms(doc: Doc) -> List[Dict[str, Any]]:
    """Flags common Latin abbreviations (Rule: APS-GPC-Latinshortenedforms-H-001)."""
    results = []
    latin_forms = {'e.g.', 'i.e.', 'etc.'}
    for token in doc:
        if token.text.lower() in latin_forms:
            results.append({
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "text": token.text
            })
    return results

def check_unique_grading(doc: Doc) -> List[Dict[str, Any]]:
    """Flags phrases that grade the absolute adjective 'unique' (Rule: APS-GPC-Adjectives-R-002)."""
    results = []
    graders = {"very", "more", "most", "less", "least", "extremely", "highly", "quite"}
    for i, token in enumerate(doc):
        if token.lemma_.lower() == "unique" and i > 0:
            if doc[i-1].lemma_.lower() in graders:
                results.append({
                    "start_char": doc[i-1].idx,
                    "end_char": token.idx + len(token.text),
                    "text": f"{doc[i-1].text} {token.text}"
                })
    return results

def check_misplaced_only(doc: Doc) -> List[Dict[str, Any]]:
    """Flags the word 'only' to prompt a manual review (Rule: APS-GPC-Typesofwords-H-002)."""
    results = []
    for token in doc:
        if token.lemma_.lower() == "only":
            results.append({
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "text": token.text
            })
    return results

def check_filler_adverbs(doc: Doc) -> List[Dict[str, Any]]:
    """Flags common unnecessary adverbs (Rule: APS-GPC-Adverbs-H-001)."""
    results = []
    filler_adverbs = {"very", "really", "quite", "extremely", "highly", "absolutely", "totally", "actually", "basically", "literally"}
    for token in doc:
        if token.lemma_.lower() in filler_adverbs:
            results.append({
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "text": token.text
            })
    return results

def check_modal_verb_to(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for the incorrect use of 'to' after a modal verb (Rule: APS-GPC-Verbs-R-007)."""
    results = []
    for i in range(len(doc) - 1):
        token = doc[i]
        next_token = doc[i+1]
        if token.tag_ == 'MD' and next_token.lemma_.lower() == 'to':
            results.append({
                "start_char": token.idx,
                "end_char": next_token.idx + len(next_token.text),
                "text": f"{token.text} {next_token.text}"
            })
    return results

def check_improper_reflexive_pronoun(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for reflexive pronouns used incorrectly as a subject (Rule: APS-GPC-Pronouns-H-004)."""
    results = []
    for token in doc:
        is_reflexive = token.text.lower().endswith(('self', 'selves'))
        if is_reflexive and "subj" in token.dep_:
            results.append({
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "text": token.text
            })
    return results

def check_a_vs_an(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for incorrect use of 'a' vs 'an' (Covers rules APS-GPC-Determiners-R-001 to R-006)."""
    results = []
    vowel_sounds = 'aeiou'
    u_exceptions = {'university', 'universal', 'unique', 'user', 'unit'}
    h_exceptions = {'hour', 'honor', 'honour', 'honest', 'heir'}
    initialism_exceptions = {'f', 'h', 'l', 'm', 'n', 'r', 's', 'x'}

    for i in range(len(doc) - 1):
        det = doc[i]
        next_word = doc[i+1]

        if det.lemma_.lower() not in ['a', 'an']:
            continue

        next_word_lower = next_word.text.lower()
        starts_with_vowel_sound = False

        if next_word.pos_ == 'NOUN' and all(c.isupper() for c in next_word.text if c.isalpha()):
            if next_word_lower[0] in initialism_exceptions:
                starts_with_vowel_sound = True
        elif next_word_lower.startswith('h') and any(next_word_lower.startswith(ex) for ex in h_exceptions):
             starts_with_vowel_sound = True
        elif next_word_lower.startswith('u') and any(next_word_lower.startswith(ex) for ex in u_exceptions):
            starts_with_vowel_sound = False
        elif next_word_lower[0] in vowel_sounds:
            starts_with_vowel_sound = True

        if det.lemma_.lower() == 'an' and not starts_with_vowel_sound:
            results.append({
                "start_char": det.idx,
                "end_char": next_word.idx + len(next_word.text),
                "text": f"{det.text} {next_word.text}"
            })
        elif det.lemma_.lower() == 'a' and starts_with_vowel_sound:
            results.append({
                "start_char": det.idx,
                "end_char": next_word.idx + len(next_word.text),
                "text": f"{det.text} {next_word.text}"
            })
    return results

def check_generic_organisation_reference(doc: Doc) -> List[Dict[str, Any]]:
    """Flags capitalized generic organisation types (Rule: APS-GPC-Organisationnames-H-007)."""
    results = []
    generic_types = {"Department", "Agency", "University", "Company", "Council", "Commission", "Authority", "Summit", "Academy"}
    for token in doc:
        if token.text in generic_types and token.i > 0 and doc[token.i-1].text.lower() == 'the':
            is_formal_name = False
            if token.i < len(doc) - 2 and doc[token.i + 1].text.lower() == 'of' and doc[token.i + 2].pos_ == 'PROPN':
                is_formal_name = True
            if not is_formal_name:
                results.append({
                    "start_char": token.idx,
                    "end_char": token.idx + len(token.text),
                    "text": token.text
                })
    return results

def check_generic_official_titles(doc: Doc) -> List[Dict[str, Any]]:
    """Flags capitalized official titles used in a generic context."""
    results = []
    titles = {"Government", "Minister", "Secretary", "Premier", "Treasurer", "Mayor",
              "President", "Speaker", "Chancellor", "Governor"}
    for token in doc:
        if token.text in titles and not token.is_sent_start:
            is_formal_use = False
            if token.i < len(doc) - 1 and doc[token.i + 1].pos_ == 'PROPN' and doc[token.i + 1].ent_type_ == 'PERSON':
                is_formal_use = True
            if any(child.dep_ == 'amod' for child in token.children):
                is_formal_use = True
            if not is_formal_use:
                results.append({
                    "start_char": token.idx,
                    "end_char": token.idx + len(token.text),
                    "text": token.text
                })
    return results

def check_generic_parliamentary_terms(doc: Doc) -> List[Dict[str, Any]]:
    """Flags incorrect capitalization of specific parliamentary terms."""
    results = []
    if matcher_parliamentary is None: return []

    matches = matcher_parliamentary(doc)
    # Re-access formal_names for correction logic
    formal_names_text = {
        "FORMAL_PH": "Parliament House", "FORMAL_PL": "Parliamentary Library",
        "FORMAL_S": "the Senate", "FORMAL_HR": "the House of Representatives",
    }
    for match_id, start, end in matches:
        span = doc[start:end]
        rule_name = nlp.vocab.strings[match_id]
        if rule_name.startswith("FORMAL_"):
            if span.text != formal_names_text[rule_name]:
                results.append({"start_char": span.start_char, "end_char": span.end_char, "text": span.text})
        elif rule_name.startswith("GENERIC_"):
            if not span.is_sent_start:
                results.append({"start_char": span.start_char, "end_char": span.end_char, "text": span.text})
    return results

def check_capitalized_common_noun_definitions(doc: Doc) -> List[Dict[str, Any]]:
    """Flags acronym definitions where the full term is capitalized but contains no proper nouns."""
    results = []
    for i, token in enumerate(doc):
        if token.text == '(' and i < len(doc) - 2 and doc[i+1].is_upper and doc[i+2].text == ')':
            start_of_term_index = -1
            for j in range(i - 1, -1, -1):
                if doc[j].pos_ not in ('NOUN', 'ADJ', 'CCONJ', 'ADP'):
                    start_of_term_index = j + 1
                    break
            if start_of_term_index == -1: start_of_term_index = 0
            term_span = doc[start_of_term_index:i]
            if len(term_span) > 0 and not term_span[0].is_sent_start and term_span[0].is_title:
                has_proper_noun = any(t.pos_ == 'PROPN' for t in term_span)
                if not has_proper_noun:
                    results.append({"start_char": term_span.start_char, "end_char": term_span.end_char, "text": term_span.text})
    return results

def check_capitalized_the_before_country(doc: Doc) -> List[Dict[str, Any]]:
    """Flags capitalized 'The' before a country name mid-sentence."""
    results = []
    for token in doc:
        if token.text == "The" and not token.is_sent_start:
            if token.i < len(doc) - 1:
                next_token = doc[token.i + 1]
                if next_token.ent_type_ == 'GPE':
                    results.append({"start_char": token.idx, "end_char": token.idx + 3, "text": "The"})
    return results

def check_improperly_cased_regions(doc: Doc) -> List[Dict[str, Any]]:
    """Flags capitalized compass directions for generic regions."""
    results = []
    compass_adjectives = {"Northern", "Southern", "Eastern", "Western"}
    for token in doc:
        if token.text in compass_adjectives and token.pos_ == 'ADJ':
            if token.head.ent_type_ == 'GPE' and token.ent_type_ != 'GPE':
                 results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_org_the_capitalisation(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for 'The [Proper Noun]' mid-sentence (Rule: APS-GPC-Organisationnames-H-008)."""
    results = []
    for i in range(len(doc) - 1):
        token = doc[i]
        if token.text == "The" and not token.is_sent_start:
            next_token = doc[i+1]
            is_org_name = False
            if next_token.pos_ == 'PROPN':
                is_org_name = True
            elif next_token.pos_ == 'ADJ' and i + 2 < len(doc) and doc[i+2].pos_ == 'PROPN':
                is_org_name = True
            if is_org_name:
                results.append({"start_char": token.idx, "end_char": token.idx + 3, "text": "The"})
    return results

def check_org_verb_agreement(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for organization names using plural verbs (Rule: APS-GPC-Organisationnames-H-010)."""
    results = []
    plural_verbs = {"are", "were", "have", "do"}
    for token in doc:
        if token.dep_ == 'nsubj' and token.pos_ == 'PROPN':
            verb = token.head
            if verb.text.lower() in plural_verbs:
                has_conjunction = any(child.dep_ == 'conj' for child in token.children)
                if not has_conjunction:
                    results.append({
                        "start_char": token.idx,
                        "end_char": verb.idx + len(verb.text),
                        "text": f"{token.text} {verb.text}"
                    })
    return results

def check_numerals_vs_words(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for spelled-out numbers 2 and above (Rule: APS-GPC-Choosingnumeralsorwords-H-001)."""
    results = []
    for token in doc:
        if token.pos_ == 'NUM' and token.lemma_.lower() in SPELLED_NUMS_GT_ONE:
            results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_large_rounded_numbers(doc: Doc) -> List[Dict[str, Any]]:
    """Flags large, round numbers that could be written as '2.5 million' (Rule: APS-GPC-Choosingnumeralsorwords-H-009)."""
    results = []
    for token in doc:
        if token.pos_ == 'NUM' and token.like_num and ',' in token.text:
            text = token.text.replace(',', '')
            if text.isdigit():
                val = int(text)
                suggestion = ""
                if val >= 1_000_000_000 and val % 100_000_000 == 0:
                    suggestion = f"{val / 1_000_000_000:g} billion"
                elif val >= 1_000_000 and val % 100_000 == 0:
                    suggestion = f"{val / 1_000_000:g} million"
                if suggestion:
                    results.append({
                        "start_char": token.idx,
                        "end_char": token.idx + len(token.text),
                        "text": token.text,
                        "suggestion": suggestion
                    })
    return results

def check_aud_currency(doc: Doc) -> List[Dict[str, Any]]:
    """Flags use of 'A$' or 'AUD' (Rule: APS-GPC-Currency-H-001)."""
    results = []
    for token in doc:
        if token.pos_ == 'NUM' and token.like_num:
            for child in token.lefts:
                if child.text in ["A$", "AUD"]:
                    results.append({"start_char": child.idx, "end_char": token.idx + len(token.text), "text": f"{child.text}{token.text}"})
    return results

def check_ambiguous_dollar_sign(doc: Doc) -> List[Dict[str, Any]]:
    """Flags lone '$' symbols (Rule: APS-GPC-Currency-H-002)."""
    results = []
    for i, token in enumerate(doc):
        if token.text == '$':
            is_qualified = i > 0 and doc[i - 1].text.upper() in ['A', 'US', 'NZ', 'C']
            is_followed_by_num = i < len(doc) - 1 and doc[i + 1].like_num
            if is_followed_by_num and not is_qualified:
                results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "$"})
    return results

def check_year_span_words(doc: Doc) -> List[Dict[str, Any]]:
    """Flags 'YYYY–YYYY' spans (Rule: APS-GPC-Datesandtime-H-001)."""
    results = []
    for i in range(len(doc) - 2):
        t1, t2, t3 = doc[i], doc[i+1], doc[i+2]
        if t1.like_num and len(t1.text) == 4 and t2.text == '–' and t3.like_num and len(t3.text) == 4:
            is_exception = False
            if i < len(doc) - 4:
                t4, t5 = doc[i+3], doc[i+4]
                if t4.lemma_ in ['financial', 'calendar'] and t5.lemma_ == 'year':
                    is_exception = True
            if not is_exception:
                results.append({"start_char": t1.idx, "end_char": t3.idx + len(t3.text), "text": f"{t1.text}–{t3.text}"})
    return results

def check_financial_year_dash(doc: Doc) -> List[Dict[str, Any]]:
    """Flags 'YYYY to YY' or 'YYYY-YY' for financial/calendar years (Rule: APS-GPC-Datesandtime-H-002)."""
    results = []
    for i in range(len(doc) - 3):
        t1, t2, t3, t4 = doc[i], doc[i+1], doc[i+2], doc[i+3]
        is_year_span = (t1.like_num and len(t1.text) == 4 and (t2.lemma_ == 'to' or t2.text == '-') and t3.like_num and (len(t3.text) in [2, 4]))
        is_specified_type = t4.lemma_ in ['financial', 'calendar']
        if is_year_span and is_specified_type:
            results.append({"start_char": t1.idx, "end_char": t4.idx + len(t4.text), "text": f"{t1.text} {t2.text} {t3.text} {t4.text}"})
    return results

def check_day_month_span_words(doc: Doc) -> List[Dict[str, Any]]:
    """Flags 'D–D Month' spans (Rule: APS-GPC-Datesandtime-H-003)."""
    results = []
    for i in range(len(doc) - 3):
        t1, t2, t3, t4 = doc[i], doc[i+1], doc[i+2], doc[i+3]
        if t1.like_num and t2.text == '–' and t3.like_num and t4.text in MONTHS:
            results.append({"start_char": t1.idx, "end_char": t4.idx + len(t4.text), "text": f"{t1.text}–{t3.text} {t4.text}"})
    return results

def check_worded_decimals(doc: Doc) -> List[Dict[str, Any]]:
    """Flags decimals written as words (Rule: APS-GPC-Fractionsanddecimals-H-001)."""
    results = []
    for i in range(len(doc) - 2):
        t1, t2, t3 = doc[i], doc[i+1], doc[i+2]
        if t1.pos_ == 'NUM' and t2.lemma_ == 'point' and t3.pos_ == 'NUM':
            results.append({"start_char": t1.idx, "end_char": t3.idx + len(t3.text), "text": f"{t1.text} {t2.text} {t3.text}"})
    return results

def check_prose_ordinals_for_steps(doc: Doc) -> List[Dict[str, Any]]:
    """Flags ordinals used in prose for steps (Rule: APS-GPC-Ordinalnumbers-H-001)."""
    results = []
    ordinal_lemmas = {'first', 'second', 'third', 'firstly', 'secondly', 'thirdly'}
    for i, token in enumerate(doc):
        if token.lemma_.lower() in ordinal_lemmas:
            if token.lemma_.endswith('ly') or token.pos_ == 'ADV':
                results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
            elif token.pos_ == 'ADJ' and i < len(doc) - 1 and doc[i+1].lemma_ == 'step':
                results.append({"start_char": token.idx, "end_char": doc[i+1].idx + len(doc[i+1].text), "text": f"{token.text} {doc[i+1].text}"})
    return results

def check_compound_clause_comma(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for missing commas before conjunctions (Rule: APS-GPC-Partsofsentences-H-005)."""
    results = []
    conjunctions = {'and', 'or', 'but', 'so'}
    for token in doc:
        if token.lemma_ in conjunctions and token.dep_ == 'cc':
            verb1 = token.head
            if verb1.pos_ != 'VERB': continue
            verb2 = next((child for child in verb1.children if child.dep_ == 'conj'), None)
            if verb2 and verb2.pos_ == 'VERB':
                subj1 = next((child for child in verb1.children if 'subj' in child.dep_), None)
                subj2 = next((child for child in verb2.children if 'subj' in child.dep_), None)
                if subj1 and subj2 and subj1.lemma_.lower() != subj2.lemma_.lower():
                    if doc[token.i - 1].text != ',':
                        results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_comma_with_shared_subject(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for comma before conjunction with shared subject (Rule: APS-GPC-Partsofsentences-H-006)."""
    results = []
    for token in doc:
        if token.dep_ == 'cc' and token.i > 0:
            verb2 = token.head
            subj2_list = [c for c in verb2.children if 'nsubj' in c.dep_]
            verb1_list = [c for c in verb2.conjuncts if c.i < token.i]
            if not subj2_list and verb1_list:
                verb1 = verb1_list[0]
                if any('nsubj' in c.dep_ for c in verb1.children):
                    if doc[token.i - 1].text == ',':
                        results.append({"start_char": token.idx - 1, "end_char": token.idx, "text": ","})
    return results

def check_passive_missing_agent(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for passive voice missing an agent (Rule: APS-GPC-Partsofsentences-H-010)."""
    results = []
    for sent in doc.sents:
        is_passive = any(t.dep_ in ("nsubjpass", "auxpass") for t in sent)
        has_agent = any(t.dep_ == 'agent' for t in sent)
        if is_passive and not has_agent:
            results.append({"start_char": sent.start_char, "end_char": sent.end_char, "text": sent.text})
    return results

def check_possessive_in_compound(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for possessive markers not at end of compound (Rule: APS-GPC-Phrases-H-001)."""
    results = []
    for token in doc:
        if token.text == '-' and token.dep_ == 'punct' and token.i > 0:
            prev_token = doc[token.i - 1]
            if prev_token.text.endswith(("'s", "’s")):
                 results.append({"start_char": prev_token.idx, "end_char": prev_token.idx + len(prev_token.text), "text": prev_token.text})
    return results

def check_descriptive_apostrophe(doc: Doc) -> List[Dict[str, Any]]:
    """Flags plural possessives used for descriptive phrases (Rule: APS-GPC-Apostrophes-H-001)."""
    results = []
    for token in doc:
        if token.dep_ == 'poss' and token.text.endswith(("s'", "s’")):
            results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_nested_parentheses(doc: Doc) -> List[Dict[str, Any]]:
    """Check for nested round parentheses (Rule: APS-GPC-Bracketsandparentheses-H-003)."""
    results = []
    for token in doc:
        if token.text == '(':
            head = token.head
            if head.head != head:
                ancestor = head.head
                if any(child.text == '(' and child.dep_ == 'punct' for child in ancestor.children):
                    results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "("})
    return results

def check_round_brackets_in_quotes(doc: Doc) -> List[Dict[str, Any]]:
    """Check for round brackets inside quotes (Rule: APS-GPC-Bracketsandparentheses-H-004)."""
    results = []
    for token in doc:
        if token.text == '(':
            head = token.head
            in_quote = False
            current = head
            while current.head != current:
                if any(t.is_quote and t.dep_ == 'punct' for t in current.children):
                    in_quote = True; break
                current = current.head
            if not in_quote and any(t.is_quote and t.dep_ == 'punct' for t in current.children):
                in_quote = True
            if in_quote:
                results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "("})
    return results

def check_comma_after_short_intro(doc: Doc) -> List[Dict[str, Any]]:
    """Check for commas after short introductory phrases (Rule: APS-GPC-Commas-H-001)."""
    results = []
    for sent in doc.sents:
        if len(sent) > 10: continue
        root = sent.root
        for child in root.children:
            if child.dep_ in ('advcl', 'prep') and child.i < root.i:
                intro_span = doc[child.left_edge.i : child.right_edge.i + 1]
                if len(intro_span) <= 3 and intro_span.end < len(doc) and doc[intro_span.end].text == ',':
                    results.append({"start_char": doc[intro_span.end].idx, "end_char": doc[intro_span.end].idx + 1, "text": ","})
    return results

def check_appositive_commas(doc: Doc) -> List[Dict[str, Any]]:
    """Check for missing commas around non-essential appositives (Rule: APS-GPC-Commas-H-002)."""
    results = []
    for token in doc:
        if token.dep_ == 'appos':
            appos_span = doc[token.left_edge.i : token.right_edge.i + 1]
            has_comma_before = (appos_span.start == 0) or doc[appos_span.start - 1].text == ','
            is_at_sent_end = appos_span.end == appos_span.sent.end
            has_comma_after = is_at_sent_end or (appos_span.end < len(doc) and doc[appos_span.end].text == ',')
            if not has_comma_before or not has_comma_after:
                if appos_span.start == appos_span.sent.start and len(appos_span) == 1: continue
                results.append({"start_char": appos_span.start_char, "end_char": appos_span.end_char, "text": appos_span.text})
    return results

def check_for_example_commas(doc: Doc) -> List[Dict[str, Any]]:
    """Check for commas around 'for example' (Rule: APS-GPC-Commas-H-004)."""
    results = []
    if matcher_for_example is None: return []
    for match_id, start, end in matcher_for_example(doc):
        span = doc[start:end]; sent = span.sent
        try:
            if span.start == sent.start:
                if end < len(doc) and doc[end].text != ',':
                    results.append({"start_char": span.start_char, "end_char": span.end_char, "text": span.text})
            elif span.start > sent.start:
                has_comma_before = doc[start - 1].text == ','
                is_at_sent_end = end == sent.end
                has_comma_after = is_at_sent_end or (end < len(doc) and doc[end].text == ',')
                if not has_comma_before or not has_comma_after:
                    results.append({"start_char": span.start_char, "end_char": span.end_char, "text": span.text})
        except IndexError: continue
    return results

def check_oxford_comma(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for Oxford comma (Rule: APS-GPC-Commas-H-006)."""
    results = []
    for i in range(1, len(doc) - 1):
        if doc[i-1].text == ',' and doc[i].pos_ == 'CCONJ':
            list_head = doc[i].head
            while list_head.dep_ == 'conj': list_head = list_head.head
            if len([list_head] + list(list_head.conjuncts)) > 2:
                results.append({"start_char": doc[i-1].idx, "end_char": doc[i-1].idx + 1, "text": ","})
    return results

def check_en_dash_spans(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for en dashes used for spans (Rule: APS-GPC-Dashes-H-001)."""
    results = []
    for token in doc:
        if token.text == '–' and token.i > 0 and token.i < len(doc) - 1:
            if doc[token.i-1].like_num and doc[token.i+1].like_num:
                results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "–"})
    return results

def check_word_slashes(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for forward slashes joining words (Rule: APS-GPC-Forwardslashes-H-003)."""
    results = []
    for token in doc:
        if token.text == '/' and token.i > 0 and token.i < len(doc) - 1:
            prev_t, next_t = doc[token.i-1], doc[token.i+1]
            if prev_t.like_num or next_t.like_num: continue
            if prev_t.lemma_ == 'and' and next_t.lemma_ == 'or': continue
            if prev_t.pos_ == 'PROPN' and next_t.pos_ == 'PROPN':
                results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "/"})
            elif prev_t.is_alpha and next_t.is_alpha and prev_t.pos_ in ('NOUN', 'ADJ') and next_t.pos_ in ('NOUN', 'ADJ'):
                results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "/"})
    return results

def check_semicolon_usage(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for semicolon rules H-001 and H-002 using a more efficient token-based heuristic."""
    results = []
    for sent in doc.sents:
        scs = [t for t in sent if t.text == ';']
        if not scs: continue

        # Split sentence into parts
        parts = []
        start_idx = sent.start
        for sc in scs:
            parts.append(doc[start_idx : sc.i])
            start_idx = sc.i + 1
        parts.append(doc[start_idx : sent.end])

        # Rule H-003: Skip if it's a complex list (any part has a comma)
        if any(any(t.text == ',' for t in p) for p in parts):
            continue

        # Efficiently check each part for at least one verb and one subject
        for sc in scs:
            results.append({"start_char": sc.idx, "end_char": sc.idx + 1, "text": ";"})
    return results

def check_gov_acronyms(doc: Doc) -> List[Dict[str, Any]]:
    """Flags subsequent use of gov acronyms (Rule: APS-GPC-Acronymsandinitialisms-H-005)."""
    results = []
    if matcher_acronym_def is None: return []
    gov_keywords = {"department", "agency", "authority", "commission", "office", "bureau", "government", "service"}
    defined = {}

    for match_id, start, end in matcher_acronym_def(doc):
        acronym = doc[end-2].text; full_name = doc[start:end-3].text
        if any(kw in full_name.lower() for kw in gov_keywords):
            if acronym not in defined: defined[acronym] = doc[end-1].idx + 1
    for token in doc:
        if token.text in defined and token.idx > defined[token.text]:
            results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_etc_in_lists(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for 'etc.' in lists (Rule: APS-GPC-Latinshortenedforms-H-003)."""
    results = []
    if matcher_list_intro is None: return []
    intro_sents = {doc[start].sent for match_id, start, end in matcher_list_intro(doc)}
    for sent in intro_sents:
        for token in sent:
            if token.text.lower() in ('etc.', 'etc'):
                results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
                break
    return results

def check_weak_adjectives(doc: Doc) -> List[Dict[str, Any]]:
    """Flags common weak adjectives (Rule: APS-GPC-Adjectives-H-001)."""
    results = []
    weak = {"good", "bad", "big", "small", "nice", "great", "lovely", "amazing", "important", "significant", "wonderful", "terrible"}
    for token in doc:
        if token.lemma_.lower() in weak and token.pos_ == 'ADJ':
            results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_predicate_hyphenation(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for hyphenated compound modifiers in predicate (Rule: APS-GPC-Adjectives-H-003)."""
    results = []
    linking = {'be', 'seem', 'appear', 'become', 'feel', 'look', 'sound', 'taste'}
    for token in doc:
        if '-' in token.text and token.pos_ == 'ADJ':
            if token.dep_ in ('acomp', 'attr') or (token.head.lemma_ in linking and token.head.pos_ == 'VERB'):
                results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_adjective_strings(doc: Doc) -> List[Dict[str, Any]]:
    """Flags strings of 2+ adjectives before a noun (Rule: APS-GPC-Adjectives-H-004/H-005)."""
    results = []
    for noun in doc:
        if noun.pos_ not in ('NOUN', 'PROPN'): continue
        child_adjs = sorted([c for c in noun.children if c.dep_ == 'amod' and c.i < noun.i], key=lambda x: x.i)
        if len(child_adjs) < 2: continue
        for i in range(len(child_adjs) - 1):
            if child_adjs[i].i + 1 == child_adjs[i+1].i:
                results.append({"start_char": child_adjs[i].idx, "end_char": child_adjs[i+1].idx + len(child_adjs[i+1].text), "text": doc[child_adjs[i].i : child_adjs[i+1].i+1].text})
    return results

def check_adjective_as_adverb(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for adjectives used as adverbs (Rule: APS-GPC-Adverbs-H-002)."""
    results = []
    for token in doc:
        if token.pos_ == 'ADJ' and token.dep_ == 'advmod' and token.head.pos_ == 'VERB':
            results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_punctuation_in_structural_tags(doc: Doc) -> List[Dict[str, Any]]:
    """Checks for full stops inside headings or captions (Rule: APS-GPC-Punctuationandcapitalisation-H-001)."""
    results = []
    in_tag = False
    for token in doc:
        if token.text.startswith('__SEMANTIC_') and token.text.endswith('_START__') and ('H' in token.text or 'CAPTION' in token.text):
            in_tag = True
        elif token.text.startswith('__SEMANTIC_') and token.text.endswith('_END__'):
            in_tag = False
        if in_tag and token.text == '.':
            results.append({"start_char": token.idx, "end_char": token.idx + 1, "text": "."})
    return results

def check_gene_vs_protein(doc: Doc) -> List[Dict[str, Any]]:
    """Flags potential protein names in italics or genes in roman (Rule: APS-GPC-Plantsandanimals-H-007)."""
    results = []
    bio_pattern = re.compile(r'\b[A-Z]{2,}[0-9]*\b|\b[a-z]{2,}[0-9]+\b')
    in_italics = False
    for token in doc:
        if token.text == "__SEMANTIC_ITALIC_START__": in_italics = True
        elif token.text == "__SEMANTIC_ITALIC_END__": in_italics = False
        if bio_pattern.match(token.text):
            if token.text.isupper() and in_italics:
                results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
            elif not token.text.isupper() and not in_italics:
                results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_fractions_as_words(doc: Doc) -> List[Dict[str, Any]]:
    """Flags numeric fractions (1/2) in general text (Rule: APS-GPC-Choosingnumeralsorwords-H-002)."""
    results = []
    for token in doc:
        if '/' in token.text and any(c.isdigit() for c in token.text) and not any(c.isalpha() for c in token.text):
            results.append({"start_char": token.idx, "end_char": token.idx + len(token.text), "text": token.text})
    return results

def check_sentence_starting_percent(doc: Doc) -> List[Dict[str, Any]]:
    """Flags sentences beginning with % (Rule: APS-GPC-Percentages-H-001)."""
    results = []
    for sent in doc.sents:
        if sent[0].text == "%" or (sent[0].like_num and len(sent) > 1 and sent[1].text == "%"):
            results.append({"start_char": sent[0].idx, "end_char": sent[1].idx + 1 if len(sent) > 1 and sent[1].text == "%" else sent[0].idx + 1, "text": sent.text[:10]})
    return results

def check_verb_presence(doc: Doc) -> List[Dict[str, Any]]:
    """Flags sentences that lack a finite verb (Rule: APS-GPC-Verbs-H-001)."""
    results = []
    for sent in doc.sents:
        if len(sent) < 4: continue
        if not any(t.pos_ in ("VERB", "AUX") for t in sent):
            results.append({"start_char": sent.start_char, "end_char": sent.end_char, "text": sent.text})
    return results

def check_ordinal_pairing(doc: Doc) -> List[Dict[str, Any]]:
    """Checks that 'Firstly' is paired with 'Secondly' within the next few sentences (Rule: APS-GPC-Ordinalnumbers-H-002)."""
    results = []
    sents = list(doc.sents)
    for i, sent in enumerate(sents):
        if "firstly" in sent.text.lower():
            # Check the current and next two sentences for "secondly"
            found_secondly = "secondly" in sent.text.lower()
            if not found_secondly:
                for j in range(i + 1, min(i + 3, len(sents))):
                    if "secondly" in sents[j].text.lower():
                        found_secondly = True; break
            if not found_secondly:
                results.append({"start_char": sent.start_char, "end_char": sent.end_char, "text": "Firstly"})
    return results

def check_australian_government_casing(doc: Doc) -> List[Dict[str, Any]]:
    """Ensures 'Australian Government' is capped only together (Rule: APS-GPC-Governmentterms-H-001)."""
    results = []
    for i in range(len(doc) - 1):
        if doc[i].text == "Australian" and doc[i+1].text == "government":
            results.append({"start_char": doc[i].idx, "end_char": doc[i+1].idx + len(doc[i+1].text), "text": "Australian government"})
        if doc[i].text == "Government" and (i == 0 or doc[i-1].text != "Australian") and not doc[i].is_sent_start:
            results.append({"start_char": doc[i].idx, "end_char": doc[i].idx + len(doc[i].text), "text": "Government"})
    return results

# Map of Heuristic IDs to Functions
HEURISTIC_FUNCTIONS: Dict[str, Callable[[Doc], List[Dict[str, Any]]]] = {
    "APS-GPC-Partsofsentences-H-009": check_passive_voice,
    "APS-GPC-Partsofsentences-H-001": check_complete_sentence,
    "APS-GPC-Nouns-R-004": check_collective_noun_agreement,
    "APS-GPC-Adjectives-H-002": check_hyphenated_modifier,
    "APS-GPC-Pronouns-H-005": check_that_vs_which,
    "APS-GPC-Nouns-H-001": check_missing_determiner,
    "APS-GPC-Exclamationmarks-H-001": check_exclamation_marks,
    "APS-GPC-Conjunctions-H-001": check_matched_correlatives,
    "APS-GPC-Latinshortenedforms-H-001": check_prefer_english_forms,
    "APS-GPC-Adjectives-R-002": check_unique_grading,
    "APS-GPC-Typesofwords-H-002": check_misplaced_only,
    "APS-GPC-Adverbs-H-001": check_filler_adverbs,
    "APS-GPC-Verbs-R-007": check_modal_verb_to,
    "APS-GPC-Pronouns-H-004": check_improper_reflexive_pronoun,
    "APS-GPC-Determiners-R-001": check_a_vs_an,
    "APS-GPC-Organisationnames-H-007": check_generic_organisation_reference,
    "APS-GPC-Governmentterms-H-007": check_generic_official_titles,
    "APS-GPC-Governmentterms-H-014": check_generic_parliamentary_terms,
    "APS-GPC-Medicalterms-H-004": check_capitalized_common_noun_definitions,
    "APS-GPC-Nationalities,peoplesandplacesoutsideAustralia-H-003": check_capitalized_the_before_country,
    "APS-GPC-Nationalities,peoplesandplacesoutsideAustralia-H-006": check_improperly_cased_regions,
    "APS-GPC-Organisationnames-H-008": check_org_the_capitalisation,
    "APS-GPC-Organisationnames-H-010": check_org_verb_agreement,
    "APS-GPC-Choosingnumeralsorwords-H-001": check_numerals_vs_words,
    "APS-GPC-Choosingnumeralsorwords-H-009": check_large_rounded_numbers,
    "APS-GPC-Currency-H-001": check_aud_currency,
    "APS-GPC-Currency-H-002": check_ambiguous_dollar_sign,
    "APS-GPC-Datesandtime-H-001": check_year_span_words,
    "APS-GPC-Datesandtime-H-002": check_financial_year_dash,
    "APS-GPC-Datesandtime-H-003": check_day_month_span_words,
    "APS-GPC-Fractionsanddecimals-H-001": check_worded_decimals,
    "APS-GPC-Ordinalnumbers-H-001": check_prose_ordinals_for_steps,
    "APS-GPC-Partsofsentences-H-005": check_compound_clause_comma,
    "APS-GPC-Partsofsentences-H-006": check_comma_with_shared_subject,
    "APS-GPC-Partsofsentences-H-010": check_passive_missing_agent,
    "APS-GPC-Phrases-H-001": check_possessive_in_compound,
    "APS-GPC-Apostrophes-H-001": check_descriptive_apostrophe,
    "APS-GPC-Bracketsandparentheses-H-003": check_nested_parentheses,
    "APS-GPC-Bracketsandparentheses-H-004": check_round_brackets_in_quotes,
    "APS-GPC-Commas-H-001": check_comma_after_short_intro,
    "APS-GPC-Commas-H-002": check_appositive_commas,
    "APS-GPC-Commas-H-004": check_for_example_commas,
    "APS-GPC-Commas-H-006": check_oxford_comma,
    "APS-GPC-Dashes-H-001": check_en_dash_spans,
    "APS-GPC-Forwardslashes-H-003": check_word_slashes,
    "APS-GPC-Semicolons-H-001": check_semicolon_usage,
    "APS-GPC-Acronymsandinitialisms-H-005": check_gov_acronyms,
    "APS-GPC-Latinshortenedforms-H-003": check_etc_in_lists,
    "APS-GPC-Adjectives-H-001": check_weak_adjectives,
    "APS-GPC-Adjectives-H-003": check_predicate_hyphenation,
    "APS-GPC-Adjectives-H-004": check_adjective_strings,
    "APS-GPC-Adverbs-H-002": check_adjective_as_adverb,
    "APS-GPC-Fullstops-H-003": check_punctuation_in_structural_tags,
    "APS-GPC-Plantsandanimals-H-007": check_gene_vs_protein,
    "APS-GPC-Choosingnumeralsorwords-H-002": check_fractions_as_words,
    "APS-GPC-Percentages-H-001": check_sentence_starting_percent,
    "APS-GPC-Verbs-H-001": check_verb_presence,
    "APS-GPC-Ordinalnumbers-H-002": check_ordinal_pairing,
    "APS-GPC-Governmentterms-H-001": check_australian_government_casing,
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

        # Refined logic: prefer heuristic if available for this rule ID
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
                    res.get("suggestion") or suggestion
                )
            # If we used a heuristic, skip the regex for the same rule ID
            continue

        if category == "regex":
            pattern = rule.get("pattern")
            if pattern:
                try:
                    flags = re.MULTILINE
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
            # This part is now handled by the check above (if rule_id in HEURISTIC_FUNCTIONS),
            # but we keep it for any rules that might be added to HEURISTIC_FUNCTIONS
            # later but not yet handled by the skip logic.
            pass

    return sorted(findings, key=lambda x: x.get("start_char", 0))
