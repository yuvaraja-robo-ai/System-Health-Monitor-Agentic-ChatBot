/* global React, WireframeFrame, Sparkline, BarHisto, UsageBar, LogLine */

// Editorial / card stack — scannable, magazine-like, narrative reads top-to-bottom
function W4_Editorial({ host = "jetson" }) {
  const isJetson = host === "jetson";
  return (
    <WireframeFrame
      host={host}
      title="Briefing — Editorial"
      meta="Scroll-friendly narrative read · starts with a headline, ends with detail"
    >
      {/* Headline card */}
      <div className="box" style={{ padding: 24, marginBottom: 16, position: "relative" }}>
        <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
          <div style={{ flex: 1 }}>
            <div className="muted mono" style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase" }}>
              Daily briefing · 22 Apr 2026 · {isJetson ? "jetson-orin-nano" : "ubuntu-x86"}
            </div>
            <h1 style={{ fontSize: 34, lineHeight: 1.1, marginTop: 10, maxWidth: "90%" }}>
              System is <span style={{ color: "var(--amber)" }}>mostly healthy</span>, but{" "}
              <span className="ai">inference-svc has been leaking memory for 6 hours</span>.
            </h1>
            <div className="muted" style={{ marginTop: 10, fontSize: 13, maxWidth: "80%" }}>
              Headline generated on-demand · last run 14:02 · sources: 4 metrics streams · 2 log streams · 12 journal units
            </div>
          </div>
          <div style={{ textAlign: "right", minWidth: 160 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 56, lineHeight: 1 }}>82</div>
            <div className="muted mono" style={{ fontSize: 11 }}>health / 100</div>
            <div style={{ marginTop: 10 }}><span className="chip amber">1 warning</span></div>
            <div style={{ marginTop: 6 }}><span className="chip fill">▸ Re-run agent</span></div>
          </div>
        </div>
      </div>

      {/* Featured incident card */}
      <div className="box" style={{ padding: 18, marginBottom: 16, borderWidth: 2 }}>
        <div style={{ display: "flex", gap: 20 }}>
          <div style={{ flex: 2 }}>
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em" }}>Featured incident</div>
            <h2 style={{ fontSize: 20, marginTop: 6 }}>inference-svc · probable memory leak</h2>
            <div className="hr" />
            <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
              <div>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Probable cause</div>
                <div className="ai" style={{ fontSize: 13, marginTop: 4 }}>
                  CUDA tensor allocator fragmenting; RSS grows linearly regardless of load. Correlates with "allocator reserve exhausted" log lines.
                </div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Impact</div>
                <div style={{ fontSize: 13, marginTop: 4 }}>
                  Projected OOM in <b>~3h 40m</b> if not restarted. Video-pipeline dependent (gst drops at q&gt;48).
                </div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Confidence</div>
                <div style={{ fontSize: 13, marginTop: 4 }}>
                  <span className="mono" style={{ fontSize: 22 }}>0.78</span>{" "}
                  <span className="muted">based on 3 similar past incidents in KB</span>
                </div>
              </div>
            </div>
            <div className="hr-soft" />
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Suggested steps</div>
            <ol style={{ fontSize: 13, margin: "6px 0 0 18px", padding: 0, lineHeight: 1.7 }}>
              <li>Capture a py-spy dump and `nvidia-smi --query-gpu=memory.used` snapshot</li>
              <li>Restart <span className="mono">inference-svc.service</span> as a holdover</li>
              <li>Pin torch allocator: <span className="mono">PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True</span></li>
              <li>Compare with incident <span className="mono">#INC-204</span> (matched 0.86)</li>
            </ol>
          </div>
          <div style={{ flex: 1, borderLeft: "1px solid var(--rule-soft)", paddingLeft: 16 }}>
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>RSS over 6h</div>
            <div style={{ height: 120 }}><Sparkline seed={8} trend="leak" height={120} className="amber" /></div>
            <div className="mono muted" style={{ fontSize: 10, marginTop: 4 }}>1.21G → 1.84G  (+52%)</div>
            <div className="hr-soft" />
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>Related log spike</div>
            <div style={{ height: 44, color: "var(--rose)" }}><BarHisto seed={12} spikeAt={24} height={44} /></div>
            <div className="mono muted" style={{ fontSize: 10 }}>err/min · last 30m</div>
          </div>
        </div>
      </div>

      {/* 3-up vitals row */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 16 }}>
        <div className="box">
          <div className="section-title"><span className="lbl">Platform vitals</span></div>
          <div className="col" style={{ gap: 8 }}>
            <UsageBar label="CPU"  value="47%"     pct={47} />
            <UsageBar label="RAM"  value="5.8/8G"  pct={72} tone="amber" />
            <UsageBar label="Disk" value="62%"     pct={62} />
            <UsageBar label="Swap" value="5%"      pct={5} />
          </div>
        </div>
        <div className="box">
          <div className="section-title"><span className="lbl">Jetson SoC</span><span className="chip teal">15W</span></div>
          <div className="col" style={{ gap: 8 }}>
            <UsageBar label="GPU"    value="71%"    pct={71} tone="teal" />
            <UsageBar label="VRAM"   value="2.1/4G" pct={52} />
            <UsageBar label="Temp"   value="64°C"   pct={64} tone="amber" />
            <UsageBar label="Power"  value="11.4W"  pct={76} />
          </div>
        </div>
        <div className="box">
          <div className="section-title"><span className="lbl">Watched apps</span><span className="chip soft">5 · edit</span></div>
          <table className="wf-table">
            <tbody>
              <tr><td><span className="dot amber" /> inference-svc</td><td className="num">1.84G ↗</td></tr>
              <tr><td><span className="dot teal"  /> video-pipeline</td><td className="num">740M</td></tr>
              <tr><td><span className="dot teal"  /> api-gateway</td><td className="num">210M</td></tr>
              <tr><td><span className="dot teal"  /> mqtt-bridge</td><td className="num">94M</td></tr>
              <tr><td><span className="dot" /> telemetry</td><td className="num">62M</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Log section as editorial 2-col */}
      <div className="box" style={{ marginBottom: 16 }}>
        <div className="section-title"><span className="lbl">Recent critical log lines</span><span className="muted mono" style={{ fontSize: 11 }}>summarized into 3 clusters</span></div>
        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          {[
            { t: "CUDA OOM cluster", n: "12 events · 2h", svc: "inference-svc", s: "Repeated allocator exhaustion on batch 8. See featured incident." },
            { t: "GST frame drops",  n: "48 events · 30m", svc: "video-pipeline", s: "Queue depth sustained >48; correlated with CPU spikes on cpu3." },
            { t: "Thermal warnings", n: "4 events · 15m", svc: "thermal-zone", s: "cpu-therm crossed 64°C. Fan profile is auto — upgrade to quiet-max?" },
          ].map(c => (
            <div key={c.t} style={{ borderLeft: "2px solid var(--ink)", paddingLeft: 10 }}>
              <div className="muted mono" style={{ fontSize: 10 }}>{c.n}</div>
              <div style={{ fontWeight: 600, fontSize: 13, marginTop: 2 }}>{c.t}</div>
              <div className="muted mono" style={{ fontSize: 10, marginTop: 2 }}>{c.svc}</div>
              <div className="ai" style={{ fontSize: 12, marginTop: 6 }}>{c.s}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 40 }}>
        <div className="annot">Scannable — good for async users who check in a few times a day</div>
        <div className="annot ink">Wavy underline = LLM-authored text, plain = direct from metrics</div>
      </div>
    </WireframeFrame>
  );
}

window.W4_Editorial = W4_Editorial;
