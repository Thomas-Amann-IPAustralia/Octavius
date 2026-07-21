# How Octavius Works — A Plain-Language Guide

*This document explains Octavius from beginning to end: how its rules are built,
and how those rules are applied to your writing. It's written for a general
audience. You don't need to be a programmer to follow it. Wherever a technical
term is unavoidable, it's explained with a plain-English comparison the first
time it appears.*

---

## Contents

1. [What Octavius is, in one paragraph](#1-what-octavius-is-in-one-paragraph)
2. [The big picture: two separate jobs](#2-the-big-picture-two-separate-jobs)
3. [Part One — Building the rulebook](#3-part-one--building-the-rulebook)
4. [Part Two — Applying the rulebook to your writing](#4-part-two--applying-the-rulebook-to-your-writing)
5. [A worked example: one sentence, start to finish](#5-a-worked-example-one-sentence-start-to-finish)
6. [Why it's built this way](#6-why-its-built-this-way)
7. [Keeping the rulebook up to date](#7-keeping-the-rulebook-up-to-date)
8. [Glossary](#8-glossary)

---

## 1. What Octavius is, in one paragraph

Octavius is a proofreading assistant for people who write on behalf of the
Australian Public Service. You paste or type your document into it, and it
underlines places where your writing doesn't follow the
[Australian Government Style Manual](https://www.stylemanual.gov.au/) — the
official guide to how government content should be written. For each underline
it tells you *what* the issue is, *why* it matters, and often *how* to fix it,
with a link back to the exact page of the Style Manual that the advice comes
from. Think of it as a spell-checker, except instead of catching misspelled
words it catches *style* problems: passive voice, jargon, headings written in
the wrong case, American spellings, overly long sentences, and hundreds of
other things the Style Manual has an opinion about.

---

## 2. The big picture: two separate jobs

It helps to understand that Octavius really does **two different jobs**, and
they happen at different times.

**Job one — building the rulebook.** Long before you ever open the app,
Octavius has to *learn the rules*. The Australian Government Style Manual is a
large website full of guidance written for humans. Someone (or, in this case,
an automated pipeline) has to read all of that guidance and turn each piece of
advice into a precise, testable "rule" that a computer can check. The end
result of this job is a single finished file — the **rulebook** — a bit like a
cookbook where every recipe has been written down, tested, and approved.

**Job two — applying the rulebook.** When you actually use the app, Octavius
takes your document and runs it against that finished rulebook, then shows you
what it found. This happens live, in a fraction of a second, every time you
stop typing.

The first job is slow, careful, and happens occasionally (whenever the Style
Manual changes or the rules are improved). The second job is fast and happens
constantly. The rest of this document walks through each in turn.

> **Analogy:** Building the rulebook is like a publisher preparing a
> proofreading manual — researching, drafting, fact-checking, and printing it.
> Applying the rulebook is like a proofreader sitting down with that finished
> manual and marking up your essay. The publisher's work happens once; the
> proofreader uses it again and again.

---

## 3. Part One — Building the rulebook

### 3.1 Where the rules come from

Every rule in Octavius traces back to a real page of the Australian Government
Style Manual. Nothing is invented. If the Style Manual says "write dates as
*12 January 2026*, not *January 12, 2026*", then somewhere in Octavius there is
a rule that checks for that, and it carries a link straight back to the page it
came from. This matters because it means every underline Octavius shows you can
be justified — you can always click through and read the original guidance.

### 3.2 The assembly line

Turning a website full of human-friendly advice into a set of computer-checkable
rules is done by a **pipeline** — an assembly line of six steps, each of which
takes the output of the previous step and refines it a little more. Here is the
whole line at a glance, followed by a plain-language description of each step.

```
  Style Manual website
          │
          ▼
   ①  Copy the pages          →  a tidy local copy of the guidance
          │
          ▼
   ②  Extract the rules       →  a list of individual "do this / don't do that" rules
          │
          ▼
   ③  Write the check         →  the actual test each rule performs
          │
          ▼
   ③·⁵ Describe when to check  →  notes on which kinds of text each rule applies to
          │
          ▼
   ④  Test every rule         →  proof that each check actually works
          │
          ▼
   ⑤  Fix the failures        →  a second attempt at any rule that failed its test
          │
          ▼
   ⑥  Publish                 →  the finished, sealed rulebook the app loads
```

#### Step ① — Copy the pages ("scraping")

First, Octavius makes its own local copy of the Style Manual website so it can
work from a stable snapshot rather than a live site that might change or go
offline. This is called *scraping* — automatically visiting each page and
saving its text.

The Style Manual's website tries to block automated visitors, so this step is a
little like a determined researcher who, when the front desk won't let them in,
politely uses a different door: if a quick request is refused, Octavius falls
back to driving a real web browser to load the page exactly as a person would.
It also keeps a record of every page it saved and checks nothing was corrupted
along the way.

#### Step ② — Extract the rules

A single Style Manual page might contain several distinct pieces of advice mixed
in with examples and explanation. In this step, an AI language model reads each
page and pulls out the individual rules as separate, self-contained statements —
for example, "Headings should use sentence case, not title case." Each extracted
rule also gets a short plain-English summary, a slightly longer explanation of
*why*, and a category label (more on categories below).

#### Step ③ — Write the check ("rules as code")

A plain-English rule like "don't use American spellings" isn't something a
computer can act on directly. This step turns each rule into an actual
**check** — a small, precise instruction that can look at a piece of text and
answer "does this rule apply here, yes or no?"

Not every rule can be checked the same way, so each rule is given a **category**
(the technical word is *taxonomy*) that determines *how* it gets checked:

- **Pattern rules** *(regex)* — for issues you can spot by looking for a
  specific pattern of characters. For example, the American spelling "finalize"
  can be caught by looking for the letters *f-i-n-a-l-i-z-e*. A "pattern" here is
  just a precise description of what to look for, like a search-and-find on
  steroids.
- **Word-list rules** *(lookup)* — for issues that come down to a list of
  specific words or phrases to watch for. For example, a list of jargon terms to
  avoid. The check simply scans for any word on the list.
- **Structure rules** *(structural)* — for issues about the *shape* of the
  writing rather than the words themselves. For example, "a bullet point
  shouldn't end with a full stop" is about structure, not vocabulary.
- **Judgement rules** *(semantic, discretionary, and others)* — for issues that
  genuinely require human judgement and can't be reliably checked by a machine.
  These are recorded so nothing is lost, but they're deliberately *not* turned
  into automatic checks, because a machine would get them wrong too often.

At the same time, this step invents a handful of **test sentences** for each
rule: some that the rule *should* catch, and some that it *should not*. These
become the rule's exam, used two steps later.

#### Step ③·⁵ — Describe when to check ("features")

This is a subtle but important step. Most rules only make sense in certain kinds
of text. A rule about headings should only ever look at headings. A rule about
long sentences shouldn't fire inside a code snippet or a web address.

So each rule is tagged with a short description of the *conditions* under which
it should even be considered — the kinds of text it cares about, and the kinds
it should ignore. These tags are called **features**. (You'll meet features
again in Part Two, because they're the same tags Octavius later attaches to
*your* writing to decide which rules are worth running.)

This step also labels how *fixable* each rule is:

- **Safe to auto-fix** — Octavius can confidently offer a one-click correction
  (e.g. swapping "finalize" for "finalise").
- **Needs a rewrite** — the fix requires rephrasing, so Octavius flags it but
  won't rewrite it for you.
- **Needs a human** — the issue is real but too nuanced for an automatic
  suggestion; Octavius just points it out.

#### Step ④ — Test every rule

Now each rule sits its exam. Octavius runs every rule against the test sentences
that were written for it in step ③. A rule **passes** only if it catches all the
sentences it was supposed to catch *and* leaves alone all the sentences it was
supposed to ignore. A rule that fails — say, it misses a problem, or it flags
something that's perfectly fine — is marked as failed.

This is the quality gate that keeps the rulebook honest. **Only rules that pass
their exam are ever allowed into the finished rulebook.** A rule that fails is
held back until it can be fixed.

#### Step ⑤ — Fix the failures ("correction")

Any rule that failed its exam gets a second chance. An AI model looks at what
went wrong and rewrites the faulty check, and then the corrected rule is
re-tested. Every correction is logged, so there's always a record of what was
changed and why.

#### Step ⑥ — Publish

Finally, all the rules that passed are packed into a single, sealed file — the
**published rulebook**. This is the finished cookbook. It's a compact, efficient
format built for fast reading by the app, and it's the *only* rule file the
running app ever loads. Rules that didn't pass, or that were deliberately set
aside, simply aren't included.

### 3.3 Two versions of the rulebook: the draft and the finished copy

Behind the scenes there are always two copies of the rulebook, and it's worth
knowing the difference:

- **The working draft** — a human- and machine-editable master list containing
  *every* rule, including failed ones, judgement-only ones, and ones that have
  been paused. This is the workshop where rules are edited.
- **The published rulebook** — the sealed, tested, app-ready copy that contains
  *only* the rules that passed. This is what ships.

When someone wants to add, change, or remove a rule, they edit the draft, re-run
the exam, and re-publish. A rule can also be quietly **paused** (kept in the
draft for the record but excluded from the published copy) — useful for a rule
that's technically correct but causes too many false alarms to be helpful yet.

---

## 4. Part Two — Applying the rulebook to your writing

Now for the part you actually see. Everything below happens live, in well under
a second, each time you pause while typing.

### 4.1 The editor

Octavius gives you a rich-text editor — the kind where headings look like
headings and bullet lists look like bullet lists, rather than a plain box of
text. This matters more than it might seem. Because the editor understands the
*structure* of what you're writing, Octavius knows which parts of your document
are headings, which are paragraphs, which are bullet points, which are tables,
and so on. That structural awareness is what lets it apply heading rules only to
headings, list rules only to lists, and so on.

Octavius waits until you stop typing for a moment (about four-tenths of a second)
before it checks anything. This small pause — called *debouncing* — stops it
from frantically re-checking on every single keystroke, which would be wasteful
and distracting.

### 4.2 Breaking your document into zones

The first thing Octavius does with your document is break it into its natural
pieces. Each piece — a heading, a paragraph, a single bullet point, a table
cell, a quote — is called a **zone**. Each zone is labelled with what kind of
thing it is and where exactly it sits in your document, so that when Octavius
later finds a problem, it can point to the precise spot.

A couple of zone types — chunks of computer code and inline code — are marked
"don't check this," because style rules for prose don't apply to code. Those
zones are set aside and never bothered with.

### 4.3 Masking: covering up the parts to ignore

Even within an ordinary paragraph, there are usually bits that shouldn't be
proofread as if they were normal writing: web addresses, file names, product
names, direct quotations, snippets of code, and so on. A rule that flags long
sentences shouldn't count a long web address as a "sentence," and a spelling
rule shouldn't try to "correct" a brand name.

So before checking, Octavius **masks** these regions — think of it as laying an
opaque sticky note over each one that reads "ignore me." The checks run over the
masked version of the text, so they never trip over things that were never meant
to be judged. Octavius keeps a note of exactly what was under each sticky note,
so it can peel them off again afterwards and show you your original text
untouched.

### 4.4 Features: describing what each piece of text looks like

This is the clever core of how Octavius stays fast and accurate. Before running
any rules, it takes a quick glance at every zone and jots down a set of plain
observations about it — the same kind of **features** you met in Part One. For
example, for a given zone it might note:

- *This is a heading.*
- *It contains a date.*
- *It contains a web address.*
- *It's written in the passive voice.*
- *It's a long sentence.*
- *It mentions a piece of legislation.*
- *It sits inside a table.*

None of these observations is a judgement about whether anything is *wrong*.
They're just a quick description of what the text *is like* — a fingerprint.
Some of these fingerprints are simple to read off (does it contain a date?);
others need a bit of language analysis to work out (is this sentence passive?),
which Octavius does using a natural-language toolkit that understands grammar.

> **Analogy:** Imagine a mailroom clerk who, before sorting a stack of letters,
> quickly stamps each envelope with a few tags: "handwritten," "has a foreign
> stamp," "marked urgent." The clerk isn't deciding what to do with the letters
> yet — just describing them so the right people can be handed the right ones.

### 4.5 The smart shortlist: only running rules that could possibly apply

Octavius contains a *lot* of rules. Running every single one against every
sentence would be slow and, worse, would produce needless false alarms. This is
where the fingerprints pay off.

Each rule, remember, was tagged in Part One with the conditions it cares about —
which features a piece of text must have (or must *not* have) for the rule to be
relevant. So for each zone, Octavius compares the zone's fingerprint against
those conditions and draws up a **shortlist** of only the rules that could
possibly match. A heading rule is shortlisted only for headings; a passive-voice
rule only for passive sentences; a rule that must never fire inside a web
address is dropped for any zone containing one.

The mechanism that makes this shortlisting near-instant is called an **inverted
index**. That's just a fancy name for the same idea as the index at the back of
a book: instead of reading every page to find where "koala" is mentioned, you
look up "koala" in the index and jump straight to the right pages. Octavius does
the reverse of the obvious thing — rather than asking each rule "do you apply
here?", it uses the fingerprint to look up "which rules care about text like
this?" — and gets its shortlist in one quick lookup.

> There is also a simpler, slower fallback mode that skips the shortlist and
> runs every rule against everything. It exists mainly for testing and
> debugging; the smart-shortlist mode is the one built for everyday use.

### 4.6 Running the checks

Now Octavius runs only the shortlisted rules against each zone. Each rule looks
at the (masked) text and reports back any spots where it applies — for instance,
"the word *finalize* at characters 20 to 28." These raw results are called
**findings**.

To avoid repeating work, Octavius remembers the results for text it has already
seen. If you have the same sentence twice, or you edit one paragraph and leave
the rest untouched, it reuses the earlier answers for the unchanged parts rather
than re-checking them. (This memory is called a *cache*.)

### 4.7 Tidying up the results

The raw findings aren't shown to you straight away. First Octavius cleans them
up so the final list is sensible and not overwhelming:

1. **A firing budget.** If a single rule would flag the *same* issue dozens of
   times in one document, that's more noise than help. So each rule is capped:
   after it has flagged an issue a handful of times, any further instances are
   rolled up into a single summary note ("this issue appears many times")
   instead of dozens of separate underlines.

2. **Removing exact duplicates.** If the very same rule flags the very same spot
   twice, the duplicate is dropped.

3. **Grouping overlapping findings.** If two *different* rules both point at the
   exact same span of text, they're merged into one finding that mentions both,
   so you don't see two underlines stacked on the same words. When findings are
   merged, Octavius takes the most cautious view of how to fix them — if any of
   the merged rules needs a human, the combined finding needs a human.

4. **Quieting down on short or shapeless documents.** Some rules are about the
   overall *document* — for example, "documents should have headings." These
   only make sense once you've actually written a real document. If you've only
   typed a sentence or two, or a fragment with no real structure, these
   whole-document rules are held back so Octavius doesn't nag you about a
   document you haven't finished writing. (The roll-up summaries from the firing
   budget are the one exception — those always come through.)

### 4.8 Showing you the results

Finally, the cleaned-up findings are sent back to the editor and shown two ways
at once:

- **Inline highlights** — the exact words at issue are underlined or highlighted
  right there in your text, so you can see problems in context.
- **A findings panel** — a side list of every finding, each with its plain
  summary, the reason behind it, a link to the Style Manual page it came from,
  and, where possible, a suggested fix.

Because Octavius kept careful track of where every zone and every finding sits,
each highlight lands on precisely the right words, even after all the masking
and behind-the-scenes rearranging.

### 4.9 Suggestions and fixes

For findings that are **safe to auto-fix**, Octavius offers a one-click
correction — for example, replacing an American spelling with the Australian
one, or converting a title-case heading to sentence case. For findings that
**need a rewrite** or **need a human**, it won't touch your words; it simply
explains the issue and leaves the decision to you. This division is deliberate:
Octavius will only make a change for you when it can be confident the change is
correct.

---

## 5. A worked example: one sentence, start to finish

Suppose you type this heading into Octavius:

> **Finalizing The Report**

Here's the journey it takes:

1. **Zone.** Octavius recognises this as a *heading* zone, and notes where it
   sits in your document.
2. **Masking.** There are no web addresses, code, or quotes here, so nothing
   gets covered up.
3. **Fingerprint (features).** Octavius jots down: *this is a heading*, *it's in
   title case* (every important word is capitalised), *it contains the American
   spelling pattern "-ize."*
4. **Shortlist.** From the full rulebook, Octavius draws up the short list of
   rules that care about headings and about title case and about American
   spelling — a few rules, not the whole book.
5. **Run the checks.** Two rules match:
   - *Use Australian spelling* flags **Finalizing** (should be "Finalising").
   - *Headings should use sentence case* flags the whole heading (should be
     "Finalising the report").
6. **Tidy up.** The two findings don't cover the exact same span, so they stay
   as two separate findings. Neither is a duplicate. The document is short, but
   these are ordinary (not whole-document) rules, so they aren't held back.
7. **Show and fix.** Both problems are underlined in your heading and listed in
   the panel. The spelling fix is *safe to auto-fix*, so you get a one-click
   "change to Finalising." The sentence-case fix is offered as a suggested
   rewrite of the whole heading. Each finding links to the Style Manual page it
   came from.

The whole thing happens in the blink of an eye after you stop typing.

---

## 6. Why it's built this way

A few of Octavius's design choices are worth calling out, because they explain
why it behaves the way it does.

**Every rule is traceable.** Because rules are extracted from real Style Manual
pages and carry a link back, Octavius can always justify itself. It's an
assistant that shows its working, not a black box.

**Rules must pass an exam before they ship.** Nothing reaches you until it has
proven, on test sentences, that it catches what it should and ignores what it
shouldn't. This is the single biggest guard against Octavius crying wolf.

**Fingerprints keep it fast *and* quiet.** By describing your text first and
then only running the handful of rules that could possibly apply, Octavius stays
quick even with a large rulebook — and, just as importantly, avoids the false
alarms you'd get from running irrelevant rules everywhere.

**Masking respects the parts that aren't prose.** Web addresses, code, and
quotations are left alone, so Octavius doesn't "correct" things that were never
meant to follow prose style.

**It only auto-fixes when it's sure.** One-click fixes are reserved for changes
that are safe and unambiguous. Everything else is offered as advice, leaving you
in control.

**It's cautious on unfinished writing.** Whole-document rules stay quiet until
there's actually a document to judge, so you're not nagged mid-sentence.

---

## 7. Keeping the rulebook up to date

The Style Manual changes over time, and the rules can always be improved. Keeping
Octavius current follows the same assembly line from Part One, and it can be done
two ways:

- **Automatically.** The six-step pipeline can re-copy the Style Manual, extract
  any new or changed guidance, generate and test fresh checks, and re-publish —
  largely on its own, on a schedule.
- **By hand.** A person can edit the working-draft rulebook directly: add a new
  rule, adjust an existing one, pause a noisy one, or remove one. After any
  hand-edit, the rule is re-tested and the rulebook re-published so the change
  takes effect.

In both cases the golden rule holds: **only rules that pass their exam make it
into the published rulebook the app loads.** Everything Octavius shows you has
earned its place.

---

## 8. Glossary

| Term | Plain-English meaning |
|---|---|
| **Rule** | A single, checkable piece of style guidance (e.g. "use Australian spelling"), traceable to a Style Manual page. |
| **Rulebook** | The complete collection of rules. Exists as an editable *working draft* and a sealed, app-ready *published* copy. |
| **Pipeline** | The six-step assembly line that turns Style Manual pages into tested rules. |
| **Scraping** | Automatically saving a local copy of the Style Manual's web pages. |
| **Taxonomy / category** | The *kind* of a rule, which decides how it's checked: pattern, word-list, structure, or human-judgement. |
| **Pattern (regex)** | A precise description of characters to search for — a supercharged find-and-replace. |
| **Zone** | One natural piece of your document — a heading, a paragraph, a bullet point, a table cell, and so on. |
| **Masking** | Temporarily covering up parts of the text (web addresses, code, quotes) so they aren't proofread as ordinary prose. |
| **Feature / fingerprint** | A quick, factual observation about a piece of text ("this is a heading," "this contains a date") used to decide which rules to run. |
| **Inverted index / shortlist** | A back-of-the-book-style index that instantly finds which rules could apply to a given piece of text. |
| **Finding** | A single spot where a rule applies to your text — what becomes an underline in the editor. |
| **Firing budget** | A cap on how many times one rule can flag the same issue before the rest are rolled up into a summary. |
| **Cache** | Octavius's short-term memory of results for text it has already checked, so unchanged parts aren't re-checked. |
| **Debounce** | The brief pause after you stop typing before Octavius re-checks, so it isn't working on every keystroke. |
| **Document-level gating** | Holding back whole-document rules until there's a real, structured document to judge. |
| **Mutation class** | How fixable a finding is: safe to auto-fix, needs a rewrite, or needs a human. |

---

*For the technical architecture, file-by-file breakdown, and developer
instructions, see [`CLAUDE.md`](../CLAUDE.md), [`README.md`](../README.md), and
[`CLAUDE_Octavius Rulebook Creation Pipeline.md`](../CLAUDE_Octavius%20Rulebook%20Creation%20Pipeline.md).*
