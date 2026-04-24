# SystemHealth Implementation Guide

Date: 2026-04-23

## Purpose

This document describes the current runtime implementation of SystemHealth, the backend and frontend surfaces that exist today, how they map to the wireframes, and what is still missing.

Use this as the primary engineering reference for:

- current architecture
- implemented APIs
- implemented runtime screens
- edge-device data collection
- known gaps and next steps

For design intent and wireframe usage, see [DESIGN_USAGE.md](/home/ds/Documents/Development/SchoolofAI/SystemHealth/DESIGN_USAGE.md:1).

## Runtime Architecture

### Backend

The runtime backend is a FastAPI application served from:

- [app/main.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/main.py:1)

It starts collectors, analytics tasks, API routers, websocket streams, and static-file serving for the runtime dashboard.

### Frontend

The runtime dashboard is served from:

- [dashboard.html](/home/ds/Documents/Development/SchoolofAI/SystemHealth/dashboard.html:1)
- [dashboard.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/dashboard.jsx:1)
- [dashboard.css](/home/ds/Documents/Development/SchoolofAI/SystemHealth/dashboard.css:1)

The runtime dashboard is a live operational UI backed by FastAPI APIs and websocket streams.

### Wireframes

The design wireframes remain separate from the runtime dashboard and are served from:

- [SystemHealth Wireframes.html](/home/ds/Documents/Development/SchoolofAI/SystemHealth/SystemHealth%20Wireframes.html:1)
- [wf1-cockpit.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf1-cockpit.jsx:1)
- [wf2-sidebar.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf2-sidebar.jsx:1)
- [wf3-terminal.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf3-terminal.jsx:1)
- [wf4-editorial.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf4-editorial.jsx:1)
- [wf5-leakhunter.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/wf5-leakhunter.jsx:1)

The runtime app now mirrors more of these layouts, but it is still not a 1:1 reproduction.

## Edge Data Collection

### Collectors currently implemented

- [app/collectors/psutil_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/psutil_collector.py:1)
  - CPU
  - memory
  - disk
  - network
  - temperatures
  - process snapshots

- [app/collectors/jtop_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/jtop_collector.py:1)
  - Jetson GPU load
  - GPU memory
  - SoC temperature
  - power draw
  - fan

- [app/collectors/journald_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/journald_collector.py:1)
  - system/service logs
  - journald-derived log streaming

- [app/collectors/crash_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/crash_collector.py:1)
  - crash-like signal detection from journald
  - exit code pattern detection

- [app/collectors/filelog_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/filelog_collector.py:1)
  - structured or plain-text app logs from configured files/directories

### Analytics currently implemented

- [app/analytics/leak.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/analytics/leak.py:1)
  - RSS leak slope
  - rolling regression
  - TTL to OOM

- [app/analytics/health.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/analytics/health.py:1)
  - overall health score
  - drivers based on CPU, memory, disk, temperature, leaks, crashes

## Storage

### SQLite

- [app/db/sqlite.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/db/sqlite.py:1)

Used for:

- metrics history
- process RSS history
- event storage
- downsampling

Recent hardening:

- write serialization
- WAL mode
- busy timeout
- reduced `database is locked` failures

### DuckDB

- [app/db/duckdb.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/db/duckdb.py:1)

Used for:

- log ingestion
- log queries
- log clustering
- service log summaries

## Implemented APIs

### Core runtime APIs

- `GET /api/meta`
  - metadata about host, arch, uptime, capabilities

- `GET /api/system/current`
  - current system snapshot

- `GET /api/system/history`
  - historical metric series

- `GET /api/processes`
  - current process list

- `GET /api/processes/{pid}/rss`
  - RSS history for a specific process

- `GET /api/logs`
  - log query endpoint

- `GET /api/logs/cluster`
  - grouped error/log cluster summaries

- `GET /api/logs/histogram`
  - grouped log counts over time

- `GET /api/health`
  - latest health score payload

- `GET /api/leaks`
  - current leak detector output

- `GET /api/crashes`
  - crash signal counts and recent events

- `GET /api/units`
  - systemd/service state with derived severity and log/crash context

- `POST /api/diagnose`
  - on-demand incident diagnosis using current context and KB matches

### App-centric APIs

- `GET /api/apps`
  - derived app-centric summary list
  - combines process, leak, log, crash, and service data

- `GET /api/apps/{name}`
  - selected app detail
  - includes RSS history for matched process

### Briefing API

- `GET /api/briefing`
  - editorial-style payload for the briefing screen
  - includes:
    - headline
    - health
    - featured incident
    - watched apps summary
    - log clusters
    - context digest

### Websocket streams

- `/ws/system`
- `/ws/processes`
- `/ws/logs`
- `/ws/leaks`
- `/ws/health`
- `/ws/jetson`

## Runtime Screen Coverage

### Implemented screens

- `overview`
  - current cockpit-style live view

- `focus`
  - app-focused screen
  - backed by `/api/apps` and `/api/apps/{name}`

- `terminal`
  - terminal-like operations screen
  - backed by live streams plus `/api/units` and `/api/logs`

- `briefing`
  - editorial-style summary screen
  - backed by `/api/briefing`

- `hunter`
  - leak-hunter style app memory table
  - backed by `/api/apps`

- `processes`
- `services`
- `leaks`
- `logs`
- `crashes`
- `diagnose`

### Current mapping from wireframes to runtime

- `W1_Cockpit`
  - represented by `overview` plus `services` and `logs`

- `W2_Sidebar`
  - represented by `focus`

- `W3_Terminal`
  - represented by `terminal`

- `W4_Editorial`
  - represented by `briefing`

- `W5_LeakHunter`
  - represented by `hunter`

## Configuration

Defined in [app/config.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/config.py:1).

Important runtime variables:

- `SH_LOG_APP_DIRS`
  - list of app-log files or directories to ingest

- `SH_MONITORED_APPS`
  - list of preferred app names for app-centric views

- `SH_LLAMA_URL`
- `SH_OLLAMA_URL`
- `SH_LLM_MODEL`

## Current Gaps

### Not yet implemented

- persistent monitored-app registry
- UI for adding/removing monitored apps
- Docker/container runtime collector
- container-focused app import flow
- interactive restart/action controls
- per-thread CPU profiling
- py-spy or dump capture flow
- persistent app identity model beyond heuristic matching
- dedicated websocket streams for app and briefing payloads

### Design mismatch that still remains

- runtime screens use live data and are more compact than the wireframes
- some wireframe decorative annotations and storytelling elements are simplified
- several operational chips/buttons in wireframes are present only as visual concepts, not executable actions

## Recommended Next Steps

1. Add persistent monitored-app storage in SQLite.
2. Add CRUD endpoints for monitored apps.
3. Add UI to choose apps from:
   - processes
   - systemd services
   - Docker containers
   - custom names
4. Add Docker/container collectors.
5. Add app-specific websocket streams for focus/hunter/briefing.
6. Add guarded operational actions only after authentication and safety rules are defined.

## Files Most Relevant To This Implementation

- [app/main.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/main.py:1)
- [app/config.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/config.py:1)
- [app/api/apps.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/api/apps.py:1)
- [app/api/briefing.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/api/briefing.py:1)
- [app/api/derived.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/api/derived.py:1)
- [app/api/processes.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/api/processes.py:1)
- [app/api/logs.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/api/logs.py:1)
- [app/collectors/psutil_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/psutil_collector.py:1)
- [app/collectors/jtop_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/jtop_collector.py:1)
- [app/collectors/journald_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/journald_collector.py:1)
- [app/collectors/filelog_collector.py](/home/ds/Documents/Development/SchoolofAI/SystemHealth/app/collectors/filelog_collector.py:1)
- [dashboard.jsx](/home/ds/Documents/Development/SchoolofAI/SystemHealth/dashboard.jsx:1)
- [dashboard.css](/home/ds/Documents/Development/SchoolofAI/SystemHealth/dashboard.css:1)
