/* global React, WireframeFrame, Sparkline, BarHisto, UsageBar, LogLine */

function W2_Sidebar({ host = "jetson" }) {
  const isJetson = host === "jetson";

  const apps = [
    { name: "inference-svc",  state: "warn", cpu: 34, mem: "1.8G / ↗ leak", tag: "custom" },
    { name: "video-pipeline", state: "ok",   cpu: 22, mem: "740M",          tag: "custom" },
    { name: "api-gateway",    state: "ok",   cpu: 8,  mem: "210M",          tag: "custom" },
    { name: "mqtt-bridge",    state: "ok",   cpu: 2,  mem: "94M",           tag: "custom" },
    { name: "telemetry",      state: "idle", cpu: 1,  mem: "62M",           tag: "custom" },
  ];

  return (
    <WireframeFrame
      host={host}
      title="App Focus — Sidebar"
      meta="Pick an app on the left → everything on the right is about that app"
    >
      <div className="grid" style={{ gridTemplateColumns: "300px 1fr", gap: 14 }}>
        {/* LEFT RAIL */}
        <div className="col" style={{ gap: 14 }}>
          <div className="box pad-0">
            <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--rule)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--ink-2)", fontWeight: 600 }}>Monitored Apps</div>
                <div className="muted" style={{ fontSize: 11 }}>4 of 12 selected</div>
              </div>
              <span className="chip soft">＋ add</span>
            </div>
            <div style={{ padding: 8 }}>
              <div className="chip soft" style={{ width: "100%", justifyContent: "flex-start" }}>🔍  filter processes…</div>
            </div>
            <div>
              {apps.map((a, i) => (
                <div key={a.name} style={{
                  display: "flex", gap: 10, alignItems: "center",
                  padding: "10px 12px",
                  borderTop: "1px solid var(--rule-soft)",
                  background: i === 0 ? "var(--paper-2)" : "transparent",
                  borderLeft: i === 0 ? "3px solid var(--ink)" : "3px solid transparent",
                }}>
                  <span className={`chk ${i < 4 ? "on" : ""}`} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span className={`dot ${a.state === "warn" ? "amber" : a.state === "ok" ? "teal" : ""}`} />
                      <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{a.name}</span>
                    </div>
                    <div className="muted mono" style={{ fontSize: 10, marginTop: 2 }}>cpu {a.cpu}% · rss {a.mem}</div>
                  </div>
                  <div style={{ width: 50, height: 20 }}>
                    <Sparkline seed={a.name.length * 7} height={20} points={22}
                      trend={a.state === "warn" ? "leak" : "flat"}
                      className={a.state === "warn" ? "amber" : ""} />
                  </div>
                </div>
              ))}
              <div style={{ padding: "10px 12px", borderTop: "1px solid var(--rule-soft)" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Not monitored</div>
              </div>
              {["gst-plugin-scanner", "pulseaudio", "snapd", "containerd-shim"].map(n => (
                <div key={n} style={{ display: "flex", gap: 10, padding: "6px 12px", alignItems: "center" }}>
                  <span className="chk" />
                  <span className="mono muted" style={{ fontSize: 11 }}>{n}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="box">
            <div className="section-title"><span className="lbl">Host vitals</span></div>
            <div className="col" style={{ gap: 6 }}>
              <UsageBar label="CPU"   value="47%"    pct={47} />
              <UsageBar label="RAM"   value="5.8/8G" pct={72} tone="amber" />
              <UsageBar label="Disk"  value="62%"    pct={62} />
              {isJetson
                ? <UsageBar label="GPU" value="71%" pct={71} tone="teal" />
                : <UsageBar label="Net" value="24M" pct={24} />}
              <UsageBar label="Temp"  value="64°C"   pct={64} tone="amber" />
            </div>
          </div>
        </div>

        {/* RIGHT PANE */}
        <div className="col" style={{ gap: 14 }}>
          {/* Header strip */}
          <div className="box" style={{ display: "flex", gap: 18, alignItems: "center" }}>
            <div>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em" }}>Focused</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 600 }}>inference-svc</div>
              <div className="muted mono" style={{ fontSize: 11 }}>pid 2104 · py3.10 · up 6h 22m · /opt/app</div>
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ textAlign: "right" }}>
              <span className="chip amber">⚠ memory growth 38% / hr</span>
              <div style={{ marginTop: 6 }}>
                <span className="chip soft">restart</span>{" "}
                <span className="chip soft">logs ↗</span>{" "}
                <span className="chip fill">ask agent</span>
              </div>
            </div>
          </div>

          {/* Leak story — the star of this wireframe */}
          <div className="box">
            <div className="section-title">
              <span className="lbl">Memory — leak detector</span>
              <span className="legend"><span>RSS</span><span>heap</span><span>baseline</span></span>
            </div>
            <div style={{ height: 150, position: "relative" }}>
              <Sparkline seed={3} trend="leak" height={150} className="amber" />
              <div style={{ position: "absolute", left: "72%", top: 8, right: 8, borderLeft: "1.5px dashed var(--amber)", paddingLeft: 6 }}>
                <div className="hand" style={{ color: "var(--amber)", fontSize: 16, lineHeight: 1 }}>linear drift</div>
                <div className="mono muted" style={{ fontSize: 10 }}>+0.6 MB / min</div>
              </div>
            </div>
            <div className="hr-soft" />
            <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", fontSize: 11 }}>
              <div><div className="muted">RSS now</div><div className="mono" style={{ fontSize: 16 }}>1.84 G</div></div>
              <div><div className="muted">RSS 6h ago</div><div className="mono" style={{ fontSize: 16 }}>1.21 G</div></div>
              <div><div className="muted">Drift</div><div className="mono amber" style={{ fontSize: 16, color: "var(--amber)" }}>+520 MB</div></div>
              <div><div className="muted">Time to OOM</div><div className="mono" style={{ fontSize: 16 }}>~3h 40m</div></div>
            </div>
          </div>

          {/* two sub panels */}
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div className="box">
              <div className="section-title"><span className="lbl">CPU per thread</span><span className="chip soft">8 threads</span></div>
              <div className="col" style={{ gap: 4 }}>
                {["main","worker-0","worker-1","worker-2","gst-bus","torch-io","http","gc"].map((t, i) => (
                  <div key={t} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span className="mono muted" style={{ width: 80, fontSize: 10 }}>{t}</span>
                    <div style={{ flex: 1 }}><UsageBar pct={[80,55,52,48,20,35,8,3][i]} tone={i<4?"":"teal"} /></div>
                    <span className="mono" style={{ width: 34, textAlign: "right", fontSize: 10 }}>{[80,55,52,48,20,35,8,3][i]}%</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="box">
              <div className="section-title"><span className="lbl">App logs · tail</span><span className="live-dot" /></div>
              <LogLine ts="14:02:09" lvl="ERR"  svc="inference" msg="cuda OOM @ batch=8" />
              <LogLine ts="14:02:02" lvl="WARN" svc="inference" msg="allocator fragmenting 42%" />
              <LogLine ts="14:01:55" lvl="INFO" svc="inference" msg="loaded model yolov8n.engine" tone="dim" />
              <LogLine ts="14:01:40" lvl="WARN" svc="inference" msg="queue depth > 32" />
              <LogLine ts="14:01:22" lvl="INFO" svc="inference" msg="tick 1000, 23.4 fps" tone="dim" />
              <LogLine ts="14:00:58" lvl="INFO" svc="inference" msg="tick 900, 24.1 fps" tone="dim" />
              <div className="hr-soft" />
              <div className="mono muted" style={{ fontSize: 10 }}>/var/log/app/inference.log · otel-filelog</div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 40, marginTop: 18 }}>
        <div className="annot">App-first layout — customer apps are the whole point, everything else is context</div>
        <div className="annot ink">Leak detector is computed: RSS slope over rolling window + projected OOM</div>
      </div>
    </WireframeFrame>
  );
}

window.W2_Sidebar = W2_Sidebar;
