# OCTAVIUS

**Frontend Rebuild — Implementation Specification**

*Option A: FastAPI + Static HTML/JS | Option C: React (Stretch Goal)*

*April 2026*

---

## 1. Background and Motivation

Octavius currently runs as a **Streamlit application**. Streamlit is appropriate for internal tooling and rapid prototyping, but it imposes two hard limitations that make it unsuitable as a longer-term frontend for this tool:

- **UI ownership:** The surrounding shell — layout, navigation, branding — belongs to Streamlit and cannot be meaningfully customised. The tool will always look like a Streamlit app.
- **Realtime interaction model:** Streamlit operates on a request/response cycle triggered by widget events. True keystroke-level feedback (spellcheck-style rule highlighting as the user types) is not achievable without significant workarounds, and even then the experience will feel laggy.

The rebuild addresses both issues. The Python rule execution logic does not change — only the interface layer is replaced.

---

## 2. Goals

| Goal | Description |
| --- | --- |
| **Realtime checking** | Rule violations surface as the user types, with a short debounce delay (~300ms). No submit button required. |
| **Rule group filtering** | Users can enable or disable groups of rules before or during a checking session. The active filter is sent with each API request. |
| **Full UI control** | The interface is plain HTML/CSS/JS (Option A) or React (Option C). No framework shell is visible to the user. |
| **Zero ongoing cost** | Frontend hosted free on GitHub Pages. Backend hosted on Render free tier. |
| **Python stays Python** | All rule execution logic remains in the existing FastAPI/Python stack. The frontend is purely presentational. |
| **Upgrade path preserved** | Option A is explicitly designed so that Option C (React) is a frontend swap only — no backend changes required. |

---

## 3. Architecture Overview

### 3.1 Option A — FastAPI Backend + Static HTML/JS Frontend

This is the primary implementation target. The system is split into two independently deployable units:

**Frontend (GitHub Pages):** A single HTML file with embedded CSS and vanilla JavaScript. No build step. No dependencies. Deployed by pushing to the `gh-pages` branch of the Octavius repository.

**Backend (Render):** A FastAPI application exposing a `/check` endpoint. Accepts a POST request containing the document text and a list of active rule group IDs. Returns a JSON array of violations. The existing Octavius rule execution engine powers this — no logic changes required.

Communication between the two is a standard HTTP fetch call. The frontend debounces keystrokes and fires a POST to the Render URL. Violations are rendered as inline highlights over the text area.

### 3.2 Option C — React Frontend (Stretch Goal)

Option C replaces the HTML/JS frontend with a **React application built with Vite**. The FastAPI backend is **unchanged**. React simply calls the same `/check` endpoint via `fetch()`.

Option C is appropriate when the UI becomes complex enough to benefit from component-based state management — for example, if rule violation panels, user preferences, session history, or multi-document support are added. It is not necessary for the initial working version.

Both options are deployed in the same way: static files to GitHub Pages. The only difference is that Option C requires a build step (`npm run build`) before deployment.

---

## 4. Infrastructure

| Component | Detail |
| --- | --- |
| **Frontend hosting** | GitHub Pages — free, permanent, no traffic limits for static files. Deploys via GitHub Actions on push to main. |
| **Backend hosting** | Render free tier — hosts the FastAPI Docker container or Python service. Spins down after 15 minutes of inactivity; first request after sleep takes ~30 seconds to wake. |
| **Custom domain** | Optional. GitHub Pages supports custom domains via CNAME. Render supports custom domains on paid plans. |
| **HTTPS** | Both GitHub Pages and Render provide HTTPS automatically at no cost. |
| **CORS** | FastAPI backend must include CORS middleware permitting requests from the GitHub Pages origin. |

### 4.1 Render Free Tier — Known Limitation

The Render free tier sleeps inactive services after 15 minutes. For a tool used regularly during work hours this is rarely a problem — the service stays warm. For sporadic use or sharing with external users, the cold-start delay will be noticeable.

Upgrade options if this becomes a problem, in order of cost:

- **Fly.io free tier:** 3 shared VMs included, does not sleep in the same way as Render. Slightly steeper CLI-based setup.
- **Railway hobby plan:** ~$5/month, lowest-friction option that stays consistently awake.
- **Oracle Cloud free tier:** ARM VM, genuinely free permanently, full control, requires self-managed uptime.

None of these changes affect the frontend or the rule logic.

---

## 5. API Contract

The frontend communicates with a single endpoint. The contract must remain stable across both Option A and Option C frontends.

### 5.1 POST /check

| Field | Value |
| --- | --- |
| **Method** | POST |
| **Content-Type** | application/json |
| **Auth** | None (internal tool). Add a bearer token if the endpoint becomes public. |

**Request body:**

```json
{
  "text": "The full document content as a string.",
  "rule_groups": ["punctuation", "capitalisation", "plain_language"]
}
```

**Response body:**

```json
[
  {
    "rule_id": "PUNC_001",
    "group": "punctuation",
    "message": "Oxford comma missing before final list item.",
    "start": 42,
    "end": 55,
    "severity": "warning"
  },
  ...
]
```

The `start` and `end` fields are character offsets into the submitted text string. The frontend uses these to render highlights.

---

## 6. Frontend Behaviour

### 6.1 Text input

- A large textarea (or `contentEditable` div) accepts the user's document text.
- On every keystroke, a debounce timer resets. After 300ms of inactivity, a `/check` request fires.
- A loading indicator (subtle spinner or status text) shows while a request is in flight.
- If a request is already in flight when a new one is triggered, the in-flight request is cancelled (`AbortController`).

### 6.2 Rule group filtering

- A panel (sidebar or top bar) lists all available rule groups sourced from the rulebook.
- Each group has a checkbox. All groups are enabled by default.
- Toggling a group immediately triggers a fresh `/check` request with the updated group list.
- Group selections persist in `localStorage` so they survive page refresh.

### 6.3 Violation rendering

- Violations are rendered as coloured underlines over the relevant text spans.
- **Warning severity:** amber/orange underline.
- **Error severity:** red underline.
- Hovering a violation shows a tooltip with the rule message.
- A summary panel below (or beside) the editor lists all active violations with their rule ID and message. Clicking a violation scrolls to and highlights the relevant span.

### 6.4 Highlight rendering — implementation note

Rendering underlines inside a textarea is not natively supported by browsers. Two standard approaches exist:

- **Overlaid div approach:** A transparent div is positioned precisely over the textarea. Highlight spans are injected into the div at the correct character offsets. The textarea background is set to transparent. This is the simplest approach for vanilla JS.
- **contentEditable approach:** Replace the textarea with a `contentEditable` div. Highlights are injected directly as styled spans. More powerful but requires careful handling of cursor position when re-rendering.

For Option A, the overlaid div approach is recommended. For Option C (React), libraries such as `react-highlight-within-textarea` or a custom `contentEditable` component are available.

---

## 7. Option A — Build Plan

### Step 1 — FastAPI endpoint

- Add a `/check` POST route to the existing FastAPI app.
- Add CORS middleware permitting the GitHub Pages origin.
- Wire the route to the existing rule execution engine, passing `text` and `rule_groups`.
- Return the violation array as JSON.
- Test locally with curl or Postman before touching the frontend.

### Step 2 — Deploy backend to Render

- Confirm Octavius has a `requirements.txt` and a `Procfile` or `render.yaml`.
- Connect the repository to Render. Set the start command to:
  ```
  uvicorn main:app --host 0.0.0.0 --port $PORT
  ```
- Note the deployed Render URL (e.g. `https://octavius.onrender.com`).

### Step 3 — Build the static frontend

- Create a single `index.html` file containing all HTML, CSS, and JavaScript.
- Hardcode the Render URL as a JS constant (or use a `.env`-style approach at build time if needed later).
- Implement the debounced fetch, violation rendering, and rule group checkboxes as described in Section 6.
- Test against the live Render endpoint.

### Step 4 — Deploy to GitHub Pages

- Enable GitHub Pages on the repository (Settings → Pages → Deploy from branch).
- Push `index.html` to the configured branch (`gh-pages` or `docs/` on main).
- Confirm the page loads and the `/check` endpoint responds.

**Estimated effort:**
- Steps 1–2 (backend): 2–4 hours assuming existing rule engine is callable as a function.
- Steps 3–4 (frontend): 3–6 hours for a functional but unstyled version. Visual polish is additional.

---

## 8. Option C — React Stretch Goal

**The FastAPI backend does not change when moving from Option A to Option C.** React calls the same `/check` endpoint. Option C is a frontend replacement only.

### 8.1 When to consider the upgrade

- The UI grows beyond what vanilla JS can manage cleanly (multiple panels, complex state, user preferences).
- Multi-document support, session history, or export features are added.
- Another developer joins and the codebase benefits from component structure.

### 8.2 What changes

| Component | Change |
| --- | --- |
| **Build tooling** | Vite (`npm create vite@latest`). Replaces the single HTML file with a `src/` directory of `.jsx` components. |
| **Deployment** | `npm run build` produces a `dist/` folder. This is pushed to GitHub Pages instead of the raw HTML file. A GitHub Actions workflow handles this automatically. |
| **State management** | `useState` and `useEffect` replace vanilla JS variables and event listeners. No external state library (Redux etc.) needed at this scale. |
| **Highlight rendering** | A `contentEditable` component or a library like `react-highlight-within-textarea` handles in-editor violation spans. |
| **Styling** | Tailwind CSS (via CDN or PostCSS) or plain CSS modules. Choice does not affect the backend. |

### 8.3 What does not change

- FastAPI backend — zero changes.
- The `/check` API contract — zero changes.
- Render deployment — zero changes.
- GitHub Pages hosting — same platform, different files.
- Rule logic, rulebook format, Parquet pipeline — untouched.

### 8.4 Migration path

Option A and Option C can run in parallel during transition. Both frontends can point at the same Render backend URL. Build Option C in a feature branch, test it, then swap the GitHub Pages deployment source. The Option A HTML file can be archived rather than deleted.

---

## 9. Out of Scope

The following are not part of the Option A deliverable and are noted here to keep the initial build focused. They are not ruled out permanently.

- Authentication and user accounts.
- Saving or exporting checked documents.
- Rule editing or management via the frontend.
- Multi-user collaboration.
- Mobile-optimised layout (desktop-first is sufficient for this tool).

---

## 10. Decision Summary

| Decision | Choice |
| --- | --- |
| **Build target** | Option A — FastAPI backend + single HTML/JS frontend |
| **Frontend hosting** | GitHub Pages (free, no build step required for Option A) |
| **Backend hosting** | Render free tier |
| **Realtime model** | Debounced POST on keyup, 300ms delay, AbortController for in-flight cancellation |
| **Highlight rendering** | Overlaid transparent div positioned over textarea |
| **Rule filtering** | Checkbox panel per rule group, selections persisted in localStorage |
| **Stretch goal** | Option C — Vite + React frontend, same backend, same hosting platforms |
| **Backend changes for Option C** | None |

---

*Octavius Frontend Specification | April 2026*
