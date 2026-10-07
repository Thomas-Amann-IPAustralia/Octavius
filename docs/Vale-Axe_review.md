**Vale could substantially reduce what you need to build.** I would use the actual Vale engine for your deterministic prose checks, with your application handling imports, rule provenance, exceptions, reporting and any additional analysis. **Axe-core would be a complementary accessibility checker for material rendered on the web.**

Your broader scope—briefs, reports, emails, presentations, social posts and other non-sensitive writing—is compatible with this approach. The Australian Government Style Manual itself applies across government content, including briefs, policy documents, reports, forms and communications. [AGA](https://architecture.digital.gov.au/standard/australian-government-style-manual?utm_source=chatgpt.com)

**Vale checks writing against rules you supply.** You encode a guideline in a YAML file, specifying what to detect, where to look, the explanation to show and, optionally, a suggested replacement. Vale runs these checks locally without requiring an LLM. Installing it gives you the engine; you still need an Australian Government rule set. [docs.vale.sh](https://docs.vale.sh/topics/styles?utm_source=chatgpt.com)

Using the categories in your outline, its fit looks like this:

| Your rule category | How Vale could help | What still needs care |
|---|---|---|
| **A. Mechanical** | Detect punctuation, spacing and specified date or number patterns. | Encode the manual’s exceptions accurately. |
| **B. Lexical with exceptions** | Check preferred terms, inconsistent terminology and spelling with configured dictionaries. | Account for quotations, official names and specialist usage. |
| **C. Structural and formatting** | Apply different checks to headings, lists, table cells and captions. | Preserve that structure when importing documents. |
| **D. Contextual or semantic** | Check some acronym definitions, sentence length, readability measures and grammatical patterns. | These checks provide limited evidence about meaning or comprehension. |
| **E. Judgement and intent** | Supply findings that inform review. | Audience suitability, cultural appropriateness and communication effectiveness still need judgement. |

Vale’s documented checks include substitution, consistency, capitalization, spelling, readability and part-of-speech sequences, alongside pattern and counting checks. [docs.vale.sh](https://docs.vale.sh/topics/styles?utm_source=chatgpt.com)

For example, the Style Manual suggests *use* as a simpler alternative to *utilise*. An illustrative Vale rule could be:

```yaml
extends: substitution
message: "Consider '%s' instead of '%s'."
level: suggestion
scope: ~blockquote
ignorecase: true
link: https://www.stylemanual.gov.au/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice
swap:
  utilise: use
```

That produces a repeatable finding wherever the pattern matches outside block quotations. The suggestion level leaves the author to assess the context. The underlying word-choice guidance comes directly from the manual. [Style Manual](https://www.stylemanual.gov.au/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice?utm_source=chatgpt.com)

Vale’s awareness of document structure is particularly useful for your project. It can target heading text, list items, table cells, link text and image alternative text. It normally excludes code from prose checks. That saves you from rebuilding much of the segmentation and scoping machinery described in your outline. [docs.vale.sh](https://docs.vale.sh/topics/scopes?utm_source=chatgpt.com)

**I would revise two recommendations in your outline.**

First, it understates Vale’s ability to handle relationships across text. Vale’s `conditional` check can detect an acronym used before its definition, carrying definitions forward across later paragraphs. Its `script` extension supports arbitrary logic written in Tengo, including checks over the raw document. Some rules currently assigned to your custom or model tiers could therefore remain deterministic inside Vale. This does not establish that every proposed relationship is supported; it warrants checking the actual rules before allocating them elsewhere. [docs.vale.sh](https://docs.vale.sh/checks/conditional?utm_source=chatgpt.com)

Second, **I would favour integrating Vale over creating a “Vale-compatible Python reimplementation.”** Reimplementing it would make you responsible for parser behaviour, scope matching, exceptions and future compatibility. Your FastAPI backend can invoke Vale and consume its JSON output, which includes the rule, severity, matched text, location, message, guidance link and available action. [docs.vale.sh](https://docs.vale.sh/topics/cli?utm_source=chatgpt.com)

Your proposed rule registry remains useful, but its fields—such as `tier`, `validator`, `mutation_class` and `confidence`—are your application’s contract. You would need to map appropriate rules into native Vale YAML and retain the additional metadata alongside them.

**The GOV.UK example demonstrates a useful implementation pattern.** The linked repository packages government writing guidance as Vale rules, distinguishes conditional advice from firmer checks, and tests expected behaviour with examples. Its technical-documentation focus comes from the chosen rules and workflow; it does not restrict Vale to that genre. I would borrow its packaging and testing approach, then validate each adopted rule against Australian guidance. [alphagov/tech-docs-linter · GitHub](https://github.com/alphagov/tech-docs-linter?utm_source=chatgpt.com)

**Axe-core checks the accessibility of rendered web content.** It examines the browser’s document structure and presentation. Its rules can identify issues such as missing image alternatives, links or controls without accessible names, missing form labels, invalid language attributes and insufficient colour contrast. These are useful checks when your material becomes a webpage or an interactive form. [GitHub](https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md?utm_source=chatgpt.com)

It does not supply Australian Government writing rules for grammar, terminology or tone. Consider an image with alternative text: axe-core can identify certain technical problems with the alternative-text mechanism; deciding whether the description conveys the relevant information requires further review.

It also does not establish complete accessibility compliance. Axe-core returns `incomplete` results for cases it cannot determine confidently, and its maintainers explicitly identify the need for manual review. [GitHub](https://github.com/dequelabs/axe-core?utm_source=chatgpt.com)

For your broad writing scope, the practical distinction is:

| Material | Vale’s role | Axe-core’s role |
|---|---|---|
| **Pasted text, emails, briefs and social-post drafts** | Check the wording; structural checks depend on the information supplied. | Little direct value for the text alone. |
| **Webpages and online forms** | Check prose and selected text elements. | Check the actual rendered page and relevant interaction states. |
| **Word documents, presentations and PDFs** | Check extracted text or a converted representation through an import layer. | Does not assess the native document’s accessibility. An HTML preview only establishes findings about that preview. |

Vale documents support for plain-text input and multiple markup formats. Axe-core’s API analyses rendered content on a loaded webpage. The native-document boundary above follows from those interfaces. [docs.vale.sh](https://docs.vale.sh/topics/cli?utm_source=chatgpt.com)

This is also why I would soften your outline’s recommendation to make Markdown the sole canonical representation. Markdown may work well for checking prose, but your import layer should retain original document locations and relevant structure. Otherwise, a correct finding may be difficult to highlight in Word, and some formatting information may disappear before checking.

My recommended division of responsibility would be:

- **Vale:** deterministic prose rules that fit its checks and scopes.
- **Your custom engine:** remaining deterministic checks, document imports, source mappings, writing profiles, rule versions and reporting.
- **Axe-core:** accessibility checks on rendered web outputs and on your own editor interface.
- **Optional model assistance and human review:** contextual questions that the deterministic checks cannot settle.

Keep the distinction between deterministic findings and model-assisted advice visible. If an LLM can suppress a Vale finding, the final results are no longer strictly determined by the text, configuration and tool versions. Also, document-wide rules need document-wide context: checking each paragraph independently would lose earlier acronym definitions.

I would start by encoding **20–30 representative Style Manual rules in Vale**, including exceptions and structural rules, then evaluate them against examples from your actual writing genres. That will show how much custom logic remains. For your immediate goal, Vale deserves that trial first; axe-core becomes valuable when checking web presentation is part of the scope.
