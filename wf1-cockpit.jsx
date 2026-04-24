/* global React, WireframeFrame, Sparkline, BarHisto, UsageBar, LogLine, AppRow */

function W1_Cockpit({ host = "jetson" }) {
  const isJetson = host === "jetson";
  return (
    <WireframeFrame
      host={host}
      title="Overview — Cockpit"
      meta="Dense single-pane ops view · everything one glance away"
    >
      {/* Row 1 — health score + key KPIs + ai button */}
      <div className="grid" style={{ gridTemplateColumns: "1.1fr 2.2fr 1fr", marginBottom: 14 }}>
        <div className="box" style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <div>
            <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em" }}>Health Score</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 46, lineHeight: 1, marginTop: 4 }}>82<span className="dim" style={{ fontSize: 20 }}>/100</span></div>
            <div style={{ marginTop: 6 }}><span className="chip amber">1 warning</span></div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ height: 70 }}><Sparkline seed={11} trend="down" height={70} /></div>
            <div className="legend" style={{ marginTop: 4 }}><span>trailing 24h</span></div>
          </div>
        </div>

        <div className="box">
          <div className="section-title"><span className="lbl">Key signals · live</span><span className="mono muted">tick 1s</span></div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {[
              { k: "CPU",    v: "47%", t: "flat",  tone: "" },
              { k: "RAM",    v: "5.8/8G", t: "leak", tone: "amber" },
              { k: "Disk",   v: "62%", t: "flat",  tone: "" },
              { k: isJetson ? "GPU" : "Net", v: isJetson ? "71%" : "24Mb/s", t: "spike", tone: "" },
            ].map(({ k, v, t, tone }) => (
              <div key={k}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>{k}</div>
                <div className="mono" style={{ fontSize: 18, marginTop: 2 }}>{v}</div>
                <div style={{ height: 28, marginTop: 4 }}><Sparkline seed={k.charCodeAt(0)} trend={t} height={28} className={tone} /></div>
              </div>
            ))}
          </div>
        </div>

        <div className="box ink" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", opacity: 0.7 }}>Ask the agent</div>
            <div style={{ fontFamily: "var(--font-hand)", fontSize: 22, marginTop: 6 }}>Something look off?</div>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
            <span className="chip fill" style={{ borderColor: "#fff", background: "transparent", color: "#fff" }}>▸ Diagnose now</span>
            <span className="chip fill" style={{ borderColor: "#555", background: "transparent", color: "#ccc" }}>last 5m</span>
          </div>
        </div>
      </div>

      {/* Row 2 — jetson strip + ubuntu strip (always both) */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 14 }}>
        <div className="box">
          <div className="section-title"><span className="lbl">Jetson Orin · SoC</span><span className="chip teal">on · 15W mode</span></div>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <UsageBar label="GPU load"      value="71%"     pct={71} tone="teal" />
            <UsageBar label="GPU mem"       value="2.1/4G"  pct={52} />
            <UsageBar label="SoC temp"      value="64°C"    pct={64} tone="amber" />
            <UsageBar label="Power draw"    value="11.4W"   pct={76} />
            <UsageBar label="EMC bw"        value="38%"     pct={38} />
            <UsageBar label="Fan"           value="auto 40%" pct={40} />
          </div>
        </div>
        <div className="box">
          <div className="section-title"><span className="lbl">Ubuntu x86 · platform</span><span className="chip soft">headless</span></div>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <UsageBar label="cpu0-7 avg"    value="47%"     pct={47} />
            <UsageBar label="swap used"     value="0.2G"    pct={10} />
            <UsageBar label="sda1 /"        value="62%"     pct={62} />
            <UsageBar label="nvme0 /data"   value="44%"     pct={44} />
            <UsageBar label="net eth0"      value="24Mb/s"  pct={24} />
            <UsageBar label="pkg temp"      value="58°C"    pct={58} />
          </div>
        </div>
      </div>

      {/* Row 3 — apps (customer-focused) + services + logs */}
      <div className="grid" style={{ gridTemplateColumns: "1.3fr 1fr 1.3fr" }}>
        <div className="box">
          <div className="section-title"><span className="lbl">Monitored apps</span><span className="chip soft">+ add</span></div>
          <table className="wf-table">
            <thead><tr><th></th><th>App</th><th>PID</th><th>CPU</th><th>RSS</th><th>24h</th></tr></thead>
            <tbody>
              <AppRow on name="inference-svc"  pid={2104} cpu={34} mem="1.8G" trend="leak" leak />
              <AppRow on name="video-pipeline" pid={2210} cpu={22} mem="740M" trend="spike" />
              <AppRow on name="mqtt-bridge"    pid={1842} cpu={2}  mem="94M"  trend="flat" />
              <AppRow on name="api-gateway"    pid={1910} cpu={8}  mem="210M" trend="flat" />
              <AppRow      name="telemetry"    pid={1780} cpu={1}  mem="62M"  trend="flat" />
            </tbody>
          </table>
          <div className="annot" style={{ marginTop: 8 }}>nmon-style list — click any app to isolate its CPU/RSS timeline</div>
        </div>

        <div className="box">
          <div className="section-title"><span className="lbl">Top failing services</span><span className="chip rose">3</span></div>
          <table className="wf-table">
            <tbody>
              <tr><td>● <b>docker.service</b></td><td className="num">restarts ×4</td></tr>
              <tr><td>● nvargus-daemon</td><td className="num">err 1.2k/h</td></tr>
              <tr><td>● inference-svc</td><td className="num">OOM ×1</td></tr>
              <tr><td className="muted">○ sshd</td><td className="num muted">ok</td></tr>
              <tr><td className="muted">○ systemd-resolved</td><td className="num muted">ok</td></tr>
            </tbody>
          </table>
        </div>

        <div className="box" style={{ display: "flex", flexDirection: "column" }}>
          <div className="section-title">
            <span className="lbl">Live log tail · journalctl -f</span>
            <span><span className="live-dot" /> <span className="mono" style={{ fontSize: 10, marginLeft: 4 }}>streaming</span></span>
          </div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <LogLine ts="14:02:09" lvl="ERR"  svc="inference-svc" msg="cuda OOM: allocator reserve exhausted (1.8G)" />
            <LogLine ts="14:02:07" lvl="WARN" svc="kernel"        msg="nvgpu: fb_mmu: page fault, engine=gr" />
            <LogLine ts="14:02:01" lvl="INFO" svc="video-pipeline" msg="gst-launch dropping frames (q=48)" tone="dim" />
            <LogLine ts="14:01:58" lvl="WARN" svc="thermal"       msg="zone cpu-therm reached 64°C" />
            <LogLine ts="14:01:55" lvl="INFO" svc="systemd"       msg="Started user@1000.service" tone="dim" />
            <LogLine ts="14:01:51" lvl="INFO" svc="mqtt-bridge"   msg="publish ok topic=device/telemetry" tone="dim" />
            <LogLine ts="14:01:48" lvl="OK"   svc="api-gateway"   msg="healthcheck 200 (14ms)" tone="dim" />
          </div>
          <div className="hr-soft" />
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="chip soft">level: all</span>
            <span className="chip soft">svc: any</span>
            <span className="chip soft">/regex</span>
            <span className="chip">pause</span>
          </div>
        </div>
      </div>

      {/* bottom annotations */}
      <div style={{ display: "flex", gap: 40, marginTop: 18 }}>
        <div className="annot ink">Everything visible, zero scrolling — best for wall-mount / ops room</div>
        <div className="annot">AI stays quiet until you hit "Diagnose now" — matches "on-demand"</div>
      </div>
    </WireframeFrame>
  );
}

window.W1_Cockpit = W1_Cockpit;
