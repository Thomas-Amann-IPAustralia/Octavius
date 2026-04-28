# Octavius Repository Index

This document provides a comprehensive index of the Octavius repository, a plain-language linter for Australian Public Service (APS) content.

## Root Directory

| File / Folder | Description |
| :--- | :--- |
| `app.py` | Main Streamlit application entry point. Provides the UI for the rule editor and developer tools. |
| `main.py` | FastAPI backend providing API endpoints (`/check`, `/groups`) for standalone frontend implementations. |
| `index.html` | A standalone, vanilla JavaScript and HTML implementation of the Octavius frontend. |
| `octavius_component.py` | Declaration and helper for the Streamlit custom component that wraps the React-based editor. |
| `README.md` | Project overview, installation instructions, and architecture summary. |
| `CLAUDE.md` | Developer-focused guide with commands, architectural details, and rule-authoring instructions. |
| `CLAUDE_Octavius Rulebook Creation Pipeline.md` | Detailed specification for the six-phase automated pipeline that builds the rulebook. |
| `octavius_frontend_spec.md` | Technical specification for the Octavius frontend component. |
| `render.yaml` | Deployment configuration for hosting the FastAPI backend on Render. |
| `requirements.txt` | Python dependencies for the core application and Streamlit UI. |
| `requirements-pipeline.txt` | Python dependencies for the rulebook creation pipeline (e.g., Selenium, OpenAI, trafilatura). |
| `rules_working_draft.jsonl` | The primary working file for the rulebook pipeline, containing rules in various stages of extraction and testing. |
| `amendment_log.json` | A log of corrections applied to rules during Phase 5 of the pipeline. |
| `batch_state.json` | Tracks the status of active OpenAI Batch API jobs (Phase 2, 3, and 5). |
| `content_manifest.json` | A manifest of all scraped markdown files from the Style Manual, including SHA-256 hashes. |
| `sitemap_state.json` | Persistent state tracking URL last-modification dates from the Style Manual sitemap. |
| `RuleGenerationDemo.xlsx` | Spreadsheet for demonstrating or manually tracking rule generation. |
| `.claudeignore` | Configuration for files ignored by Claude. |
| `.gitignore` | Standard Git ignore configuration. |
| `.devcontainer/` | VS Code Remote - Containers configuration for a consistent development environment. |
| `.github/` | GitHub Actions workflows and configuration. |
| `archive/` | Retired code, data, and previous implementations kept for reference. |
| `content/` | Local mirror of the Australian Government Style Manual, stored as markdown files. |
| `frontend/` | Source code for the React-based Octavius editor. |
| `library_of_rules/` | Authoritative source material and reference documentation for style rules. |
| `logic/` | Core Python logic for the linting engine and rule execution. |
| `pages/` | Additional Streamlit pages (e.g., the Developer window). |
| `prompts/` | Markdown templates used by the LLM in Phase 3 for generating rule trigger code. |
| `published/` | Final artifacts produced by the pipeline, including the rulebook in Parquet format. |
| `src/` | Python scripts implementing the six-phase rulebook creation pipeline. |
| `tests/` | Unit tests for the core linting engine. |

## Core Application Logic (`logic/`)

| File | Description |
| :--- | :--- |
| `engine.py` | The core linting engine. Contains `lint_text()` which runs a list of rules against a spaCy document and returns findings. |
| `rules.py` | Definitions of implemented rules, including the `RULES` registry and individual `check_*` functions (e.g., passive voice detection). |
| `sandbox.py` | A secure execution environment for user-provided Python code, enabling safe testing of new rules in the Developer window. |
| `__init__.py` | Marks the directory as a Python package. |

## Frontend (`frontend/`)

The React 18 frontend, built with TypeScript and Tailwind CSS. It is loaded as a custom component in Streamlit.

| File / Folder | Description |
| :--- | :--- |
| `src/OctaviusEditor.tsx` | The root React component that orchestrates the editor state and layout. |
| `src/components/` | Reusable UI components including the `TextEditor`, `FindingsPanel`, `FindingCard`, and `RulesPanel`. |
| `src/hooks/` | Custom React hooks: `useHighlights` for text segmentation and `useOctaviusState` for editor state management. |
| `src/types.ts` | Shared TypeScript interfaces for findings, rules, and component props. |
| `src/styles/` | Global CSS and Tailwind configuration. |
| `build/` | The compiled production build of the React application, served by Streamlit. |
| `public/` | Static assets and the HTML template for the standalone frontend. |
| `package.json` | Node.js dependencies and build scripts. |
| `tsconfig.json` | TypeScript compiler configuration. |
| `tailwind.config.js` | Tailwind CSS theme and plugin configuration. |

## Streamlit Pages (`pages/`)

| File | Description |
| :--- | :--- |
| `1_Developer.py` | A dedicated developer tool for testing rules from the spreadsheet and building new rules with AI assistance. |

## Rulebook Creation Pipeline (`src/`)

The scripts in this directory implement the six-phase automated pipeline for building the rulebook from the Australian Government Style Manual.

| Script | Phase | Description |
| :--- | :--- | :--- |
| `scrape.py` | 1 | Fetches the Style Manual sitemap and mirrors pages to markdown in the `content/` directory using Selenium and trafilatura. |
| `extract_rules.py` | 2 | Uses the OpenAI Batch API to extract discrete style rules from the mirrored markdown content into JSONL format. |
| `generate_code.py` | 3 | Uses the OpenAI Batch API to generate executable Python trigger code and test examples for each extracted rule. |
| `run_tests.py` | 4 | Executes the generated trigger code against its test examples to verify correctness. |
| `correct_rules.py` | 5 | Uses the OpenAI Batch API (GPT-4o) to fix rules that failed testing in Phase 4. |
| `publish.py` | 6 | Normalizes the validated rules and publishes them as a Snappy-compressed Parquet file in the `published/` directory. |

## LLM Prompts (`prompts/`)

Markdown templates used in Phase 3 of the pipeline to guide the LLM in generating trigger code for different rule taxonomies.

| File | Taxonomy |
| :--- | :--- |
| `regex.md` | Rules detectable via standard regular expressions. |
| `spacy.md` | Rules requiring spaCy token attributes (POS tags, dependencies, etc.). |
| `lookup.md` | Rules that flag words or phrases against a reference list. |
| `structural.md` | Rules based on document structure or patterns in raw text. |
| `semantic.md` | Prompt templates for rules requiring semantic LLM analysis. |
| `contextual.md` | Prompt templates for rules requiring contextual LLM analysis. |

## GitHub Workflows (`.github/workflows/`)

Automated CI/CD workflows for the pipeline phases.

| Workflow | Description |
| :--- | :--- |
| `phase1_scrape.yml` | Nightly job to mirror the Style Manual content. |
| `phase2_submit.yml` / `phase2_collect.yml` | Submits extraction jobs and collects results. |
| `phase3_submit.yml` / `phase3_collect.yml` | Submits code generation jobs and collects results. |
| `phase4_test.yml` | Runs verification tests on all rules. |
| `phase5_submit.yml` / `phase5_collect.yml` | Submits correction jobs for failing rules and collects fixes. |
| `phase6_publish.yml` | Manual workflow to publish the final Parquet rulebook. |

## Content and Reference (`library_of_rules/` and `content/`)

| Folder | Description |
| :--- | :--- |
| `library_of_rules/` | The authoritative source material for rules, catalogued from the Australian Government Style Manual. Organized by topic (e.g., Grammar, Punctuation, Accessibility). Includes `SiteMap.md` as a navigation index. |
| `content/` | A local mirror of the Style Manual website in markdown format, generated by Phase 1 of the pipeline. It serves as the input for rule extraction in Phase 2. |

## Published Artifacts (`published/`)

| File | Description |
| :--- | :--- |
| `rulebook.parquet` | The final, validated rulebook artifact produced by Phase 6. Optimized for performance and portable across analytical tools. |
| `rulebook_metadata.json` | Metadata for the published rulebook, including rule counts by taxonomy and the SHA-256 hash of the Parquet file. |

## Testing and Quality Assurance (`tests/`)

| File | Description |
| :--- | :--- |
| `test_engine.py` | Pytest suite for the `logic/engine.py` linting engine, ensuring findings are correctly identified and formatted. |
| `__init__.py` | Marks the directory as a Python package. |

## Archives and Legacy (`archive/`)

| Folder | Description |
| :--- | :--- |
| `RETIRED/` | Contains the legacy "Trinity" implementation and related report/config files. |
| `logic/` | Previous iterations of the linting logic and parsers. |
| `frontend/` | Older versions of the frontend implementation. |
| `data/` | Historical rulebooks in Excel format and source ZIP files. |
| `tests/` | Legacy test files for retired components. |

## Pipeline State Files

These files are located in the root directory and are used by the automated pipeline to maintain state across phases.

| File | Description |
| :--- | :--- |
| `sitemap_state.json` | Records the last-seen `lastmod` date for every URL in the Style Manual sitemap to enable incremental scraping. |
| `content_manifest.json` | A generated list of all mirrored markdown files and their SHA-256 hashes, ensuring content integrity. |
| `batch_state.json` | Stores active OpenAI Batch IDs and metadata during extraction and generation phases. |
| `amendment_log.json` | Tracks manual and LLM-assisted corrections made to rules during the refinement process. |
