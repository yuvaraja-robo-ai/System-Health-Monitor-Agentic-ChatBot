/* global React, WireframeFrame, Sparkline, BarHisto, UsageBar, LogLine */

// App-centric "Leak Hunter" — focused on customer apps, memory leak detection, app selection
function W5_LeakHunter({ host = "jetson" }) {
  const isJetson = host === "jetson";

  const apps = [
    { name: "inference-svc",  pid: 2104, cpu: 34, rss: 1840, peak: 1920, slope: "+0.6M/m", ttl: "3h 40m", state: "leak" },
    { name: "video-pipeline", pid: 2210, cpu: 22, rss: 740,  peak: 810,  slope: "+0.0",    ttl: "—",      state: "ok" },
    { name: "api-gateway",    pid: 1910, cpu: 8,  rss: 210,  peak: 245,  slope: "+0.0",    ttl: "—",      state: "ok" },
    { name: "mqtt-bridge",    pid: 1842, cpu: 2,  rss: 94,   peak: 98,   slope: "+0.0",    ttl: "—",      state: "ok" },
  ];

  return (
    <WireframeFrame
      host={host}
      title="Leak Hunter — App-centric"
      meta="Customer apps at the top · memory leak story as the spine of the page"
    >
      {/* TOP — app picker as chips */}
      <div className="box" style={{ padding: "14px 16px", marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 10 }}>
          <div>
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em" }}>Step 1 · pick apps to monitor</div>
            <div className="hand" style={{ fontSize: 20 }}>you can add any binary, service, or container</div>
          </div>
          <div style={{ flex: 1 }} />
          <span className="chip soft">import from docker ps</span>
          <span className="chip soft">pick from systemd</span>
          <span className="chip fill">＋ add custom</span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {[
            ["inference-svc", true, "amber"],
            ["video-pipeline", true, "teal"],
            ["api-gateway", true, "teal"],
            ["mqtt-bridge", true, "teal"],
            ["telemetry-agent", true, ""],
            ["gst-plugin-scanner", false, ""],
            ["containerd-shim", false, ""],
            ["pulseaudio", false, ""],
            ["snapd", false, ""],
            ["chrony", false, ""],
            ["docker:redis", false, ""],
            ["docker:postgres", false, ""],
          ].map(([n, on, tone]) => (
            <span key={n} className={`chip ${on ? (tone || "fill") : "soft"}`} style={{ padding: "4px 10px" }}>
              <span className={`chk ${on ? "on" : ""}`} />
              <span className="mono">{n}</span>
            </span>
          ))}
        </div>
      </div>

      {/* MAIN — the leak story */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        {/* overlaid chart of all app RSS */}
        <div className="box">
          <div className="section-title">
            <span className="lbl">Memory · RSS per app · last 6h</span>
            <span className="legend">
              <span style={{ color: "var(--amber)" }}>inference-svc</span>
              <span>video-pipeline</span>
              <span className="muted">api-gateway</span>
            </span>
          </div>
          <div style={{ height: 200, position: "relative" }}>
            <div style={{ position: "absolute", inset: 0 }}><Sparkline seed={21} trend="leak" min={0.2} max={0.85} height={200} className="amber" /></div>
            <div style={{ position: "absolute", inset: 0, opacity: 0.6 }}><Sparkline seed={22} trend="flat" min={0.28} max={0.40} height={200} /></div>
            <div style={{ position: "absolute", inset: 0, opacity: 0.35 }}><Sparkline seed={23} trend="flat" min={0.10} max={0.15} height={200} /></div>
            {/* OOM projection guide */}
            <div style={{ position: "absolute", left: "85%", top: 4, bottom: 4, borderLeft: "1.5px dashed var(--rose)", paddingLeft: 6 }}>
              <div className="hand" style={{ color: "var(--rose)", fontSize: 16, lineHeight: 1 }}>proj. OOM</div>
              <div className="mono muted" style={{ fontSize: 10 }}>~17:42</div>
            </div>
          </div>
          <div className="hr-soft" />
          <div className="mono muted" style={{ fontSize: 11 }}>
            leak detector: linear regression on 30-min RSS window, flags slope &gt; 0.2 MB/min
          </div>
        </div>

        {/* ranked table */}
        <div className="box">
          <div className="section-title">
            <span className="lbl">Per-app memory health</span>
            <span className="chip soft">sort: slope ▾</span>
          </div>
          <table className="wf-table">
            <thead>
              <tr><th>App</th><th className="num">RSS</th><th className="num">Peak</th><th className="num">Slope</th><th className="num">TTL→OOM</th><th></th></tr>
            </thead>
            <tbody>
              {apps.map(a => (
                <tr key={a.pid} style={{ background: a.state === "leak" ? "rgba(217,162,50,0.08)" : "transparent" }}>
                  <td>
                    <span className={`dot ${a.state === "leak" ? "amber" : "teal"}`} />{" "}
                    <b>{a.name}</b>
                    <div className="muted" style={{ fontSize: 10 }}>pid {a.pid} · cpu {a.cpu}%</div>
                  </td>
                  <td className="num">{a.rss}M</td>
                  <td className="num muted">{a.peak}M</td>
                  <td className="num" style={{ color: a.state === "leak" ? "var(--amber)" : "inherit" }}>{a.slope}</td>
                  <td className="num">{a.ttl}</td>
                  <td style={{ width: 70 }}>
                    <div style={{ height: 18 }}>
                      <Sparkline seed={a.pid} points={24} height={18}
                        trend={a.state === "leak" ? "leak" : "flat"}
                        className={a.state === "leak" ? "amber" : ""} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="hr-soft" />
          <div style={{ display: "flex", gap: 6 }}>
            <span className="chip soft">snapshot py-spy</span>
            <span className="chip soft">restart app</span>
            <span className="chip soft">pin limits</span>
          </div>
        </div>
      </div>

      {/* ROW — crash history + restart counts (first-class) */}
      <div className="box" style={{ marginBottom: 14 }}>
        <div className="section-title">
          <span className="lbl">App crash & restart history · 24h</span>
          <span className="chip rose">2 crashes</span>
        </div>
        <div className="grid" style={{ gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 14 }}>
          <div>
            <div className="muted mono" style={{ fontSize: 10 }}>timeline (24h) — ticks = crash, bars = restart</div>
            <svg className="spark" viewBox="0 0 400 60" preserveAspectRatio="none" style={{ height: 60 }}>
              <line className="axis" x1="0" y1="50" x2="400" y2="50" />
              {[40, 85, 120, 170, 210, 260, 310, 355].map((x, i) => (
                <g key={i}>
                  <rect x={x - 3} y={35} width={6} height={15} fill="var(--ink-3)" />
                </g>
              ))}
              {[{x:140, label:"SIGKILL"},{x:300, label:"SIGSEGV"}].map((c, i) => (
                <g key={i}>
                  <line x1={c.x} x2={c.x} y1={6} y2={50} stroke="var(--rose)" strokeWidth="1.5" />
                  <circle cx={c.x} cy={6} r={3} fill="var(--rose)" />
                  <text x={c.x + 4} y={12} fontSize="9" fill="var(--rose)">{c.label}</text>
                </g>
              ))}
              {[0, 100, 200, 300, 400].map(x => <text key={x} x={x} y={58} fontSize="8">{`-${Math.round((400-x)/400*24)}h`}</text>)}
            </svg>
          </div>
          <div>
            <table className="wf-table">
              <thead><tr><th>App</th><th className="num">crashes</th><th className="num">restarts</th></tr></thead>
              <tbody>
                <tr><td><b>inference-svc</b></td><td className="num" style={{color:"var(--rose)"}}>1</td><td className="num">3</td></tr>
                <tr><td>video-pipeline</td><td className="num">0</td><td className="num">1</td></tr>
                <tr><td>api-gateway</td><td className="num" style={{color:"var(--rose)"}}>1</td><td className="num">2</td></tr>
                <tr><td>mqtt-bridge</td><td className="num muted">0</td><td className="num muted">0</td></tr>
              </tbody>
            </table>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Last crash</div>
            <div className="mono" style={{ fontSize: 13, marginTop: 4 }}>inference-svc</div>
            <div className="mono muted" style={{ fontSize: 10 }}>09:14 · exit 137 · SIGKILL</div>
            <div className="mono" style={{ fontSize: 11, marginTop: 6 }}>reason: <span className="ai">likely OOM killer (cgroup memory limit hit)</span></div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Crash signals detected</div>
            <div className="col" style={{ gap: 4, marginTop: 4 }}>
              <div className="mono" style={{ fontSize: 11 }}><span className="dot rose" /> SIGSEGV  · 1</div>
              <div className="mono" style={{ fontSize: 11 }}><span className="dot rose" /> SIGKILL  · 1</div>
              <div className="mono" style={{ fontSize: 11 }}><span className="dot" /> SIGTERM  · 0</div>
              <div className="mono" style={{ fontSize: 11 }}><span className="dot amber" /> exit≠0  · 3</div>
            </div>
            <div className="annot" style={{ marginTop: 8 }}>pulled from journalctl CRIT + systemd state</div>
          </div>
        </div>
      </div>

      {/* ROW — custom app logs (logs FROM apps, not system) */}
      <div className="grid" style={{ gridTemplateColumns: "2fr 1fr", gap: 14, marginBottom: 14 }}>
        <div className="box">
          <div className="section-title">
            <span className="lbl">Custom app logs · filelog receiver</span>
            <span>
              <span className="chip soft">inference.log</span>{" "}
              <span className="chip soft">pipeline.log</span>{" "}
              <span className="chip soft">gateway.json</span>{" "}
              <span className="live-dot" />
            </span>
          </div>
          <LogLine ts="14:02:09" lvl="ERR"  svc="inference" msg='{"event":"oom","batch":8,"device":"cuda:0","reserved":"1.80G"}' />
          <LogLine ts="14:02:02" lvl="WARN" svc="inference" msg='{"event":"alloc_fragment","ratio":0.42}' />
          <LogLine ts="14:01:40" lvl="WARN" svc="inference" msg='{"event":"queue_full","depth":33,"cap":32}' />
          <LogLine ts="14:01:22" lvl="INFO" svc="inference" msg='{"event":"tick","n":1000,"fps":23.4}' tone="dim" />
          <LogLine ts="14:01:09" lvl="INFO" svc="pipeline"  msg='{"event":"drop","frames":3,"q":48}' />
          <LogLine ts="14:00:58" lvl="INFO" svc="gateway"   msg='{"event":"req","path":"/predict","ms":14}' tone="dim" />
          <LogLine ts="14:00:40" lvl="INFO" svc="gateway"   msg='{"event":"req","path":"/predict","ms":16}' tone="dim" />
          <div className="hr-soft" />
          <div className="mono muted" style={{ fontSize: 10 }}>parser: json · fields extracted: event, batch, device, ms, depth, cap</div>
        </div>

        <div className="box">
          <div className="section-title"><span className="lbl">Host vitals</span></div>
          <div className="col" style={{ gap: 6 }}>
            <UsageBar label="CPU"  value="47%"    pct={47} />
            <UsageBar label="RAM"  value="5.8/8G" pct={72} tone="amber" />
            <UsageBar label="Disk" value="62%"    pct={62} />
            {isJetson && <UsageBar label="GPU"  value="71%"  pct={71} tone="teal" />}
            {isJetson && <UsageBar label="VRAM" value="2.1G" pct={52} />}
            <UsageBar label="Temp" value="64°C"   pct={64} tone="amber" />
            <UsageBar label="Power" value={isJetson ? "11.4W" : "—"} pct={isJetson?76:0} />
          </div>
        </div>
      </div>

      {/* AI on-demand strip */}
      <div className="box ink" style={{ padding: "14px 18px", display: "flex", gap: 16, alignItems: "center" }}>
        <div style={{ fontFamily: "var(--font-hand)", fontSize: 22, color: "var(--teal)" }}>Need a diagnosis?</div>
        <div style={{ flex: 1 }} className="muted">
          Agent will pull top errors, 30-min metric anomalies, and similar past incidents from the vector KB —{" "}
          <span className="mono" style={{ color: "#ddd" }}>python -m systemhealth.agent diagnose --app inference-svc</span>
        </div>
        <span className="chip fill" style={{ borderColor: "#fff", background: "transparent", color: "#fff" }}>▸ Run</span>
      </div>

      <div style={{ display: "flex", gap: 40, marginTop: 18 }}>
        <div className="annot">Leak detection is the spine — everything on the page supports the RSS story</div>
        <div className="annot ink">Matches nmon's spirit: app-by-app view, with slope &amp; TTL→OOM columns that nmon doesn't have</div>
      </div>
    </WireframeFrame>
  );
}

window.W5_LeakHunter = W5_LeakHunter;
