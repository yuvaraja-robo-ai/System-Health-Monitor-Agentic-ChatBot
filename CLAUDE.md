# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

No build step. Open `SystemHealth Wireframes.html` in a browser directly, or serve via any static file server:

```bash
python3 -m http.server 8080
# then open http://localhost:8080/SystemHealth%20Wireframes.html
```

React 18, ReactDOM, and Babel standalone are loaded from CDN (unpkg). JSX is transpiled in-browser at runtime — no compilation needed.

## Architecture

**Entry point:** `SystemHealth Wireframes.html` — bootstraps React, defines a `TWEAK_DEFAULTS` block (e.g. `host: "jetson"`), and mounts all wireframe components. The `useTweaks` hook persists tweaks to `localStorage` and communicates with a parent frame via `postMessage` for live-edit mode.

**Layer 1 — Canvas (`design-canvas.jsx`):** Figma-style design canvas. Exports `DesignCanvas`, `DCSection`, `DCArtboard`, `DCPostIt` to `window`. Handles pan/zoom viewport (mouse-wheel, trackpad pinch, Safari `gesturestart`), drag-to-reorder artboards within sections, inline label editing, and a fullscreen focus overlay. Canvas layout state persists to `.design-canvas.state.json` via `window.omelette.writeFile` (only works in omelette preview host).

**Layer 2 — Primitives (`primitives.jsx`):** Shared low-fi wireframe UI components exported to `window`: `Sparkline`, `BarHisto`, `UsageBar`, `LogLine`, `AppRow`, `WireframeFrame`. Uses deterministic seeded PRNG (`seedRand`) so sparklines are stable across re-renders.

**Layer 3 — Wireframes (`wf1-cockpit.jsx` … `wf5-leakhunter.jsx`):** One React component per screen, each accepting `host` prop (`"jetson"` | `"ubuntu"`) to toggle Jetson-specific fields (GPU vs Net). Screens:
- `W1_Cockpit` — dense single-pane ops overview (health score, KPIs, logs, processes)
- `W2_Sidebar` — sidebar navigation shell
- `W3_Terminal` — terminal / log explorer view
- `W4_Editorial` — editorial / alert detail view
- `W5_LeakHunter` — app-centric memory leak detection

**Styles (`styles.css`):** CSS custom properties (`--paper`, `--ink`, `--teal`, `--amber`, `--rose`, `--font-hand`, `--font-mono`, `--font-ui`). Class-based primitives: `.box`, `.chip`, `.row`, `.col`, `.grid`, `.spark`.

## Key conventions

- All JSX files use `/* global React, ... */` comments to declare browser globals — no imports.
- Components exported via `Object.assign(window, {...})` at end of each file; load order in the HTML matters.
- `host` prop drives Jetson-vs-Ubuntu conditional rendering throughout all wireframes.
- Sparkline `trend` values: `"flat"`, `"up"`, `"down"`, `"spike"`, `"leak"`.
