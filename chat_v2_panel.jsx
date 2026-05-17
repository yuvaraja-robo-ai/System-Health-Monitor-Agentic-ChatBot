/* global React, ReactDOM */
/*
 * ai_core chat panel v2 — full-width slide-in panel.
 * WS /api/chat_v2/stream → real-time log + generative UI cards
 */

(function mountAiCoreChat() {
  if (!window.React || !window.ReactDOM) { setTimeout(mountAiCoreChat, 100); return; }
  const { useState, useRef, useEffect, useCallback } = React;
  const h = React.createElement;

  // ── styles ────────────────────────────────────────────────────────────────
  const STYLE_ID = "aicore-chat-style-v2";
  if (!document.getElementById(STYLE_ID)) {
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = `
      @keyframes acspin { to { transform: rotate(360deg); } }
      @keyframes acslide { from { opacity:0; transform:translateX(40px); } to { opacity:1; transform:none; } }
      @keyframes acfade  { from { opacity:0; } to { opacity:1; } }
      @keyframes acpulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.55; transform:scale(.92); } }

      #aicore-root * { box-sizing: border-box; }
      #aicore-root { font: 13px/1.5 'Inter', system-ui, sans-serif; }

      /* FAB */
      #aicore-root .ac-fab {
        position: fixed; bottom: 24px; right: 24px; z-index: 9990;
        display: flex; align-items: center; gap: 8px;
        padding: 12px 20px; border-radius: 999px;
        background: linear-gradient(135deg, #1d4ed8, #7c3aed);
        color: #fff; border: 0; cursor: pointer;
        font: 600 14px Inter; box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        transition: transform .15s, box-shadow .15s;
      }
      #aicore-root .ac-fab:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(0,0,0,0.3); }
      #aicore-root .ac-fab .pulse {
        width: 8px; height: 8px; border-radius: 50%; background: #4ade80;
        box-shadow: 0 0 0 0 rgba(74,222,128,.6);
        animation: pulse 2s infinite;
      }
      @keyframes pulse { 70%{box-shadow:0 0 0 8px rgba(74,222,128,0)} 100%{box-shadow:0 0 0 0 rgba(74,222,128,0)} }

      /* Panel */
      #aicore-root .ac-panel {
        position: fixed; top: 0; right: 0; bottom: 0; z-index: 9991;
        width: min(680px, 100vw);
        background: #0f172a; color: #e2e8f0;
        display: flex; flex-direction: column;
        box-shadow: -8px 0 40px rgba(0,0,0,0.4);
        animation: acslide .2s ease-out;
      }

      /* Header */
      #aicore-root .ac-header {
        padding: 14px 18px; background: #0f172a;
        border-bottom: 1px solid #1e293b;
        display: flex; align-items: center; gap: 10px;
        flex-shrink: 0;
      }
      #aicore-root .ac-header .title { flex: 1; }
      #aicore-root .ac-header .title h2 {
        margin: 0; font: 700 15px Inter; color: #f1f5f9;
        display: flex; align-items: center; gap: 8px;
      }
      #aicore-root .ac-header .title p {
        margin: 2px 0 0; font-size: 11px; color: #64748b;
      }
      #aicore-root .ac-close {
        width: 28px; height: 28px; border-radius: 6px;
        background: #1e293b; border: 0; cursor: pointer;
        color: #94a3b8; font-size: 16px; display: flex;
        align-items: center; justify-content: center;
        transition: background .1s;
      }
      #aicore-root .ac-close:hover { background: #334155; color: #f1f5f9; }

      /* Status bar */
      #aicore-root .ac-status {
        padding: 8px 18px; background: #0d1b2e;
        border-bottom: 1px solid #1e293b;
        display: flex; align-items: center; gap: 10px;
        font-size: 12px; color: #38bdf8; flex-shrink: 0;
      }
      #aicore-root .ac-status .spinner {
        width: 14px; height: 14px; border: 2px solid #1e3a5f;
        border-top-color: #38bdf8; border-radius: 50%;
        animation: acspin .7s linear infinite; flex-shrink: 0;
      }
      #aicore-root .ac-status .turn-badge {
        margin-left: auto; padding: 2px 8px; border-radius: 4px;
        background: #1e3a5f; font-size: 11px; color: #7dd3fc;
      }

      /* Tabs */
      #aicore-root .ac-tabs {
        display: flex; border-bottom: 1px solid #1e293b; flex-shrink: 0;
        background: #0f172a;
      }
      #aicore-root .ac-tab {
        padding: 9px 16px; border: 0; background: transparent;
        color: #64748b; cursor: pointer; font: 500 12px Inter;
        border-bottom: 2px solid transparent;
        transition: color .15s, border-color .15s;
      }
      #aicore-root .ac-tab:hover { color: #94a3b8; }
      #aicore-root .ac-tab.active { color: #38bdf8; border-bottom-color: #38bdf8; }
      #aicore-root .ac-tab .badge {
        margin-left: 5px; padding: 1px 5px; border-radius: 9px;
        background: #1e293b; font-size: 10px; color: #94a3b8;
      }
      #aicore-root .ac-tab.active .badge { background: #1e3a5f; color: #7dd3fc; }

      /* Body */
      #aicore-root .ac-body { flex: 1; overflow-y: auto; padding: 16px 18px; }
      #aicore-root .ac-body::-webkit-scrollbar { width: 4px; }
      #aicore-root .ac-body::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }

      /* Log panel */
      #aicore-root .ac-log {
        font: 11px/1.6 'Geist Mono', ui-monospace, monospace;
        background: #020817; border: 1px solid #1e293b; border-radius: 8px;
        padding: 10px 12px; max-height: 240px; overflow-y: auto;
      }
      #aicore-root .ac-log::-webkit-scrollbar { width: 3px; }
      #aicore-root .ac-log::-webkit-scrollbar-thumb { background: #334155; }
      #aicore-root .log-line { padding: 1px 0; display: flex; gap: 6px; align-items: baseline; }
      #aicore-root .log-icon { flex-shrink: 0; width: 14px; text-align: center; font-size: 10px; }
      #aicore-root .log-tag  { flex-shrink: 0; font: 600 9px Inter; letter-spacing: .04em; min-width: 120px; opacity: .7; }
      #aicore-root .log-rest { flex: 1; white-space: pre-wrap; word-break: break-all; }

      /* phase tags */
      #aicore-root .log-line.phase-init    { color: #94a3b8; }
      #aicore-root .log-line.phase-gw      { color: #64748b; }
      #aicore-root .log-line.phase-mcp     { color: #38bdf8; }
      #aicore-root .log-line.phase-verify  { color: #818cf8; }
      #aicore-root .log-line.phase-verdict { color: #a78bfa; font-weight: 600; }

      /* react step tags */
      #aicore-root .log-line.react-req      { color: #7dd3fc; }
      #aicore-root .log-line.react-resp     { color: #38bdf8; font-weight: 600; }
      #aicore-root .log-line.react-cot      { color: #c084fc; font-style: italic; }
      #aicore-root .log-line.react-thinking { color: #818cf8; font-style: italic; }
      #aicore-root .log-line.react-dispatch { color: #facc15; font-weight: 600; }
      #aicore-root .log-line.react-result   { color: #34d399; }
      #aicore-root .log-line.react-observe  { color: #475569; }
      #aicore-root .log-line.react-final    { color: #a78bfa; font-weight: 700; }
      #aicore-root .log-line.react-empty    { color: #475569; }
      #aicore-root .log-line.react-text     { color: #94a3b8; }

      /* utility */
      #aicore-root .log-line.error  { color: #f87171; }
      #aicore-root .log-line.warn   { color: #fbbf24; }
      #aicore-root .log-line.info   { color: #94a3b8; }
      #aicore-root .log-line.prompt { color: #e2e8f0; font-weight: 600; }
      #aicore-root .log-line.debug  { color: #475569; }

      /* Cards */
      #aicore-root .ac-card {
        background: #1e293b; border: 1px solid #334155;
        border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;
        animation: acfade .3s ease-out;
      }
      #aicore-root .ac-card-label {
        font: 600 10px Inter; color: #64748b;
        text-transform: uppercase; letter-spacing: .06em; margin-bottom: 8px;
        display: flex; align-items: center; gap: 6px;
      }
      #aicore-root .ac-card-label .dot {
        width: 6px; height: 6px; border-radius: 50%; background: #38bdf8; flex-shrink: 0;
      }

      /* Metric tile */
      #aicore-root .metric-val { font: 700 32px Inter; color: #f1f5f9; line-height: 1; }
      #aicore-root .metric-val .unit { font: 400 14px Inter; color: #64748b; margin-left: 4px; }
      #aicore-root .metric-meta { margin-top: 6px; font-size: 12px; color: #64748b; }
      #aicore-root .metric-delta { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; margin-top: 4px; }
      #aicore-root .metric-delta.up { color: #f87171; }
      #aicore-root .metric-delta.down { color: #4ade80; }
      #aicore-root .threshold-bar { margin-top: 8px; height: 4px; border-radius: 2px; background: #0f172a; overflow: hidden; }
      #aicore-root .threshold-fill { height: 100%; border-radius: 2px; transition: width .5s; }

      /* Sparkline */
      #aicore-root svg.spark { display: block; width: 100%; height: 60px; }
      #aicore-root svg.spark .spark-area { fill: url(#sparkGrad); stroke: none; }
      #aicore-root svg.spark .spark-line { fill: none; stroke-width: 2; stroke-linecap: round; }

      /* Table */
      #aicore-root table.ac-table { width: 100%; border-collapse: collapse; font-size: 12px; }
      #aicore-root table.ac-table th {
        font: 600 10px Inter; color: #64748b; text-transform: uppercase;
        letter-spacing: .05em; padding: 6px 8px; border-bottom: 1px solid #334155;
        text-align: left;
      }
      #aicore-root table.ac-table td { padding: 7px 8px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }
      #aicore-root table.ac-table tr:last-child td { border-bottom: 0; }
      #aicore-root table.ac-table tr:hover td { background: #263348; }

      /* Process list */
      #aicore-root .proc-row { display: flex; align-items: center; gap: 8px; padding: 7px 0; border-bottom: 1px solid #1e293b; }
      #aicore-root .proc-row:last-child { border-bottom: 0; }
      #aicore-root .proc-name { font: 600 13px 'Geist Mono', ui-monospace; color: #e2e8f0; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      #aicore-root .proc-pid  { font-size: 11px; color: #475569; }
      #aicore-root .proc-cpu  { font: 700 13px Inter; min-width: 44px; text-align: right; }
      #aicore-root .proc-rss  { font-size: 12px; color: #64748b; min-width: 60px; text-align: right; }
      #aicore-root .cpu-bar   { flex: 1; height: 4px; background: #0f172a; border-radius: 2px; overflow: hidden; max-width: 80px; }
      #aicore-root .cpu-bar-fill { height: 100%; border-radius: 2px; }
      #aicore-root .proc-flag { padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }
      #aicore-root .proc-flag.high { background: #450a0a; color: #fca5a5; }
      #aicore-root .proc-flag.warn { background: #451a03; color: #fdba74; }

      /* Alert */
      #aicore-root .ac-alert { border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }
      #aicore-root .ac-alert.ok   { background: #052e16; border: 1px solid #166534; }
      #aicore-root .ac-alert.warn { background: #1c1003; border: 1px solid #92400e; }
      #aicore-root .ac-alert.crit { background: #1c0505; border: 1px solid #991b1b; }
      #aicore-root .ac-alert .alert-title { font: 700 13px Inter; margin-bottom: 4px; }
      #aicore-root .ac-alert.ok .alert-title   { color: #4ade80; }
      #aicore-root .ac-alert.warn .alert-title { color: #fbbf24; }
      #aicore-root .ac-alert.crit .alert-title { color: #f87171; }
      #aicore-root .ac-alert .alert-msg { font-size: 12px; color: #94a3b8; }

      /* KB doc */
      #aicore-root .kb-doc { border-left: 3px solid #38bdf8; padding-left: 12px; }
      #aicore-root .kb-doc .kb-title { font: 700 13px Inter; color: #7dd3fc; margin-bottom: 6px; }
      #aicore-root .kb-step { font-size: 12px; color: #94a3b8; padding: 2px 0; padding-left: 14px; position: relative; }
      #aicore-root .kb-step::before { content: "→"; position: absolute; left: 0; color: #38bdf8; }

      /* Text card */
      #aicore-root .text-body { font-size: 13px; color: #cbd5e1; white-space: pre-wrap; line-height: 1.6; }

      /* Thinking */
      #aicore-root details.ac-thinking {
        background: #13113a; border: 1px solid #312e81;
        border-radius: 8px; margin-bottom: 10px;
      }
      #aicore-root details.ac-thinking summary {
        padding: 8px 12px; cursor: pointer; font: 600 12px Inter; color: #818cf8;
        user-select: none; list-style: none; display: flex; align-items: center; gap: 6px;
      }
      #aicore-root details.ac-thinking summary::before { content: "▶"; font-size: 9px; }
      #aicore-root details.ac-thinking[open] summary::before { content: "▼"; }
      #aicore-root .thinking-body {
        padding: 10px 12px; font: 12px/1.6 'Geist Mono', ui-monospace, monospace;
        color: #a5b4fc; border-top: 1px solid #312e81; white-space: pre-wrap;
        max-height: 200px; overflow-y: auto;
      }

      /* Verdict */
      #aicore-root .ac-verdict {
        border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;
      }
      #aicore-root .ac-verdict.pass { background: #052e16; border: 1px solid #166534; }
      #aicore-root .ac-verdict.fail { background: #1c0505; border: 1px solid #991b1b; }
      #aicore-root .ac-verdict .v-head {
        display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
      }
      #aicore-root .v-badge {
        padding: 3px 10px; border-radius: 6px; font: 700 11px Inter; letter-spacing: .04em;
      }
      #aicore-root .v-badge.pass { background: #166534; color: #4ade80; }
      #aicore-root .v-badge.fail { background: #7f1d1d; color: #f87171; }
      #aicore-root .v-conf { font-size: 12px; color: #64748b; }
      #aicore-root .v-conf strong { color: #94a3b8; }
      #aicore-root .v-reason { font-size: 12px; color: #94a3b8; line-height: 1.6; }
      #aicore-root .conf-bar { height: 4px; background: #0f172a; border-radius: 2px; margin-top: 8px; overflow: hidden; }
      #aicore-root .conf-fill { height: 100%; border-radius: 2px; transition: width .6s; }

      /* Trace step */
      #aicore-root .trace-step {
        border: 1px solid #1e293b; border-radius: 8px; margin-bottom: 8px; overflow: hidden;
      }
      #aicore-root .trace-step-head {
        padding: 8px 12px; background: #1e293b;
        display: flex; align-items: center; gap: 8px; font-size: 12px;
      }
      #aicore-root .trace-tag { padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 600; background: #0f172a; color: #38bdf8; }
      #aicore-root .trace-tool { font: 600 12px 'Geist Mono', ui-monospace; color: #e2e8f0; flex: 1; }
      #aicore-root .trace-step-body { padding: 8px 12px; font: 11px/1.5 'Geist Mono', ui-monospace; color: #64748b; white-space: pre-wrap; max-height: 120px; overflow-y: auto; }
      #aicore-root .trace-step.err { border-color: #7f1d1d; }
      #aicore-root .trace-step.err .trace-step-head { background: #1c0505; }
      #aicore-root .trace-err-pill {
        padding: 1px 7px; border-radius: 4px; font: 700 9px Inter;
        background: #7f1d1d; color: #fecaca; text-transform: uppercase; letter-spacing: .06em;
      }

      /* Summary */
      #aicore-root .ac-summary {
        font: 600 15px Inter; color: #f1f5f9; margin-bottom: 14px; line-height: 1.5;
      }

      /* Empty state */
      #aicore-root .ac-empty {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        height: 100%; gap: 16px; color: #475569; text-align: center;
      }
      #aicore-root .ac-empty .icon { font-size: 40px; opacity: .4; }
      #aicore-root .ac-empty h3 { margin: 0; font-size: 15px; color: #64748b; }
      #aicore-root .ac-empty p { margin: 0; font-size: 12px; max-width: 280px; line-height: 1.6; }
      #aicore-root .ac-chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 4px; }
      #aicore-root .ac-chip {
        padding: 5px 12px; background: #1e293b; border: 1px solid #334155;
        border-radius: 999px; font-size: 12px; color: #94a3b8; cursor: pointer;
        transition: background .1s, color .1s;
      }
      #aicore-root .ac-chip:hover { background: #334155; color: #e2e8f0; }

      /* Input */
      #aicore-root .ac-form {
        display: flex; gap: 8px; padding: 14px 18px;
        border-top: 1px solid #1e293b; background: #0f172a; flex-shrink: 0;
      }
      #aicore-root .ac-form input {
        flex: 1; padding: 10px 14px; background: #1e293b; border: 1px solid #334155;
        border-radius: 8px; color: #e2e8f0; font: 13px Inter; outline: 0;
        transition: border-color .15s;
      }
      #aicore-root .ac-form input::placeholder { color: #475569; }
      #aicore-root .ac-form input:focus { border-color: #38bdf8; }
      #aicore-root .ac-form button {
        padding: 10px 18px; background: #1d4ed8; border: 0; border-radius: 8px;
        color: #fff; font: 600 13px Inter; cursor: pointer; transition: background .15s; white-space: nowrap;
      }
      #aicore-root .ac-form button:hover:not(:disabled) { background: #2563eb; }
      #aicore-root .ac-form button:disabled { background: #1e293b; color: #475569; cursor: not-allowed; }

      /* Gauge */
      #aicore-root .gauge-wrap { display: flex; flex-direction: column; align-items: center; }

      /* Model bar */
      #aicore-root .ac-modelbar {
        display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        padding: 8px 18px; background: #0a1120;
        border-bottom: 1px solid #1e293b; flex-shrink: 0;
      }
      #aicore-root .ac-modelbar label {
        font: 600 10px Inter; color: #475569;
        text-transform: uppercase; letter-spacing: .06em; white-space: nowrap;
      }
      #aicore-root .ac-modelbar select {
        padding: 4px 8px; background: #1e293b; border: 1px solid #334155;
        border-radius: 6px; color: #94a3b8; font: 12px Inter; cursor: pointer;
        outline: 0; transition: border-color .15s;
      }
      #aicore-root .ac-modelbar select:focus { border-color: #38bdf8; color: #e2e8f0; }
      #aicore-root .ac-modelbar .sep { color: #1e293b; user-select: none; }
      #aicore-root .ac-modelbar .turns-inp {
        width: 52px; padding: 4px 8px; background: #1e293b; border: 1px solid #334155;
        border-radius: 6px; color: #94a3b8; font: 12px Inter; outline: 0;
        text-align: center;
      }
      #aicore-root .ac-modelbar .active-badge {
        margin-left: auto; padding: 2px 8px; border-radius: 4px;
        font: 600 10px Inter; background: #052e16; color: #4ade80; border: 1px solid #166534;
      }

      /* Scrollbar */
      #aicore-root .ac-body::-webkit-scrollbar { width: 4px; }
      #aicore-root .ac-body::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }

      /* Collapsible card */
      #aicore-root .ac-card-header {
        display: flex; align-items: center; justify-content: space-between;
        cursor: pointer; user-select: none;
      }
      #aicore-root .ac-card-header:hover .ac-collapse-btn { opacity: 1; }
      #aicore-root .ac-collapse-btn {
        opacity: 0.4; background: none; border: none; color: #64748b;
        font-size: 11px; cursor: pointer; padding: 0 4px;
        transition: opacity .15s, color .15s;
      }
      #aicore-root .ac-collapse-btn:hover { color: #94a3b8; }
      #aicore-root .ac-card.collapsed { padding-bottom: 10px; }

      /* View toggle */
      #aicore-root .ac-view-toggle {
        margin-left: auto; display: flex; gap: 2px; padding: 4px 8px; align-items: center;
      }
      #aicore-root .ac-view-btn {
        padding: 3px 9px; border-radius: 4px; border: 1px solid #1e293b;
        background: transparent; color: #475569; font: 500 11px Inter;
        cursor: pointer; transition: background .1s, color .1s;
      }
      #aicore-root .ac-view-btn.active { background: #1e3a5f; color: #7dd3fc; border-color: #1e3a5f; }
      #aicore-root .ac-view-btn:hover:not(.active) { background: #1e293b; color: #94a3b8; }

      /* Raw JSON view */
      #aicore-root .ac-raw {
        font: 11px/1.5 'Geist Mono', ui-monospace, monospace;
        background: #020817; border: 1px solid #1e293b; border-radius: 8px;
        padding: 12px; color: #7dd3fc; white-space: pre-wrap; word-break: break-all;
        overflow-y: auto; max-height: calc(100vh - 280px);
      }

      /* Failure banner */
      #aicore-root .ac-failure-banner {
        background: #1c0505; border: 1px solid #991b1b; border-radius: 10px;
        padding: 14px 16px; margin-bottom: 12px;
      }
      #aicore-root .ac-failure-banner .fb-head {
        display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
      }
      #aicore-root .ac-failure-banner .fb-icon { font-size: 18px; }
      #aicore-root .ac-failure-banner .fb-title {
        font: 700 14px Inter; color: #f87171;
      }
      #aicore-root .ac-failure-banner .fb-reason {
        font-size: 12px; color: #fca5a5; line-height: 1.6; margin-bottom: 8px;
      }
      #aicore-root .ac-failure-banner .fb-hint {
        font-size: 11px; color: #7f1d1d; line-height: 1.5;
      }

      /* Markdown rendering for text cards & summary */
      #aicore-root .md-body { white-space: normal; }
      #aicore-root .md-p { margin: 0 0 8px; line-height: 1.65; color: #cbd5e1; }
      #aicore-root .md-p:last-child { margin-bottom: 0; }
      #aicore-root .md-ul {
        margin: 0 0 10px; padding: 0; list-style: none;
      }
      #aicore-root .md-ul:last-child { margin-bottom: 0; }
      #aicore-root .md-ul li {
        position: relative; padding: 4px 0 4px 16px;
        color: #cbd5e1; line-height: 1.65;
      }
      #aicore-root .md-ul li::before {
        content: "▸"; position: absolute; left: 2px; top: 4px;
        color: #38bdf8; font-size: 11px; font-weight: 700;
      }
      #aicore-root .md-b { color: #f1f5f9; font-weight: 700; }
      #aicore-root .md-c {
        font: 11px/1.45 'Geist Mono', ui-monospace, monospace;
        background: #020817; border: 1px solid #1e293b; border-radius: 4px;
        padding: 1px 6px; color: #7dd3fc; word-break: break-all;
      }
      #aicore-root .md-section {
        display: grid; grid-template-columns: 140px 1fr;
        gap: 4px 14px; align-items: baseline;
        padding: 6px 0; line-height: 1.65;
      }
      #aicore-root .md-section + .md-section {
        border-top: 1px dashed #1e293b; padding-top: 8px; margin-top: 2px;
      }
      #aicore-root .md-section-label {
        color: #7dd3fc; font-weight: 700; font-size: 11px;
        text-transform: uppercase; letter-spacing: .05em;
        white-space: nowrap; align-self: start; padding-top: 2px;
      }
      #aicore-root .md-section-body { color: #e2e8f0; }
      #aicore-root .md-section-body .md-ul { margin-bottom: 0; }
      #aicore-root .md-h { color: #f1f5f9; font: 700 14px Inter; margin: 6px 0 6px; }
      #aicore-root .ac-summary.md-body { font-weight: 500; }
      #aicore-root .ac-summary .md-b { font-size: 15px; }

      /* Grouped controls — Executor / Verifier / Limits */
      #aicore-root .ac-controls {
        display: grid;
        grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(0, 0.55fr);
        gap: 8px;
        padding: 12px 18px;
        background: #0a1120;
        border-bottom: 1px solid #1e293b;
        flex-shrink: 0;
      }
      #aicore-root .ctrl-group {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 9px 11px 10px;
        display: flex; flex-direction: column; gap: 7px;
        min-width: 0;
        transition: border-color .15s;
      }
      #aicore-root .ctrl-group:hover { border-color: #334155; }
      #aicore-root .ctrl-header {
        display: flex; align-items: center; gap: 6px;
        font: 700 9px Inter; color: #7dd3fc;
        text-transform: uppercase; letter-spacing: .12em;
        padding-bottom: 6px;
        border-bottom: 1px solid #1e293b;
      }
      #aicore-root .ctrl-icon { font-size: 11px; line-height: 1; }
      #aicore-root .ctrl-row {
        display: grid;
        grid-template-columns: 56px minmax(0, 1fr);
        gap: 8px; align-items: center;
        min-width: 0;
      }
      #aicore-root .ctrl-row > label {
        font: 500 10px Inter; color: #64748b;
        text-transform: none; letter-spacing: 0; white-space: nowrap;
      }
      #aicore-root .ctrl-sel, #aicore-root .ctrl-num {
        width: 100%; min-width: 0;
        padding: 5px 9px;
        background: #1e293b; border: 1px solid #334155;
        border-radius: 6px; color: #e2e8f0;
        font: 12px Inter; outline: 0; cursor: pointer;
        transition: border-color .12s, background .12s;
        text-overflow: ellipsis;
        appearance: none; -webkit-appearance: none;
      }
      #aicore-root .ctrl-sel {
        background-image:
          linear-gradient(45deg, transparent 50%, #64748b 50%),
          linear-gradient(135deg, #64748b 50%, transparent 50%);
        background-position: calc(100% - 13px) 50%, calc(100% - 8px) 50%;
        background-size: 5px 5px, 5px 5px;
        background-repeat: no-repeat;
        padding-right: 22px;
      }
      #aicore-root .ctrl-sel:hover, #aicore-root .ctrl-num:hover { background-color: #263348; }
      #aicore-root .ctrl-sel:focus, #aicore-root .ctrl-num:focus {
        border-color: #38bdf8; background-color: #263348;
      }
      #aicore-root .ctrl-num { text-align: center; cursor: text; padding-right: 9px; }
      #aicore-root .ctrl-foot {
        font: 500 10px Inter; color: #475569;
        padding-top: 4px; border-top: 1px dashed #1e293b;
        text-align: center;
      }
      @media (max-width: 600px) {
        #aicore-root .ac-controls { grid-template-columns: 1fr; }
      }

      /* JSON auto-prefab fallback */
      #aicore-root .ac-json-fallback {
        font: 11px/1.5 'Geist Mono', ui-monospace, monospace;
        background: #020817; border: 1px solid #1e293b; border-radius: 6px;
        padding: 10px 12px; color: #7dd3fc; white-space: pre-wrap;
        word-break: break-all; margin: 8px 0; overflow-x: auto;
        max-height: 240px; overflow-y: auto;
      }
    `;
    document.head.appendChild(s);
  }

  // ── helpers ───────────────────────────────────────────────────────────────
  function cpuColor(pct) {
    if (pct >= 85) return "#f87171";
    if (pct >= 65) return "#fbbf24";
    return "#4ade80";
  }

  // Parse structured [PHASE:X] / [REACT:Tn:X] tags from agent.py log lines.
  // Returns { tag, phase, turn, rest, cls, icon }
  function parseLogTag(line) {
    if (!line) return { cls: "info", icon: "·", rest: line };
    const m = line.match(/^\[([A-Z]+):([A-Z0-9]+)(?::([A-Z]+))?\]\s*(.*)/s);
    if (!m) {
      // legacy / plain lines
      if (line.startsWith("❌") || line.includes("TOOL_ERROR")) return { cls: "error", icon: "✗", rest: line };
      if (line.startsWith("⚠️") || line.includes("WARNING")) return { cls: "warn", icon: "⚠", rest: line };
      if (line.startsWith(">")) return { cls: "prompt", icon: "»", rest: line };
      return { cls: "info", icon: "·", rest: line };
    }
    const [, ns, second, third, rest] = m;
    // ns=PHASE second=INIT/MCP/GATEWAY/VERIFY/VERDICT  third=undefined
    // ns=REACT  second=T1    third=REQUEST/RESPONSE/…
    if (ns === "PHASE") {
      const phase = second;
      const icons = { INIT: "⚙", GATEWAY: "🔗", MCP: "🔌", VERIFY: "🔎", VERDICT: "⚖" };
      const colors = { INIT: "phase-init", GATEWAY: "phase-gw", MCP: "phase-mcp", VERIFY: "phase-verify", VERDICT: "phase-verdict" };
      return { tag: `PHASE:${phase}`, cls: colors[phase] || "phase-init", icon: icons[phase] || "▶", rest, phase };
    }
    if (ns === "REACT") {
      const turn = second;   // "T1", "T2", …
      const step = third;    // "REQUEST", "RESPONSE", "COT", "THINKING", "DISPATCH", "RESULT", "OBSERVE", "FINAL", "EMPTY", "COOLDOWN", "ERROR", "TEXT"
      const stepMeta = {
        REQUEST:  { cls: "react-req",      icon: "→" },
        RESPONSE: { cls: "react-resp",     icon: "←" },
        COT:      { cls: "react-cot",      icon: "💭" },
        THINKING: { cls: "react-thinking", icon: "🧠" },
        DISPATCH: { cls: "react-dispatch", icon: "⚡" },
        RESULT:   { cls: "react-result",   icon: "✓" },
        OBSERVE:  { cls: "react-observe",  icon: "👁" },
        FINAL:    { cls: "react-final",    icon: "★" },
        EMPTY:    { cls: "react-empty",    icon: "·" },
        COOLDOWN: { cls: "warn",           icon: "⏳" },
        ERROR:    { cls: "error",          icon: "✗" },
        TEXT:     { cls: "react-text",     icon: "▸" },
      };
      const meta = stepMeta[step] || { cls: "info", icon: "·" };
      return { tag: `${turn}:${step}`, cls: meta.cls, icon: meta.icon, rest, turn, step };
    }
    return { cls: "info", icon: "·", rest: line };
  }

  function logClass(line) {
    return parseLogTag(line).cls;
  }

  // Normalize value + unit so we never show "2359508992 MB" (clearly bytes).
  // Returns [displayValue, displayUnit]. Handles byte-family auto-rescaling
  // and falls back to thousand-separators for very large plain numbers.
  function formatMetric(rawValue, rawUnit) {
    const unit = (rawUnit || "").trim();
    const v = Number(rawValue);
    if (!isFinite(v)) return [String(rawValue ?? "—"), unit];

    const BYTE_UNITS = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 };
    const u = unit.toUpperCase();

    // Byte-family with implausible magnitude → assume raw bytes, rescale.
    if (u in BYTE_UNITS) {
      let bytes = v * BYTE_UNITS[u];
      // Heuristic: claimed MB but > 1e6 → was bytes;  claimed GB but > 1e4 → was MB
      if (u === "MB" && v > 1e6) bytes = v;
      else if (u === "GB" && v > 1e4) bytes = v * BYTE_UNITS.MB;
      else if (u === "KB" && v > 1e9) bytes = v;
      // Pick best display unit
      const order = ["B", "KB", "MB", "GB", "TB"];
      let i = 0, scaled = bytes;
      while (scaled >= 1024 && i < order.length - 1) { scaled /= 1024; i++; }
      const decimals = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
      return [scaled.toFixed(decimals), order[i]];
    }

    // Pure numeric, very large → SI-prefix or comma separators
    if (Math.abs(v) >= 1000) {
      return [v.toLocaleString(undefined, { maximumFractionDigits: 2 }), unit];
    }
    // Float with many decimals → trim
    if (!Number.isInteger(v)) return [v.toFixed(2), unit];
    return [String(v), unit];
  }

  // ── inline + block markdown renderer ──────────────────────────────────────
  // Handles **bold**, `code`, bullet lines (- / *), and `**Label:** rest`
  // section headers used by the agent prompt. Keeps output compact and aligned.
  function renderInline(text, keyPrefix) {
    const out = [];
    const re = /(\*\*[^*\n]+?\*\*|`[^`\n]+?`)/g;
    let last = 0, m, k = 0;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) out.push(text.slice(last, m.index));
      const tok = m[0];
      if (tok.startsWith("**")) {
        out.push(h("strong", { key: `${keyPrefix}-b${k++}`, className: "md-b" }, tok.slice(2, -2)));
      } else {
        out.push(h("code", { key: `${keyPrefix}-c${k++}`, className: "md-c" }, tok.slice(1, -1)));
      }
      last = m.index + tok.length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out.length ? out : [text];
  }

  // Strip any <think>...</think> blocks that leaked through the backend.
  // These come from Qwen3/DeepSeek thinking mode emitted inline in content.
  const THINK_RE = /^<\/?think>\s*|<think>[\s\S]*?<\/think>/gi;

  function stripThinkTags(text) {
    if (!text || !text.includes("<think") && !text.includes("</think>")) return text;
    return text.replace(THINK_RE, "").trim();
  }

  function renderMarkdown(text) {
    if (text == null) return null;
    const src = stripThinkTags(String(text));
    if (!src.trim()) return null;
    const lines = src.split("\n");
    const blocks = [];
    let listBuf = null;
    let key = 0;
    const flushList = () => {
      if (listBuf && listBuf.length) {
        blocks.push(h("ul", { key: `ul${key++}`, className: "md-ul" }, listBuf));
      }
      listBuf = null;
    };
    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i];
      if (!raw.trim()) { flushList(); continue; }
      const bm = raw.match(/^\s*[-*]\s+(.*)$/);
      if (bm) {
        listBuf = listBuf || [];
        listBuf.push(h("li", { key: `li${key++}` }, renderInline(bm[1], `li${key}`)));
        continue;
      }
      flushList();
      const hm = raw.match(/^\s*(#{1,6})\s+(.*)$/);
      if (hm) {
        blocks.push(h("div", { key: `h${key++}`, className: "md-h" }, renderInline(hm[2], `h${key}`)));
        continue;
      }
      const sm = raw.match(/^\s*\*\*([^*\n]+?)\*\*\s*:\s*(.*)$/);
      if (sm) {
        const label = sm[1].trim();
        const rest = sm[2].trim();
        blocks.push(h("div", { key: `s${key++}`, className: "md-section" },
          h("div", { className: "md-section-label" }, label),
          h("div", { className: "md-section-body" }, rest ? renderInline(rest, `s${key}`) : null)
        ));
        continue;
      }
      blocks.push(h("p", { key: `p${key++}`, className: "md-p" }, renderInline(raw, `p${key}`)));
    }
    flushList();
    return blocks;
  }

  // ── JSON shape detection ──────────────────────────────────────────────────
  // The agent sometimes dumps tool results into the text body as JSON. Detect
  // common system-monitor shapes and reroute them to the existing prefabs so
  // users see proper UI, not a wall of braces.
  function normalizeProc(p) {
    if (!p || typeof p !== "object") return p;
    let rssMb = p.rss_mb;
    if (rssMb == null && p.rss != null) {
      const n = Number(p.rss);
      if (isFinite(n)) rssMb = n > 1e7 ? n / 1024 / 1024 : n;
    }
    if (rssMb == null && p.memory_mb != null) rssMb = Number(p.memory_mb);
    return {
      name: p.name || p.cmd || p.command || p.process || "—",
      pid: p.pid ?? p.PID ?? null,
      cpu: Number(p.cpu ?? p.cpu_pct ?? p.cpu_percent ?? p.CPU ?? 0),
      rss_mb: rssMb,
    };
  }
  function formatScalar(v) {
    if (v == null) return "—";
    if (typeof v === "number" && isFinite(v)) {
      return Number.isInteger(v)
        ? v.toLocaleString()
        : v.toLocaleString(undefined, { maximumFractionDigits: 3 });
    }
    if (typeof v === "boolean") return v ? "yes" : "no";
    return String(v);
  }
  function classifyJsonShape(obj) {
    if (obj == null || typeof obj !== "object") return null;

    if (Array.isArray(obj)) {
      if (!obj.length) return null;
      const first = obj[0];
      if (!first || typeof first !== "object") return null;
      const hasProc = "pid" in first || ("name" in first && ("cpu" in first || "rss_mb" in first || "rss" in first || "cpu_pct" in first));
      if (hasProc) {
        return { type: "process_list", title: "Processes", data: { processes: obj.map(normalizeProc) } };
      }
      // Array of gauge-style objects with RSS labels → process_list
      const RSS_LABEL_RE = /^(.+?)\s*\(RSS:\s*([\d.]+)\s*([KMGBT]i?B|bytes?)\)/i;
      if (obj.every(o => o && typeof o.label === "string" && RSS_LABEL_RE.test(o.label))) {
        const processes = obj.map(o => {
          const m = o.label.match(RSS_LABEL_RE);
          let rssMb = parseFloat(m[2]);
          const u = m[3].toUpperCase();
          if (u.startsWith("G")) rssMb *= 1024;
          else if (u.startsWith("T")) rssMb *= 1024 * 1024;
          else if (u.startsWith("K")) rssMb /= 1024;
          return { name: m[1].trim(), rss_mb: rssMb, cpu: Number(o.value) <= 100 ? Number(o.value) : 0 };
        });
        return { type: "process_list", title: "Top Processes", data: { processes } };
      }
      const cols = [...new Set(obj.flatMap(o => o && typeof o === "object" ? Object.keys(o) : []))];
      if (cols.length && cols.length <= 8) {
        const rows = obj.map(o => cols.map(c => formatScalar(o?.[c])));
        return { type: "table", title: "Data", data: { columns: cols, rows } };
      }
      return null;
    }

    if (Array.isArray(obj.processes)) {
      return { type: "process_list", title: obj.title || "Top processes",
        data: { processes: obj.processes.map(normalizeProc) } };
    }
    if (Array.isArray(obj.top_processes)) {
      return { type: "process_list", title: "Top processes",
        data: { processes: obj.top_processes.map(normalizeProc) } };
    }
    if (Array.isArray(obj.events)) {
      return { type: "timeline", title: obj.title || "Events", data: obj };
    }
    if (Array.isArray(obj.values)) {
      return { type: "sparkline", title: obj.title || obj.metric || "Trend", data: obj };
    }
    if (Array.isArray(obj.rows) && Array.isArray(obj.columns)) {
      return { type: "table", title: obj.title || "Data", data: obj };
    }
    if (Array.isArray(obj.steps) && obj.steps.length && typeof obj.steps[0] === "string") {
      return { type: "kb_doc", title: obj.title || "Runbook", data: obj };
    }
    if (obj.level && (obj.title || obj.message)) {
      return { type: "alert", title: obj.title || "Alert", data: obj };
    }
    // Tool-error envelope from MCP _get/_post: {error, detail, hint, body?}
    if (typeof obj.error === "string" && ("detail" in obj || "hint" in obj || "body" in obj)) {
      const lvl = /timed?\s*out|request_failed|HTTP 5/i.test(obj.error + " " + (obj.detail || ""))
        ? "crit" : "warn";
      return { type: "alert", title: `Tool error · ${obj.error}`,
        data: {
          level: lvl,
          title: `Tool error · ${obj.error}`,
          message: [obj.detail, obj.hint, obj.body].filter(Boolean).join(" — "),
        } };
    }
    if (typeof obj.code === "string") {
      return { type: "code_block", title: obj.title || "Snippet", data: obj };
    }
    if ("value" in obj && (typeof obj.value === "number" || !isNaN(Number(obj.value)))) {
      return { type: "metric_tile", title: obj.metric || obj.title || obj.name || "Metric", data: obj };
    }

    const keys = Object.keys(obj);
    if (!keys.length) return null;
    const allScalar = keys.every(k => obj[k] == null || typeof obj[k] !== "object");
    if (allScalar) {
      return { type: "table", title: obj.title || "Values",
        data: { columns: ["field", "value"], rows: keys.map(k => [k, formatScalar(obj[k])]) } };
    }
    // Flatten one level: { mem: {total, used}, cpu: {pct} }
    const flat = [];
    for (const [k, v] of Object.entries(obj)) {
      if (v && typeof v === "object" && !Array.isArray(v)) {
        for (const [k2, v2] of Object.entries(v)) {
          if (v2 == null || typeof v2 !== "object") flat.push([`${k}.${k2}`, formatScalar(v2)]);
        }
      } else if (v == null || typeof v !== "object") {
        flat.push([k, formatScalar(v)]);
      }
    }
    if (flat.length) {
      return { type: "table", title: "Metrics", data: { columns: ["field", "value"], rows: flat } };
    }
    return null;
  }

  // Pull JSON blocks out of free-text body: fenced ```json``` + whole-body JSON.
  function extractJsonBlocks(text) {
    const out = [];
    const fenceRe = /```(?:json|jsonc?)?\s*\n?([\s\S]*?)```/gi;
    let last = 0, m;
    while ((m = fenceRe.exec(text)) !== null) {
      if (m.index > last) out.push({ kind: "text", text: text.slice(last, m.index) });
      const raw = m[1].trim();
      try { out.push({ kind: "json", obj: JSON.parse(raw), raw }); }
      catch { out.push({ kind: "text", text: m[0] }); }
      last = m.index + m[0].length;
    }
    const tail = text.slice(last);
    const tt = tail.trim();
    if (!out.length && ((tt.startsWith("{") && tt.endsWith("}")) || (tt.startsWith("[") && tt.endsWith("]")))) {
      try { return [{ kind: "json", obj: JSON.parse(tt), raw: tt }]; } catch {}
    }
    if (tail) out.push({ kind: "text", text: tail });
    return out;
  }

  function JsonAutoCard({ obj, raw }) {
    const classified = classifyJsonShape(obj);
    if (classified) {
      const Comp = PREFABS[classified.type];
      if (Comp) return h(Comp, { title: classified.title, data: classified.data });
    }
    return h("pre", { className: "ac-json-fallback" }, raw || JSON.stringify(obj, null, 2));
  }

  // ── prefab cards ──────────────────────────────────────────────────────────
  function MetricTile({ title, data }) {
    const pct = Number(data.value) || 0;
    const color = cpuColor(pct);
    const delta = data.delta_pct;
    const thresh = data.threshold;
    const fillPct = thresh ? Math.min(100, (pct / thresh) * 100) : pct;
    const [displayVal, displayUnit] = formatMetric(data.value, data.unit);
    const displayTitle = title || data.metric || data.name || "Metric";
    return h("div", { className: "ac-card" },
      h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), displayTitle),
      h("div", { className: "metric-val" },
        displayVal,
        displayUnit && h("span", { className: "unit" }, displayUnit)
      ),
      data.label && h("div", { className: "metric-meta" }, data.label),
      delta != null && h("div", { className: "metric-delta " + (delta >= 0 ? "up" : "down") },
        delta >= 0 ? "▲" : "▼", " ", Math.abs(delta).toFixed(1), "% vs baseline"
      ),
      thresh && h("div", null,
        h("div", { className: "threshold-bar" },
          h("div", { className: "threshold-fill", style: { width: fillPct + "%", background: color } })
        ),
        h("div", { style: { fontSize: 11, color: "#475569", marginTop: 3 } }, `threshold: ${thresh}${data.unit || ""}`)
      )
    );
  }

  function SparkCard({ title, data }) {
    const values = (Array.isArray(data.values) ? data.values : []).map(Number).filter(v => isFinite(v));
    const color = data.color || "#38bdf8";
    const unit = data.unit || "";

    if (!values.length) return h("div", { className: "ac-card" },
      h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), title),
      h("div", { style: { color: "#475569", fontSize: 12, padding: "8px 0" } }, "no data")
    );

    const min = Math.min(...values), max = Math.max(...values);
    const cur = values.at(-1);
    const stats = `min ${min.toFixed(1)} · max ${max.toFixed(1)} · now ${cur.toFixed(1)} ${unit}`.trim();

    // Single value: show as a metric_tile-style readout
    if (values.length === 1) {
      return h("div", { className: "ac-card" },
        h("div", { className: "ac-card-label", style: { justifyContent: "space-between" } },
          h("span", { style: { display: "flex", alignItems: "center", gap: 6 } },
            h("div", { className: "dot", style: { background: color } }), title),
          h("span", { style: { color: "#64748b", fontSize: 10 } }, "single sample")
        ),
        h("div", { className: "metric-val", style: { fontSize: 24 } },
          cur.toFixed(1), unit && h("span", { className: "unit" }, unit))
      );
    }

    const W = 600, H = 60, pad = 4;
    const range = max - min;
    const flat = range < 1e-9;
    const xs = values.map((_, i) => pad + i * (W - pad * 2) / (values.length - 1));
    // For flat data, center the line vertically — looks intentional, not broken
    const ys = flat
      ? values.map(() => H / 2)
      : values.map(v => H - pad - ((v - min) / range) * (H - pad * 2));
    const pts = xs.map((x, i) => (i ? "L" : "M") + x.toFixed(1) + "," + ys[i].toFixed(1)).join(" ");
    const area = pts + ` L${xs.at(-1).toFixed(1)},${H - pad} L${pad},${H - pad} Z`;
    return h("div", { className: "ac-card" },
      h("div", { className: "ac-card-label", style: { justifyContent: "space-between" } },
        h("span", { style: { display: "flex", alignItems: "center", gap: 6 } },
          h("div", { className: "dot", style: { background: color } }), title),
        h("span", { style: { color: "#94a3b8", fontWeight: 400, fontSize: 11 } }, stats)
      ),
      h("svg", { className: "spark", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" },
        h("defs", null,
          h("linearGradient", { id: "sparkGrad", x1: 0, y1: 0, x2: 0, y2: 1 },
            h("stop", { offset: "0%", stopColor: color, stopOpacity: .3 }),
            h("stop", { offset: "100%", stopColor: color, stopOpacity: 0 })
          )
        ),
        !flat && h("path", { className: "spark-area", d: area }),
        h("path", { className: "spark-line", d: pts, stroke: color }),
        flat && h("text", {
          x: W - pad, y: H / 2 - 4, textAnchor: "end", fontSize: 8, fill: "#475569",
        }, `flat @ ${cur.toFixed(1)}${unit}`)
      )
    );
  }

  function TableCard({ title, data }) {
    const cols = data.columns || [], rows = data.rows || [];
    return h("div", { className: "ac-card" },
      h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), title),
      h("table", { className: "ac-table" },
        h("thead", null, h("tr", null, cols.map((c, i) => h("th", { key: i }, c)))),
        h("tbody", null, rows.map((r, ri) =>
          h("tr", { key: ri }, r.map((cell, ci) => h("td", { key: ci }, String(cell ?? "—"))))
        ))
      )
    );
  }

  function ProcessList({ title, data }) {
    const procs = data.processes || [];
    const displayTitle = title || "Processes";
    function fmtRss(p) {
      if (p.rss_mb == null) return "—";
      const mb = p.rss_mb;
      if (mb >= 1024) return (mb / 1024).toFixed(1) + " GB";
      return mb.toFixed(0) + " MB";
    }
    function rssFlagClass(p) {
      if (p.rss_mb == null) return null;
      const gb = p.rss_mb / 1024;
      if (gb >= 8) return "high";
      if (gb >= 4) return "warn";
      return null;
    }
    return h("div", { className: "ac-card" },
      h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), displayTitle),
      procs.map((p, i) => {
        const cpu = p.cpu ?? 0;
        const cpuColor_ = cpuColor(Math.min(cpu, 100));
        const cpuFlag = cpu >= 80 ? "high" : cpu >= 50 ? "warn" : null;
        const memFlag = rssFlagClass(p);
        const flag = cpuFlag || memFlag;
        return h("div", { key: i, className: "proc-row" },
          h("div", { className: "proc-name" }, p.name || "—"),
          h("div", { className: "proc-pid" }, p.pid ? `PID ${p.pid}` : ""),
          h("div", { className: "cpu-bar" },
            h("div", { className: "cpu-bar-fill", style: { width: Math.min(100, cpu) + "%", background: cpuColor_ } })
          ),
          h("div", { className: "proc-cpu", style: { color: cpuColor_ } }, cpu.toFixed(1) + "%"),
          h("div", { className: "proc-rss" }, fmtRss(p)),
          flag && h("span", { className: "proc-flag " + flag }, flag)
        );
      })
    );
  }

  function AlertCard({ title, data }) {
    const titleStr = data.title || title || "";
    // Auto-derive level when missing or contradicts the title text.
    // (LLMs often emit level=ok for a "Memory Usage High" alert.)
    let level = (data.level || "").toLowerCase();
    const titleHints = titleStr.toLowerCase();
    const hasCritWord = /\b(crit|critical|fail|down|leak|oom|panic)\b/.test(titleHints);
    const hasWarnWord = /\b(high|elevated|warn|warning|slow|degraded|saturated|hog)\b/.test(titleHints);
    if (!level || (level === "ok" && (hasCritWord || hasWarnWord))) {
      level = hasCritWord ? "crit" : hasWarnWord ? "warn" : "ok";
    }
    const icon = level === "crit" ? "🔴" : level === "warn" ? "⚠" : "✓";
    return h("div", { className: "ac-alert " + level },
      h("div", { className: "alert-title", style: { display: "flex", alignItems: "center", gap: 8 } },
        h("span", { style: { fontSize: 14 } }, icon),
        h("span", null, titleStr)
      ),
      data.message && h("div", { className: "alert-msg" }, data.message)
    );
  }

  function KbDoc({ title, data }) {
    return h("div", { className: "ac-card kb-doc" },
      h("div", { className: "kb-title" }, data.title || title),
      (data.steps || []).map((s, i) => h("div", { key: i, className: "kb-step" }, s))
    );
  }

  function TextCard({ title, data }) {
    const body = data.body || "";
    const segs = extractJsonBlocks(body);
    const hasJson = segs.some(s => s.kind === "json");
    if (hasJson) {
      return h("div", { className: "ac-card" },
        title && h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), title),
        h("div", { className: "md-body" },
          segs.map((s, i) => {
            if (s.kind === "json") return h(JsonAutoCard, { key: i, obj: s.obj, raw: s.raw });
            const r = renderMarkdown(s.text);
            if (!r || (Array.isArray(r) && !r.length)) return null;
            return h("div", { key: i, className: "md-seg" }, r);
          })
        )
      );
    }
    const rendered = renderMarkdown(body);
    return h("div", { className: "ac-card" },
      title && h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), title),
      h("div", { className: "text-body md-body" }, rendered || body)
    );
  }

  function GaugeCard({ title, data }) {
    const BYTE_UNITS = new Set(["B","KB","MB","GB","TB","KIB","MIB","GIB","TIB"]);
    const rawVal = Number(data.value) ?? 0;
    const unit = (data.unit || "").trim().toUpperCase();
    // Gauge only makes sense for true percentages (0-100, no byte unit, no
    // explicit is_percent=false). Anything else degrades to MetricTile so we
    // never clamp an RSS value of 193 GB to 100%.
    const isByteUnit = BYTE_UNITS.has(unit);
    const isPercent = !isByteUnit && rawVal >= 0 && rawVal <= 100 && unit !== "";
    const isPlainPct = !isByteUnit && rawVal >= 0 && rawVal <= 100 && (unit === "%" || data.is_percent === true);
    const useGauge = isPlainPct || (isPercent && !data.label?.match(/\bRSS\b/i));

    if (!useGauge) {
      // Degrade: render as MetricTile (handles formatMetric, threshold bar, etc.)
      const safeTitle = title || data.name || data.metric || "Metric";
      return h(MetricTile, { title: safeTitle, data });
    }

    const pct = Math.min(100, Math.max(0, rawVal));
    const color = cpuColor(pct);
    const r = 38, cx = 50, cy = 50;
    const toXY = a => [cx + r * Math.cos(a), cy - r * Math.sin(a)];
    const startA = Math.PI, endA = 0;
    const curA = startA - (pct / 100) * Math.PI;
    const [sx, sy] = toXY(startA);
    const [ex, ey] = toXY(curA);
    const [tx, ty] = toXY(endA);
    const track = `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 0 0 ${tx.toFixed(2)} ${ty.toFixed(2)}`;
    const fill  = pct < 0.5 ? "" : `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 0 0 ${ex.toFixed(2)} ${ey.toFixed(2)}`;
    const displayTitle = title || "Gauge";
    return h("div", { className: "ac-card gauge-wrap" },
      h("div", { className: "ac-card-label", style: { justifyContent: "center" } },
        h("div", { className: "dot" }), displayTitle),
      h("svg", { viewBox: "0 0 100 62", style: { width: "100%", maxWidth: 200 } },
        h("path", { d: track, fill: "none", stroke: "#1e293b", strokeWidth: 8, strokeLinecap: "round" }),
        fill && h("path", { d: fill, fill: "none", stroke: color, strokeWidth: 8, strokeLinecap: "round" }),
        h("text", { x: cx, y: cy + 4, textAnchor: "middle", fontSize: 18, fontWeight: 700, fill: color },
          pct.toFixed(0) + "%")
      ),
      data.label && h("div", { className: "metric-meta", style: { textAlign: "center", marginTop: 4, fontSize: 11 } },
        data.label)
    );
  }

  function CodeBlock({ title, data }) {
    const code = data.code || "";
    const language = data.language || "shell";
    const [copied, setCopied] = useState(false);
    const copyable = data.copyable !== false;
    const copy = useCallback(() => {
      navigator.clipboard?.writeText(code).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    }, [code]);
    return h("div", { className: "ac-card" },
      title && h("div", { className: "ac-card-label", style: { justifyContent: "space-between" } },
        h("span", { style: { display: "flex", alignItems: "center", gap: 6 } },
          h("div", { className: "dot" }), title,
          h("span", { style: { marginLeft: 8, fontSize: 9, color: "#475569", letterSpacing: 0, textTransform: "lowercase" } }, language)
        ),
        copyable && h("button", {
          onClick: copy,
          className: "ac-view-btn",
          style: { fontSize: 10, padding: "3px 8px", background: copied ? "#064e3b" : undefined, color: copied ? "#6ee7b7" : undefined },
        }, copied ? "✓ copied" : "copy")
      ),
      h("pre", {
        style: {
          font: "11px/1.5 'Geist Mono', ui-monospace, monospace",
          background: "#020817", border: "1px solid #1e293b", borderRadius: 6,
          padding: "10px 12px", color: "#7dd3fc", whiteSpace: "pre-wrap",
          wordBreak: "break-all", margin: 0, overflowX: "auto",
        },
      }, code)
    );
  }

  function Timeline({ title, data }) {
    const events = Array.isArray(data.events) ? data.events : [];
    const sevColor = s => s === "crit" ? "#f87171" : s === "warn" ? "#fbbf24" : "#4ade80";
    return h("div", { className: "ac-card" },
      h("div", { className: "ac-card-label" }, h("div", { className: "dot" }), title),
      h("div", { style: { position: "relative", paddingLeft: 18 } },
        h("div", {
          style: { position: "absolute", left: 6, top: 4, bottom: 4, width: 1, background: "#1e293b" },
        }),
        events.map((e, i) => {
          const sev = (e.severity || "ok").toLowerCase();
          return h("div", { key: i, style: { position: "relative", paddingLeft: 12, paddingBottom: 10 } },
            h("div", {
              style: {
                position: "absolute", left: -16, top: 4, width: 7, height: 7,
                borderRadius: "50%", background: sevColor(sev),
                boxShadow: "0 0 0 3px #020617",
              },
            }),
            h("div", { style: { fontSize: 10, color: "#64748b", marginBottom: 2 } }, String(e.ts || "")),
            h("div", { style: { fontSize: 12, color: "#cbd5e1", fontWeight: 500 } }, e.label || "(unnamed)"),
            e.detail && h("div", { style: { fontSize: 11, color: "#94a3b8", marginTop: 3 } }, e.detail)
          );
        })
      )
    );
  }

  const PREFABS = { metric_tile: MetricTile, sparkline: SparkCard, table: TableCard,
    process_list: ProcessList, alert: AlertCard, kb_doc: KbDoc, text: TextCard, gauge: GaugeCard,
    code_block: CodeBlock, timeline: Timeline };

  // ── PhaseStepper ──────────────────────────────────────────────────────────
  // Visualizes the agentic loop as a horizontal stepper:
  //   PLAN → TOOLS → VERIFY → COMPOSE → DONE
  // Each phase has: idle | active | done | error. Phases are inferred from the
  // current statusText / log events while running, then locked to "done" when
  // verdict + ui arrive.
  function PhaseStepper({ phase, running, hasResult, turnInfo }) {
    const phases = [
      { id: "plan",    label: "Plan",    icon: "🧠" },
      { id: "tools",   label: "Tools",   icon: "🛠" },
      { id: "verify",  label: "Verify",  icon: "✓" },
      { id: "compose", label: "Compose", icon: "▦" },
      { id: "done",    label: "Done",    icon: "●" },
    ];
    // Index of current phase
    const order = ["plan", "tools", "verify", "compose", "done"];
    let curIdx = order.indexOf(phase || "plan");
    if (hasResult) curIdx = order.length - 1;
    if (!running && !hasResult) curIdx = -1;  // idle / before first run

    return h("div", {
      style: {
        display: "flex", alignItems: "center", gap: 0, padding: "8px 12px",
        background: "#0f172a", borderBottom: "1px solid #1e293b",
      },
    },
      phases.map((p, i) => {
        const state = curIdx < 0 ? "idle" : i < curIdx ? "done" : i === curIdx ? "active" : "idle";
        const color = state === "done" ? "#4ade80" : state === "active" ? "#7dd3fc" : "#475569";
        const bg = state === "active" ? "#1e3a5f" : "transparent";
        return h(React.Fragment, { key: p.id },
          h("div", {
            style: {
              display: "flex", alignItems: "center", gap: 6, padding: "4px 8px",
              borderRadius: 6, background: bg, color,
              fontSize: 11, fontWeight: state === "active" ? 700 : 500,
              transition: "all .15s",
            },
          },
            h("span", {
              style: {
                fontSize: 12,
                animation: state === "active" && running ? "acpulse 1s ease-in-out infinite" : "none",
              },
            }, p.icon),
            h("span", null, p.label),
            state === "active" && p.id === "tools" && turnInfo &&
              h("span", { style: { fontSize: 10, color: "#64748b", marginLeft: 4 } }, turnInfo)
          ),
          i < phases.length - 1 && h("div", {
            style: {
              flex: 1, height: 1, minWidth: 8,
              background: i < curIdx ? "#4ade80" : "#1e293b",
              transition: "background .2s",
              opacity: 0.6,
            },
          })
        );
      })
    );
  }

  // ── Thinking block ────────────────────────────────────────────────────────
  function ThinkingBlock({ text }) {
    if (!text?.trim()) return null;
    return h("details", { className: "ac-thinking" },
      h("summary", null, "💭 Reasoning trace"),
      h("div", { className: "thinking-body" }, text)
    );
  }

  // ── FailureBanner ─────────────────────────────────────────────────────────
  // Splits verdict.reason into [prose, embedded JSON]. Routes JSON through
  // JsonAutoCard so payloads like `{"error":"request_failed","hint":...}` or
  // wrapper responses like `{"assistant":{"response":{"text":...}}}` render as
  // structured UI instead of a wall of braces.
  function splitReasonJson(reason) {
    if (!reason) return { prose: "", json: null, raw: null };
    const s = String(reason);
    // Find first balanced { ... } or [ ... ]
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (c !== "{" && c !== "[") continue;
      const open = c, close = c === "{" ? "}" : "]";
      let depth = 0, inStr = false, esc = false, j = i;
      for (; j < s.length; j++) {
        const ch = s[j];
        if (esc) { esc = false; continue; }
        if (ch === "\\") { esc = true; continue; }
        if (ch === '"') { inStr = !inStr; continue; }
        if (inStr) continue;
        if (ch === open) depth++;
        else if (ch === close) { depth--; if (depth === 0) { j++; break; } }
      }
      if (depth !== 0) continue;
      const candidate = s.slice(i, j);
      try {
        const obj = JSON.parse(candidate);
        const prose = (s.slice(0, i) + s.slice(j)).replace(/\s*Raw:\s*$/i, "").trim();
        return { prose, json: obj, raw: candidate };
      } catch { /* keep scanning */ }
    }
    return { prose: s.trim(), json: null, raw: null };
  }

  function unwrapAssistantText(obj) {
    // Common verifier-output wrapper: {"assistant":{"response":{"text":"..."}}}
    const t = obj?.assistant?.response?.text
            ?? obj?.response?.text
            ?? obj?.text;
    return typeof t === "string" ? t : null;
  }

  function FailureBanner({ verdict }) {
    if (!verdict || verdict.passed) return null;
    const conf = Math.round((verdict.confidence || 0) * 100);
    const { prose, json, raw } = splitReasonJson(verdict.reason);
    const unwrapped = json ? unwrapAssistantText(json) : null;

    return h("div", { className: "ac-failure-banner" },
      h("div", { className: "fb-head" },
        h("span", { className: "fb-icon" }, "⚠"),
        h("div", null,
          h("div", { className: "fb-title" }, "Diagnosis Inconclusive"),
          h("div", { style: { fontSize: 11, color: "#7f1d1d", marginTop: 2 } },
            `Confidence: ${conf}% · Verifier could not confirm the answer`)
        )
      ),
      prose && h("div", { className: "fb-reason" }, prose),
      unwrapped && h("div", {
        className: "fb-reason",
        style: { background: "#0f0303", border: "1px solid #7f1d1d", borderRadius: 6, padding: "8px 10px", marginTop: 6, color: "#fecaca" }
      },
        h("div", { style: { font: "600 9px Inter", color: "#f87171", letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 4 } },
          "Verifier said"),
        unwrapped
      ),
      json && !unwrapped && h("div", { style: { marginTop: 6 } },
        h(JsonAutoCard, { obj: json, raw })
      ),
      h("div", { className: "fb-hint" },
        "Agent ran but verifier flagged issues. Open the Trace and Log tabs for raw evidence."
      )
    );
  }

  // ── CollapsibleCard ───────────────────────────────────────────────────────
  // When collapsed: shows a compact card-shaped header bar (label + ▶ show).
  // When expanded: renders inner Comp (which provides its own label/shell) with
  // an absolutely-positioned ▼ hide button in the top-right corner.
  // Avoids double-rendering the label.
  function CollapsibleCard({ id, isCollapsed, onToggle, children, label, type }) {
    if (isCollapsed) {
      return h("div", {
        className: "ac-card",
        style: { padding: "10px 14px", marginBottom: 10, cursor: "pointer" },
        onClick: () => onToggle(id),
        title: "Click to expand",
      },
        h("div", {
          style: { display: "flex", justifyContent: "space-between", alignItems: "center" },
        },
          h("div", { className: "ac-card-label", style: { margin: 0 } },
            h("div", { className: "dot" }),
            label,
            h("span", { style: { marginLeft: 8, fontSize: 10, color: "#475569", textTransform: "lowercase", letterSpacing: 0 } },
              `· ${type}`)
          ),
          h("span", { style: { fontSize: 10, color: "#64748b" } }, "▶ show")
        )
      );
    }
    return h("div", { style: { position: "relative" } },
      h("button", {
        className: "ac-collapse-btn",
        onClick: () => onToggle(id),
        title: "Collapse",
        style: { position: "absolute", top: 8, right: 10, zIndex: 1, fontSize: 10, opacity: 0.6 },
      }, "▼ hide"),
      children
    );
  }

  // ── coalesceCards ─────────────────────────────────────────────────────────
  // Merges consecutive gauge / metric_tile cards that each represent one process
  // (label matches "ProcName (RSS: X UNIT)" or same title repeated) into a
  // single process_list card. Fixes the "3 × MEMORY USAGE 100%" pattern the
  // LLM emits when it creates one gauge per process instead of a list.
  const RSS_RE = /^(.+?)\s*\(RSS:\s*([\d.]+)\s*([KMGBT]i?B|bytes?)\)/i;
  function labelToProc(c) {
    const label = c.data?.label || "";
    const m = label.match(RSS_RE);
    if (!m) return null;
    let rssMb = parseFloat(m[2]);
    const u = m[3].toUpperCase();
    if (u.startsWith("G")) rssMb *= 1024;
    else if (u.startsWith("T")) rssMb *= 1024 * 1024;
    else if (u.startsWith("K")) rssMb /= 1024;
    const cpu = Number(c.data?.value) || 0;
    return {
      name: m[1].trim(),
      rss_mb: rssMb,
      cpu: cpu <= 100 ? cpu : 0,
      pid: c.data?.pid ?? null,
    };
  }

  function coalesceCards(cards) {
    if (!cards?.length) return cards;
    const RSS_TYPES = new Set(["gauge", "metric_tile"]);
    const out = [];
    let i = 0;
    while (i < cards.length) {
      const c = cards[i];
      if (RSS_TYPES.has(c.type) && labelToProc(c)) {
        // collect contiguous RSS-labelled cards (same or empty title group)
        const group = [c];
        let baseTitle = c.title || "";
        let j = i + 1;
        while (j < cards.length) {
          const nc = cards[j];
          if (RSS_TYPES.has(nc.type) && labelToProc(nc)) {
            if (!baseTitle) baseTitle = nc.title || "";
            group.push(nc); j++;
          } else break;
        }
        if (group.length >= 2) {
          out.push({
            type: "process_list",
            title: baseTitle || "Top Processes",
            data: { processes: group.map(labelToProc) },
          });
          i = j; continue;
        }
      }
      // Single repeated-title gauge with no RSS label — still try to normalise title
      if (c.type === "gauge" && !c.title) {
        out.push({ ...c, title: c.data?.name || c.data?.metric || "Metric" });
        i++; continue;
      }
      out.push(c); i++;
    }
    return out;
  }

  // ── GenerativeUI ──────────────────────────────────────────────────────────
  function GenerativeUI({ ui, trace, verdict, collapsed, onToggleCollapse }) {
    if (!ui?.cards) return null;
    const thinking = [...new Set((trace?.steps || []).map(s => s.thinking).filter(Boolean))]
      .concat(trace?.final_thinking ? [trace.final_thinking] : []).join("\n\n---\n\n");
    const cards = coalesceCards(ui.cards);
    return h(React.Fragment, null,
      h(FailureBanner, { verdict }),
      h(ThinkingBlock, { text: thinking }),
      ui.summary && h("div", { className: "ac-summary md-body" },
        renderMarkdown(stripThinkTags(ui.summary)) || stripThinkTags(ui.summary)
      ),
      cards.map((c, i) => {
        const cardId = `card-${i}`;
        const Comp = PREFABS[c.type] || TextCard;
        if (c.type === "alert") return h(Comp, { key: i, title: c.title, data: c.data || {} });
        return h(CollapsibleCard, {
          key: i, id: cardId, label: c.title || c.type, type: c.type,
          isCollapsed: !!collapsed[cardId],
          onToggle: onToggleCollapse,
        },
          h(Comp, { title: c.title, data: c.data || {} })
        );
      })
    );
  }

  // ── Raw JSON view ─────────────────────────────────────────────────────────
  function RawView({ data }) {
    const [copied, setCopied] = useState(false);
    const json = JSON.stringify(data, null, 2);
    const copy = useCallback(() => {
      navigator.clipboard?.writeText(json).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    }, [json]);
    return h("div", { style: { position: "relative" } },
      h("button", {
        className: "ac-view-btn",
        onClick: copy,
        style: {
          position: "absolute", top: 8, right: 8, zIndex: 1,
          fontSize: 10, padding: "3px 8px",
          background: copied ? "#064e3b" : undefined,
          color: copied ? "#6ee7b7" : undefined,
        },
      }, copied ? "✓ copied" : "copy"),
      h("pre", { className: "ac-raw" }, json)
    );
  }

  // ── Verdict panel ─────────────────────────────────────────────────────────
  function VerdictPanel({ verdict }) {
    if (!verdict) return null;
    const cls = verdict.passed ? "pass" : "fail";
    const conf = Math.round((verdict.confidence || 0) * 100);
    const confColor = conf >= 70 ? "#4ade80" : conf >= 40 ? "#fbbf24" : "#f87171";
    return h("div", { className: "ac-verdict " + cls },
      h("div", { className: "v-head" },
        h("span", { className: "v-badge " + cls }, verdict.passed ? "✓ VERIFIED" : "✗ UNVERIFIED"),
        h("span", { className: "v-conf" }, h("strong", null, conf + "%"), " confidence")
      ),
      h("div", { className: "v-reason" }, verdict.reason),
      h("div", { className: "conf-bar" },
        h("div", { className: "conf-fill", style: { width: conf + "%", background: confColor } })
      )
    );
  }

  // ── Trace panel ───────────────────────────────────────────────────────────
  // Parses each step's result as JSON when possible, flags tool errors with a
  // red pill, and renders structured shapes through JsonAutoCard. Falls back
  // to truncated text only when the result is genuinely non-JSON.
  function parseStepResult(result) {
    if (result == null) return { kind: "empty" };
    if (typeof result === "object") return { kind: "json", obj: result };
    const s = String(result).trim();
    if ((s.startsWith("{") && s.endsWith("}")) || (s.startsWith("[") && s.endsWith("]"))) {
      try { return { kind: "json", obj: JSON.parse(s) }; } catch { /* fall through */ }
    }
    return { kind: "text", text: s };
  }

  function TracePanel({ trace }) {
    if (!trace?.steps?.length) return h("div", { style: { color: "#475569", fontSize: 13, padding: "20px 0" } }, "No tool calls recorded.");
    return h(React.Fragment, null,
      h("div", { style: { marginBottom: 10, fontSize: 12, color: "#64748b" } },
        `${trace.total_turns} turns · ${trace.steps.length} tool calls · provider: ${trace.provider}`
      ),
      trace.steps.map((s, i) => {
        const parsed = parseStepResult(s.result);
        const isError = parsed.kind === "json" && parsed.obj && (parsed.obj.error || parsed.obj.status >= 400);
        return h("div", { key: i, className: "trace-step" + (isError ? " err" : "") },
          h("div", { className: "trace-step-head" },
            h("span", { style: { color: "#475569", fontSize: 11 } }, `#${s.step}`),
            h("span", { className: "trace-tag" }, s.reasoning_tag),
            h("span", { className: "trace-tool" }, s.tool_name),
            isError && h("span", { className: "trace-err-pill" }, "error"),
            h("span", { style: { fontSize: 11, color: "#475569", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } },
              JSON.stringify(s.arguments))
          ),
          parsed.kind === "json"
            ? h("div", { style: { padding: "8px 10px" } },
                h(JsonAutoCard, { obj: parsed.obj, raw: JSON.stringify(parsed.obj, null, 2) }))
            : h("div", { className: "trace-step-body" },
                parsed.kind === "text"
                  ? parsed.text.slice(0, 600) + (parsed.text.length > 600 ? " …" : "")
                  : "(empty)")
        );
      })
    );
  }

  // ── Main ChatPanel ────────────────────────────────────────────────────────
  function ChatPanel() {
    const [open, setOpen] = useState(false);
    const [question, setQuestion] = useState("");
    const [logs, setLogs] = useState([]);
    const [verdict, setVerdict] = useState(null);
    const [ui, setUi] = useState(null);
    const [trace, setTrace] = useState(null);
    const [running, setRunning] = useState(false);
    const [statusText, setStatusText] = useState("");
    const [turnInfo, setTurnInfo] = useState("");
    const [tab, setTab] = useState("answer");
    const [executor, setExecutor] = useState("auto");
    const [verifier, setVerifier] = useState("ollama");
    const [execModel, setExecModel] = useState("");
    const [verModel, setVerModel] = useState("");
    const [maxTurns, setMaxTurns] = useState(8);
    const [configLoaded, setConfigLoaded] = useState(false);
    const [activeProvider, setActiveProvider] = useState(null);
    const [viewMode, setViewMode] = useState("cards");
    const [collapsed, setCollapsed] = useState({});
    const [phase, setPhase] = useState("plan");  // plan | tools | verify | compose | done
    const [routingPolicy, setRoutingPolicy] = useState("auto");  // auto | fast | quality | cheap | balanced
    const logRef = useRef(null);
    const inputRef = useRef(null);
    const stillRunning = useRef(false);

    useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs]);
    useEffect(() => { if (open && !running) inputRef.current?.focus(); }, [open]);

    // Fetch agent config from server on first open
    useEffect(() => {
      if (!configLoaded) {
        fetch("/api/config/agent")
          .then(r => r.ok ? r.json() : null)
          .then(cfg => {
            if (!cfg) return;
            setExecutor(cfg.executor_provider || "ollama");
            setVerifier(cfg.verifier_provider || "ollama");
            setExecModel(cfg.executor_model || "qwen3:1.7b");
            setVerModel(cfg.verifier_model || "qwen3:1.7b");
            setConfigLoaded(true);
          })
          .catch(() => {
            setExecModel("qwen3:1.7b");
            setVerModel("qwen3:1.7b");
            setConfigLoaded(true);
          });
      }
    }, [configLoaded]);

    const onToggleCollapse = useCallback((id) => {
      setCollapsed(prev => ({ ...prev, [id]: !prev[id] }));
    }, []);

    const ask = useCallback((q) => {
      q = (q || question).trim();
      if (!q || running) return;
      setLogs([`> ${q}`]);
      setVerdict(null); setUi(null); setTrace(null);
      setCollapsed({}); setViewMode("cards"); setPhase("plan");
      setRunning(true); setStatusText("Connecting…"); setTurnInfo("");
      setTab("log"); setActiveProvider(null); stillRunning.current = true;
      setQuestion("");

      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${location.host}/api/chat_v2/stream`);

      ws.onopen = () => {
        setStatusText("Sending…");
        ws.send(JSON.stringify({
          message: q,
          executor_provider: executor,
          verifier_provider: verifier,
          executor_model: executor === "ollama" ? execModel : undefined,
          verifier_model: verifier === "ollama" ? verModel : undefined,
          max_turns: maxTurns,
          routing_policy: routingPolicy,
        }));
      };

      ws.onmessage = ev => {
        try {
          const d = JSON.parse(ev.data);
          if (d.type === "log") {
            const line = d.text || "";
            setLogs(l => [...l, line]);
            // Parse structured tags for status/turn updates
            const tm = line.match(/^\[REACT:(T(\d+)):([A-Z]+)\]/);
            const pm = line.match(/^\[PHASE:([A-Z]+)\]/);
            if (tm) {
              const [, turnLabel, , step] = tm;
              if (step === "REQUEST") {
                setTurnInfo(turnLabel); setStatusText("LLM request…"); setPhase("plan");
              }
              else if (step === "RESPONSE") {
                const prov = line.match(/provider=([^\s|]+)/);
                if (prov) setActiveProvider(prov[1].split("/")[0]);
                setStatusText("Processing response…");
              }
              else if (step === "DISPATCH") { setStatusText("Running tools…"); setPhase("tools"); }
              else if (step === "COOLDOWN") setStatusText("Rate limit — retrying…");
              else if (step === "FINAL") { setStatusText("Verifying answer…"); setPhase("verify"); }
              else if (step === "ERROR") setStatusText("LLM error — failing over…");
            } else if (pm) {
              const ph = pm[1];
              if (ph === "MCP" && line.includes("ready")) { setStatusText("Tools ready — thinking…"); setPhase("plan"); }
              else if (ph === "VERIFY")  { setStatusText("Verifier reasoning…"); setPhase("verify"); }
              else if (ph === "VERDICT") { setStatusText("Building answer…");    setPhase("compose"); }
              else if (ph === "COMPOSE") { setStatusText("Composing UI cards…"); setPhase("compose"); }
              else if (ph === "ROUTING") setStatusText("Routing…");
            }
          } else if (d.type === "status") {
            setStatusText(d.text); setLogs(l => [...l, d.text]);
            if (d.text && d.text.toLowerCase().includes("compos")) setPhase("compose");
          } else if (d.type === "done") {
            setVerdict(d.verdict); setUi(d.ui); setTrace(d.trace);
            setRunning(false); setTurnInfo("");
            setPhase("done");
            setStatusText("Done");
            setTab("answer"); stillRunning.current = false;
          } else if (d.type === "error") {
            setLogs(l => [...l, `❌ ${d.message}`]);
            setRunning(false); setStatusText("Error"); stillRunning.current = false;
          }
        } catch (_) {}
      };

      ws.onclose = ev => {
        if (stillRunning.current)
          setLogs(l => [...l, `⚠️ Connection dropped (code ${ev.code}). Check server logs.`]);
        setRunning(false); setStatusText(""); stillRunning.current = false;
      };

      ws.onerror = () => {
        setLogs(l => [...l, "❌ WebSocket error — is server running on :9090?"]);
        setRunning(false); setStatusText("Connection failed"); stillRunning.current = false;
      };
    }, [question, running, executor, verifier, maxTurns]);

    const onSubmit = e => { e.preventDefault(); ask(); };
    const onChip = q => { setQuestion(q); ask(q); };

    if (!open) return h("button", { className: "ac-fab", onClick: () => setOpen(true) },
      h("div", { className: "pulse" }),
      "SystemHealth Agent"
    );

    const hasResult = ui || verdict || trace;
    const logCount = logs.length;
    const stepCount = trace?.steps?.length ?? 0;

    return h("div", { className: "ac-panel" },

      // Header
      h("div", { className: "ac-header" },
        h("div", { className: "title" },
          h("h2", null, "⚡ SystemHealth Agent", h("span", { style: { fontSize: 11, fontWeight: 400, color: "#64748b" } }, " ai_core")),
          h("p", null, `ReAct · RAG · CoT — executor: ${executor === "auto" ? "auto" : executor === "ollama" ? execModel : executor} · verifier: ${verifier === "auto" ? "auto" : verifier === "ollama" ? verModel : verifier} · gateway :8100`)
        ),
        h("button", { className: "ac-close", onClick: () => setOpen(false) }, "×")
      ),

      // Grouped controls — Executor / Verifier / Limits
      !running && h("div", { className: "ac-controls" },
        // Executor group
        h("div", { className: "ctrl-group" },
          h("div", { className: "ctrl-header" },
            h("span", { className: "ctrl-icon" }, "⚡"), "Executor"
          ),
          h("div", { className: "ctrl-row" },
            h("label", null, "Policy"),
            h("select", {
              className: "ctrl-sel",
              value: routingPolicy,
              onChange: e => setRoutingPolicy(e.target.value),
              title: "auto = gateway order · fast = Groq · quality = Anthropic · cheap = Ollama · balanced = Gemini",
            },
              h("option", { value: "auto" }, "Auto"),
              h("option", { value: "fast" }, "Fast (Groq)"),
              h("option", { value: "quality" }, "Quality (Anthropic)"),
              h("option", { value: "cheap" }, "Cheap (Ollama)"),
              h("option", { value: "balanced" }, "Balanced (Gemini)")
            )
          ),
          h("div", { className: "ctrl-row" },
            h("label", null, "Provider"),
            h("select", {
              className: "ctrl-sel",
              value: executor, onChange: e => setExecutor(e.target.value),
              title: "Override the routing policy with an explicit provider",
            },
              h("option", { value: "auto" }, "Auto (gateway order)"),
              h("option", { value: "ollama" }, "Ollama (local GPU)"),
              h("option", { value: "groq" }, "Groq — llama-3.3-70b"),
              h("option", { value: "gemini" }, "Gemini — 2.5-flash-lite"),
              h("option", { value: "nvidia" }, "NVIDIA — DeepSeek-V3"),
              h("option", { value: "anthropic" }, "Anthropic — Claude Sonnet"),
              h("option", { value: "openrouter" }, "OpenRouter"),
              h("option", { value: "github" }, "GitHub — GPT-4.1-mini")
            )
          ),
          executor === "ollama" && h("div", { className: "ctrl-row" },
            h("label", null, "Model"),
            h("select", { className: "ctrl-sel", value: execModel, onChange: e => setExecModel(e.target.value) },
              h("option", { value: "qwen3:1.7b" }, "qwen3:1.7b (fast)"),
              h("option", { value: "nemotron-mini:4b" }, "nemotron-mini:4b (smart)")
            )
          )
        ),
        // Verifier group
        h("div", { className: "ctrl-group" },
          h("div", { className: "ctrl-header" },
            h("span", { className: "ctrl-icon" }, "🔎"), "Verifier"
          ),
          h("div", { className: "ctrl-row" },
            h("label", null, "Provider"),
            h("select", { className: "ctrl-sel", value: verifier, onChange: e => setVerifier(e.target.value) },
              h("option", { value: "auto" }, "Auto (gateway order)"),
              h("option", { value: "ollama" }, "Ollama (local GPU)"),
              h("option", { value: "gemini" }, "Gemini — 2.5-flash-lite"),
              h("option", { value: "anthropic" }, "Anthropic — Claude Sonnet"),
              h("option", { value: "nvidia" }, "NVIDIA — DeepSeek-V3"),
              h("option", { value: "groq" }, "Groq — llama-3.3-70b"),
              h("option", { value: "openrouter" }, "OpenRouter")
            )
          ),
          verifier === "ollama" && h("div", { className: "ctrl-row" },
            h("label", null, "Model"),
            h("select", { className: "ctrl-sel", value: verModel, onChange: e => setVerModel(e.target.value) },
              h("option", { value: "qwen3:1.7b" }, "qwen3:1.7b (fast)"),
              h("option", { value: "nemotron-mini:4b" }, "nemotron-mini:4b (smart)")
            )
          )
        ),
        // Limits group
        h("div", { className: "ctrl-group" },
          h("div", { className: "ctrl-header" },
            h("span", { className: "ctrl-icon" }, "🔁"), "Limits"
          ),
          h("div", { className: "ctrl-row" },
            h("label", null, "Turns"),
            h("input", {
              className: "ctrl-num", type: "number", min: 1, max: 20,
              value: maxTurns,
              onChange: e => setMaxTurns(Number(e.target.value)),
            })
          ),
          h("div", { className: "ctrl-foot" }, `react loop · ≤ ${maxTurns}`)
        )
      ),

      // Active provider badge while running
      running && activeProvider && h("div", { className: "ac-modelbar" },
        h("label", null, "Using"),
        h("span", { className: "active-badge" },
          executor === "auto" ? `auto → ${activeProvider}` : activeProvider === "ollama" ? execModel : activeProvider
        ),
        h("span", { style: { fontSize: 11, color: "#475569" } },
          `→ verifier: ${verifier === "auto" ? "auto" : verifier === "ollama" ? verModel : verifier}`
        ),
        h("span", { className: "sep" }, "│"),
        h("span", { style: { fontSize: 11, color: "#475569" } }, `max ${maxTurns} turns`)
      ),

      // Phase stepper — visible while running OR when a result is loaded
      (running || hasResult) && h(PhaseStepper, { phase, running, hasResult, turnInfo }),

      // Status bar — spinner only while running; completion pill after done
      (running || statusText === "Done") && h("div", {
        className: "ac-status",
        style: !running ? { background: "#052e16", borderBottomColor: "#166534", color: "#4ade80" } : undefined,
      },
        running
          ? h("div", { className: "spinner" })
          : h("span", { style: { fontSize: 13 } }, "✓"),
        statusText,
        running && turnInfo && h("span", { className: "turn-badge" }, turnInfo)
      ),

      // Tabs (only show when there's something to tab)
      hasResult && h("div", { className: "ac-tabs" },
        h("button", { className: "ac-tab " + (tab === "answer" ? "active" : ""), onClick: () => setTab("answer") }, "Answer",
          ui?.cards && h("span", { className: "badge" }, ui.cards.length)
        ),
        h("button", { className: "ac-tab " + (tab === "trace" ? "active" : ""), onClick: () => setTab("trace") }, "Trace",
          stepCount > 0 && h("span", { className: "badge" }, stepCount)
        ),
        h("button", { className: "ac-tab " + (tab === "verdict" ? "active" : ""), onClick: () => setTab("verdict") }, "Verdict"),
        h("button", { className: "ac-tab " + (tab === "log" ? "active" : ""), onClick: () => setTab("log") }, "Log",
          logCount > 0 && h("span", { className: "badge" }, logCount)
        ),
        // View mode toggle — only on Answer tab
        tab === "answer" && h("div", { className: "ac-view-toggle" },
          ["cards", "raw"].map(m =>
            h("button", { key: m, className: "ac-view-btn " + (viewMode === m ? "active" : ""),
              onClick: () => setViewMode(m) }, m)
          )
        )
      ),

      // Body
      h("div", { className: "ac-body" },

        // Log tab (always visible while running, or when log tab selected)
        (tab === "log" || (running && !hasResult)) && h("div", { className: "ac-log", ref: logRef },
          logs.map((line, i) => {
            const { cls, icon, tag, rest } = parseLogTag(line || "");
            return h("div", { key: i, className: "log-line " + cls },
              h("span", { className: "log-icon" }, icon),
              tag && h("span", { className: "log-tag" }, tag),
              h("span", { className: "log-rest" }, rest || line || " ")
            );
          })
        ),

        // Answer tab
        tab === "answer" && hasResult && h(React.Fragment, null,
          viewMode === "raw"
            ? h(RawView, { data: { verdict, ui, trace } })
            : h(React.Fragment, null,
                // VerdictPanel hidden on failure — FailureBanner inside GenerativeUI replaces it
                verdict?.passed !== false && h(VerdictPanel, { verdict }),
                h(GenerativeUI, { ui, trace, verdict, collapsed, onToggleCollapse }),
                !ui && trace && h("div", { className: "ac-card" },
                  h("div", { className: "text-body" }, trace.final_answer || "No answer generated.")
                )
              )
        ),

        // Trace tab
        tab === "trace" && h(TracePanel, { trace }),

        // Verdict tab
        tab === "verdict" && h(VerdictPanel, { verdict }),

        // Empty state
        !running && !hasResult && tab !== "log" && h("div", { className: "ac-empty" },
          h("div", { className: "icon" }, "🔍"),
          h("h3", null, "Ask about your system"),
          h("p", null, "ReAct agent with live metrics, logs, and process data. Multi-turn reasoning with CoT tags."),
          h("div", { className: "ac-chips" },
            ["why is cpu high?", "top memory hogs", "recent errors in journald", "is there a memory leak?"]
              .map(q => h("div", { key: q, className: "ac-chip", onClick: () => onChip(q) }, q))
          )
        )
      ),

      // Input form
      h("form", { className: "ac-form", onSubmit },
        h("input", {
          ref: inputRef,
          value: question,
          onChange: e => setQuestion(e.target.value),
          placeholder: running ? "Agent thinking…" : "Ask anything about this host…",
          disabled: running,
        }),
        h("button", { type: "submit", disabled: running || !question.trim() },
          running ? "Working…" : "Ask"
        )
      )
    );
  }

  const node = document.createElement("div");
  node.id = "aicore-root";
  document.body.appendChild(node);
  ReactDOM.createRoot(node).render(h(ChatPanel));
})();
