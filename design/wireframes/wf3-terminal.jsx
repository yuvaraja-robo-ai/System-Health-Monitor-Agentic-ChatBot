/* global React, WireframeFrame, Sparkline, BarHisto, UsageBar, LogLine */

// Terminal / nmon-inspired — monospace columns, keystroke-driven feel
function W3_Terminal({ host = "jetson" }) {
  const isJetson = host === "jetson";
  return (
    <WireframeFrame
      host={host}
      title="Terminal — nmon-style"
      meta="Keyboard-first, column layout, feels like a TUI in the browser"
    >
      {/* command bar */}
      <div className="box" style={{ display: "flex", gap: 14, alignItems: "center", padding: "8px 12px", marginBottom: 12 }}>
        <span className="mono" style={{ color: "var(--teal)" }}>edge@orin-nano:~$</span>
        <span className="mono">systemhealth --watch --apps inference-svc,video-pipeline,api-gateway</span>
        <span style={{ flex: 1 }} />
        <span className="mono muted" style={{ fontSize: 11 }}>[q]uit [p]ause [/]search [a]pps [i]ncident [?]help</span>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {/* LEFT — CPU / MEM / DISK / NET columns */}
        <div className="col" style={{ gap: 10 }}>
          <div className="box pad-0">
            <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--rule)", display: "flex", justifyContent: "space-between" }}>
              <span className="mono" style={{ fontWeight: 600 }}>┌── CPU ──</span>
              <span className="mono muted" style={{ fontSize: 11 }}>6 cores · arm-cortex-a78ae</span>
            </div>
            <div style={{ padding: "8px 10px" }}>
              {["cpu0","cpu1","cpu2","cpu3","cpu4","cpu5"].map((c, i) => {
                const pct = [62, 48, 35, 71, 22, 18][i];
                const block = "█".repeat(Math.round(pct/5)) + "░".repeat(20 - Math.round(pct/5));
                return (
                  <div key={c} className="mono" style={{ fontSize: 11, display: "flex", gap: 10 }}>
                    <span style={{ color: "var(--ink-3)" }}>{c}</span>
                    <span style={{ color: pct > 70 ? "var(--amber)" : "var(--ink)" }}>{block}</span>
                    <span style={{ width: 36, textAlign: "right" }}>{pct}%</span>
                  </div>
                );
              })}
              <div className="mono muted" style={{ fontSize: 11, marginTop: 4 }}>load  1m 2.14  5m 1.82  15m 1.31</div>
            </div>
          </div>

          <div className="box pad-0">
            <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--rule)" }}>
              <span className="mono" style={{ fontWeight: 600 }}>┌── MEMORY ──</span>
            </div>
            <div style={{ padding: "8px 10px" }}>
              <div className="mono" style={{ fontSize: 11 }}>phys   <span className="amber" style={{ color: "var(--amber)" }}>████████████████░░░░</span>  5.8G / 8.0G  (72%)</div>
              <div className="mono" style={{ fontSize: 11 }}>swap   ██░░░░░░░░░░░░░░░░░░  0.2G / 4.0G  ( 5%)</div>
              <div className="mono" style={{ fontSize: 11 }}>cache  ██████████░░░░░░░░░░  1.2G</div>
              <div className="mono" style={{ fontSize: 11 }}>buff   █░░░░░░░░░░░░░░░░░░░  0.1G</div>
              <div style={{ height: 40, marginTop: 6 }}><Sparkline seed={5} trend="leak" height={40} className="amber" /></div>
              <div className="mono muted" style={{ fontSize: 10 }}>↗ RSS drift detected on inference-svc (+0.6M/min)</div>
            </div>
          </div>

          <div className="box pad-0">
            <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--rule)" }}>
              <span className="mono" style={{ fontWeight: 600 }}>┌── {isJetson ? "JETSON SoC" : "DISK + NET"} ──</span>
            </div>
            <div style={{ padding: "8px 10px" }} className="mono" >
              {isJetson ? (
                <>
                  <div style={{ fontSize: 11 }}>GPU   ██████████████░░░░░░  71%   2.1G vram</div>
                  <div style={{ fontSize: 11 }}>TEMP  cpu 58°C  gpu 64°C  soc 61°C  ao 47°C</div>
                  <div style={{ fontSize: 11 }}>POWER 11.4W  (mode: 15W max)</div>
                  <div style={{ fontSize: 11 }}>EMC   ███████░░░░░░░░░░░░░  38%  freq 2133MHz</div>
                  <div style={{ fontSize: 11 }}>FAN   rpm 3200  profile auto</div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 11 }}>sda1 /          ████████████░░░░░░░░  62%  187G/300G</div>
                  <div style={{ fontSize: 11 }}>nvme0 /data     ████████░░░░░░░░░░░░  44%  440G/1T</div>
                  <div style={{ fontSize: 11 }}>eth0  ↓ 24.1 MB/s   ↑ 3.4 MB/s</div>
                  <div style={{ fontSize: 11 }}>io_wait          2%  (healthy)</div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT — processes + services + log tail */}
        <div className="col" style={{ gap: 10 }}>
          <div className="box pad-0">
            <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--rule)", display: "flex", justifyContent: "space-between" }}>
              <span className="mono" style={{ fontWeight: 600 }}>┌── TOP PROCESSES (watched) ──</span>
              <span className="mono muted" style={{ fontSize: 11 }}>sort: mem ▾  [a] edit</span>
            </div>
            <div style={{ padding: "6px 10px" }}>
              <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)", borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4 }}>
                {"PID    USER     %CPU   RSS    THR  TIME+     COMMAND"}
              </div>
              {[
                ["2104","edge","34.2","1.84G","8","6:22:11","inference-svc",true],
                ["2210","edge","22.0","740M","12","6:21:55","video-pipeline",false],
                ["1910","www","  8.1","210M","4","6:22:14","api-gateway",false],
                ["1842","mqtt","2.0"," 94M","2","6:22:14","mqtt-bridge",false],
                ["1780","edge","1.0"," 62M","2","6:22:11","telemetry-agent",false],
                ["  14","root","1.9","  0K","-","6:22:22","[kworker/u12:0]",false],
              ].map((r, i) => (
                <div key={i} className="mono" style={{ fontSize: 11, color: r[7] ? "var(--amber)" : "var(--ink)" }}>
                  {r.slice(0,7).map((c, j) => (
                    <span key={j} style={{ display: "inline-block", width: [56, 60, 56, 56, 32, 72, 180][j] }}>{c}</span>
                  ))}
                </div>
              ))}
              <div className="mono muted" style={{ fontSize: 10, marginTop: 6 }}>highlight = flagged by leak/anomaly detector</div>
            </div>
          </div>

          <div className="box pad-0">
            <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--rule)" }}>
              <span className="mono" style={{ fontWeight: 600 }}>┌── SYSTEMD UNITS ──</span>
            </div>
            <div style={{ padding: "6px 10px" }}>
              {[
                ["docker.service",       "running", "restarts ×4", "amber"],
                ["nvargus-daemon",       "running", "err 1.2k/h",  "rose"],
                ["inference-svc.service","running", "OOM ×1",      "amber"],
                ["sshd.service",         "running", "ok",          "teal"],
                ["systemd-journald",     "running", "ok",          "teal"],
              ].map(([n, s, d, t]) => (
                <div key={n} className="mono" style={{ fontSize: 11, display: "flex", gap: 10 }}>
                  <span className={`dot ${t}`} style={{ marginTop: 5 }} />
                  <span style={{ width: 200 }}>{n}</span>
                  <span className="muted" style={{ width: 80 }}>{s}</span>
                  <span style={{ color: `var(--${t})` }}>{d}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="box pad-0">
            <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--rule)", display: "flex", justifyContent: "space-between" }}>
              <span className="mono" style={{ fontWeight: 600 }}>┌── LIVE TAIL · journalctl -f ──</span>
              <span><span className="live-dot" /> <span className="mono muted" style={{ fontSize: 11 }}>5m buffer</span></span>
            </div>
            <div style={{ padding: "6px 10px" }}>
              <LogLine ts="14:02:09" lvl="ERR"  svc="inference-svc" msg="cuda OOM: allocator exhausted (1.8G)" />
              <LogLine ts="14:02:07" lvl="WARN" svc="kernel"        msg="nvgpu fb_mmu: page fault gr" />
              <LogLine ts="14:02:01" lvl="INFO" svc="video-pipeline" msg="gst dropping frames (q=48)" tone="dim" />
              <LogLine ts="14:01:58" lvl="WARN" svc="thermal"        msg="zone cpu-therm 64°C" />
              <LogLine ts="14:01:55" lvl="INFO" svc="systemd"        msg="Started user@1000.service" tone="dim" />
              <LogLine ts="14:01:51" lvl="OK"   svc="mqtt-bridge"    msg="publish ok device/telemetry" tone="dim" />
              <LogLine ts="14:01:22" lvl="INFO" svc="inference-svc"  msg="tick 1000, 23.4 fps" tone="dim" />
            </div>
          </div>
        </div>
      </div>

      {/* footer status bar */}
      <div className="box ink" style={{ marginTop: 12, padding: "6px 12px", display: "flex", gap: 18, fontFamily: "var(--font-mono)", fontSize: 11 }}>
        <span>● health 82/100</span>
        <span>alerts 1</span>
        <span>↻ 1s</span>
        <span>buffer 5m</span>
        <span style={{ flex: 1 }} />
        <span className="muted">press [i] to run AI incident analysis →</span>
      </div>

      <div style={{ display: "flex", gap: 40, marginTop: 18 }}>
        <div className="annot ink">TUI vibe — efficient for SSH-only / headless Jetson devices</div>
        <div className="annot">Served by a small Python FastAPI app (psutil + jtop); works offline on the device</div>
      </div>
    </WireframeFrame>
  );
}

window.W3_Terminal = W3_Terminal;
