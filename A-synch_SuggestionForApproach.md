Suggestion for updating Octavius front-end to an **Asynchronous Event-Driven Pipeline** utilizing a **Shared-Nothing Multi-Threaded Architecture**. For a system engineer, the implementation can be described through three core architectural patterns:

### 1. The Debounced "Twin-Track" Observer Pattern
To maintain a 60FPS UI while running heavy computations, the system decouples the **Primary Event Loop** (User Input) from the **Analysis Pipeline** (Rule Checking).

* **State Synchronization (Shadow Document):** The application maintains a lightweight, read-only representation of the text buffer (the "Shadow Document") in a background thread or Web Worker. 
* **Debounce Trigger:** Keystrokes are not processed immediately. Instead, each input event resets a high-resolution timer (e.g., 300ms). Only when the timer expires—indicating a "natural pause"—is the `Snapshot` passed to the analysis engine.
* **Dirty-Range Tracking:** To avoid $O(n)$ re-processing of the entire document, the system tracks "dirty" indices. The background worker only re-runs the expensive linguistic parsing on the affected paragraph/block, while maintaining a persistent cache for unchanged blocks.

### 2. Multi-Stage Pipeline (Waterfall Filter)
The 2,800 rules are not executed as a flat list; they are organized into an **Inference Hierarchy** to optimize for CPU throughput and power consumption.

* **Stage 1: Aho-Corasick Automaton (Deterministic):** ~800 lookup rules are compiled into a single state machine. This allows for $O(length\_of\_text)$ search complexity. All keyword violations are found in a single memory sweep.
* **Stage 2: Dependency Parsing (Structural):** The system passes the text through a **spaCy/Cython pipeline**. It generates a **Directed Acyclic Graph (DAG)** of the sentence structure. Grammatical rules are executed as queries against this graph (e.g., "Flag if `AUX` node is parent to `VBN` node with `by` agent").
* **Stage 3: Vector Embeddings (Fuzzy Matching):** Remaining semantic rules are checked using **Cosine Similarity** between the current sentence vector (generated via a local Bi-encoder like `all-MiniLM-L6-v2`) and a pre-indexed vector store of rule violations.
* **Stage 4: LLM/SLM (Reasoning):** The most expensive "intelligence" (e.g., the protective markings check) is only invoked as a **Conditional Branch**. If Stages 1–3 return a high "Ambiguity Score," the segment is sent to an SLM (Phi-4-mini) for final verification.

### 3. Coordinate Interop (The Incidents Map)
The background thread does not modify the user's text. It operates as a **Pure Function**: `f(DocumentState) -> List[Incident]`.

* **Incident Schema:** Each violation is returned as a data object containing `(StartOffset, EndOffset, RuleID, Metadata)`.
* **The Merge:** The UI thread receives this JSON list asynchronously. It performs a **Z-Index Layering**—it keeps the text on one layer and renders the "Squiggly Lines" on a separate SVG/Canvas layer positioned directly over the text coordinates.
* **Optimistic UI:** When the user begins typing inside a flagged range, the UI "optimistically" clears the squiggly line immediately before the background thread confirms the fix, preventing visual "ghosting."

### System Constraints Summary
* **Concurrency:** Shared-memory read access for the Shadow Document; message-passing (IPC) for the Result Set.
* **Latency Target:** <50ms for local rules (Stage 1-2); <200ms for semantic rules (Stage 3).
* **Complexity:** Stage 1 is $O(n)$; Stage 2 is $O(n)$; Stage 3 is $O(log\ n)$ with an HNSW index.

### Important note
- **Stage 2.** The 'Waterfall Filter' is a potential *future* state and should NOT be considered as within scope for the V1 deployment. Simply applying the rules whose "test_result": "pass" is the intent for the intial pass.
- Users should be allowed to turn off individual rules or in batches by their rule ID and/or their taxonomy.
