# SystemHealth Design Usage Guide

Date: 2026-04-23

## Purpose

This document explains how to use the wireframes as the design source of truth when implementing or extending the runtime application.

Use this document when:

- building new runtime screens
- deciding how a feature should be presented
- checking whether a runtime API is sufficient for a wireframe
- planning missing implementation work from design intent

For the engineering implementation state, see [IMPLEMENTATION.md](/home/ds/Documents/Development/SchoolofAI/SystemHealth/IMPLEMENTATION.md:1).

## Design Source Files

Main design entry:

- [SystemHealth Wireframes.html](/home/ds/Documents/Development/SchoolofAI/SystemHealth/SystemHealth%20Wireframes.html:1)

Supporting design files:

- [design-canvas.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/design-canvas.jsx:1)
- [primitives.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/primitives.jsx:1)
- [styles.css](/home/ds/Documents/Development/SchoolofAI/SystemHealth/styles.css:1)

Screen wireframes:

- [wf1-cockpit.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf1-cockpit.jsx:1)
- [wf2-sidebar.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf2-sidebar.jsx:1)
- [wf3-terminal.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf3-terminal.jsx:1)
- [wf4-editorial.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf4-editorial.jsx:1)
- [wf5-leakhunter.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf5-leakhunter.jsx:1)

## How To Use The Wireframes

### Treat the wireframes as behavioral intent, not pixel-perfect UI

The runtime dashboard should preserve:

- information hierarchy
- screen purpose
- user workflow
- expected data groupings
- required backend capabilities

It does not need to replicate:

- every annotation
- exact hand-drawn presentation
- static sample labels
- decorative layout details that do not add runtime value

### Read each wireframe in two passes

1. Identify the screen purpose.
2. Extract the data requirements and interactions.

Example:

- `W5_LeakHunter` is not just a table.
  - it implies:
    - app selection
    - leak ranking
    - TTL to OOM
    - crash history
    - restart counts
    - custom app logs

That means the implementation work is both:

- frontend screen work
- backend data-shaping work

## Per-Screen Usage Guidance

### `W1_Cockpit`

Intent:

- dense single-pane operational overview
- quick scanning
- wallboard or operator-at-a-glance usage

Implementation implications:

- top-line health score must be visible immediately
- KPIs should be live
- failing services and live logs must be adjacent to system KPIs
- watched apps should be visible on the same screen

Use when:

- designing the default landing page
- building NOC/operator views

### `W2_Sidebar`

Intent:

- app-centric navigation
- choose one app, then inspect only that app’s world

Implementation implications:

- requires a monitored-app concept
- requires selected-app detail endpoint
- requires recent logs, leak state, crash history, and service context for the selected app

Use when:

- building customer-facing investigation flow
- reducing operator overload from full-system views

### `W3_Terminal`

Intent:

- SSH/headless-friendly mental model
- browser UI that still feels like a TUI

Implementation implications:

- monospace presentation is part of the experience
- process, unit, and log data must remain compact
- should support keyboard-first workflows in future iterations

Use when:

- implementing device-local diagnostics
- supporting engineers who think in terminal layouts

### `W4_Editorial`

Intent:

- narrative summary
- async-friendly incident briefing
- top-down reading order

Implementation implications:

- needs a summarized headline
- needs a featured incident
- needs prioritized clusters and suggested actions
- works best with derived backend payloads instead of only raw tables

Use when:

- building daily briefings
- providing escalation summaries
- presenting “what matters now”

### `W5_LeakHunter`

Intent:

- memory leak detection as the spine of the experience
- customer apps are first-class entities

Implementation implications:

- leak data must be app-centric, not only pid-centric
- crash/restart history must sit near memory story
- app logs are part of the diagnosis flow
- UI should answer:
  - which app is drifting
  - how fast
  - when it will become critical
  - what else supports that diagnosis

Use when:

- implementing memory-health and stability tooling
- prioritizing GPU/Jetson inference services and long-running edge applications

## Host-Mode Design Rule

The wireframes support two host modes:

- `jetson`
- `ubuntu`

Any runtime screen derived from the wireframes should preserve host-aware behavior:

- Jetson mode should surface:
  - GPU
  - SoC temperature
  - power draw
  - fan

- Ubuntu/x86 mode should surface:
  - disk
  - network
  - general platform metrics

This design rule comes from:

- [SystemHealth Wireframes.html](/home/ds/Documents/Development/SchoolofAI/SystemHealth/SystemHealth%20Wireframes.html:1)
- [wf1-cockpit.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf1-cockpit.jsx:1)
- [wf2-sidebar.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf2-sidebar.jsx:1)
- [wf3-terminal.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf3-terminal.jsx:1)

## Design-To-Implementation Checklist

When implementing from a wireframe, check all of the following:

- What is the primary entity?
  - host
  - app
  - service
  - incident

- What is the decision the user should make on this screen?

- What backend payload would make this screen simple to render?

- Is the runtime implementation currently using raw data where a derived API would be more appropriate?

- Does the screen need:
  - live websocket data
  - polling
  - historical metrics
  - clustered logs
  - leak ranking
  - crash grouping
  - service state

- Does the screen imply a missing collector?
  - Docker
  - container logs
  - restart counts
  - app registry

## Current Design-Driven Missing Work

The wireframes still imply the following missing implementation areas:

- persistent monitored app management
- Docker/container import path
- app registry UI
- richer action model
- better app identity correlation between:
  - process name
  - systemd unit
  - file logs
  - crash events
- stronger briefing generation and incident confidence model

## Recommended Usage Pattern For Future Work

When adding a new feature:

1. Start from the relevant wireframe.
2. Write down the data contract the screen actually needs.
3. Add or reshape backend APIs first.
4. Implement the runtime screen second.
5. Keep decorative wireframe elements optional unless they improve clarity.

This avoids building screens that look closer to the wireframes but still lack the required edge-device data model.
