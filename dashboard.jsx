/* global React, ReactDOM */
const { useEffect, useMemo, useReducer, useRef, useState } = React;

// ───── utilities ─────
const fmtBytes = (b) => {
  if (!b && b !== 0) return "—";
  const u = ["B", "K", "M", "G", "T"]; let i = 0; let v = b;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(v < 10 ? 1 : 0) + u[i];
};
const fmtPct = (v) => v == null ? "—" : `${v.toFixed(0)}%`;
const fmtBps = (b) => {
  if (b == null) return "—";
  const u = ["B/s", "K/s", "M/s", "G/s"]; let i = 0; let v = b;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(1) + u[i];
};
const fmtDuration = (s) => {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(0)}s`;
  if (s < 3600) return `${(s / 60).toFixed(0)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
};
const tsToHMS = (ts) => {
  const d = typeof ts === "string" ? new Date(ts) : new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour12: false });
};

// ───── ws hook with reconnect ─────
function useWS(path, onMessage) {
  const [status, setStatus] = useState("connecting");
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;
  useEffect(() => {
    let stop = false;
    let ws;
    let retry;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}${path}`;
    const connect = () => {
      if (stop) return;
      ws = new WebSocket(url);
      ws.onopen = () => setStatus("live");
      ws.onmessage = (e) => { try { cbRef.current(JSON.parse(e.data)); } catch (err) { console.warn("ws parse error", err); } };
      ws.onerror = () => setStatus("down");
      ws.onclose = () => {
        setStatus("down");
        if (!stop) retry = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => { stop = true; clearTimeout(retry); try { ws && ws.close(); } catch {} };
  }, [path]);
  return status;
}

// ───── polling hook ─────
function usePoll(url, interval = 5000) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    if (!url) {
      setData(null);
      setErr(null);
      return;
    }
    let alive = true;
    const tick = () => fetch(url).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }).then(j => { if (alive) { setData(j); setErr(null); } }).catch(e => { if (alive) setErr(e.message); });
    tick();
    const id = setInterval(tick, interval);
    return () => { alive = false; clearInterval(id); };
  }, [url, interval]);
  return [data, err];
}

// ───── ring buffer for live series ─────
function useSeries(max = 120) {
  const ref = useRef([]);
  const [, force] = useReducer(x => x + 1, 0);
  const push = (v) => {
    ref.current.push(v);
    if (ref.current.length > max) ref.current.shift();
    force();
  };
  return [ref.current, push];
}

// ───── sparkline ─────
function Spark({ data, tone = "accent", height = 48, min, max }) {
  if (!data || data.length < 2) return <svg className="mini-spark" viewBox="0 0 100 100" preserveAspectRatio="none" />;
  const W = 100, H = 100;
  const lo = min != null ? min : Math.min(...data);
  const hi = max != null ? max : Math.max(...data);
  const span = hi - lo || 1;
  const step = W / (data.length - 1);
  const color = tone === "warn" ? "#f0c674" : tone === "err" ? "#e26b6b" : tone === "info" ? "#7aa2f7" : "#7bd88f";
  const pts = data.map((v, i) => `${(i * step).toFixed(2)},${(H - ((v - lo) / span) * H).toFixed(2)}`).join(" ");
  const fill = `M0,${H} L${pts.split(" ").join(" L")} L${W},${H} Z`;
  return (
    <svg className="mini-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }}>
      <path d={fill} fill={color} opacity="0.12" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// ───── top bar ─────
function TopBar({ meta, health, wsStatus }) {
  const score = health?.score ?? null;
  const tone = score == null ? "" : score >= 85 ? "ok" : score >= 60 ? "warn" : "err";
  const drivers = (health?.drivers || []).map(d => d.factor).slice(0, 3).join(" · ");
  return (
    <div className="topbar">
      <div className="brand">SystemHealth</div>
      <div className="meta">
        <span><span className={`ws-dot ${wsStatus}`} />{wsStatus}</span>
        {meta && <>
          <span><b>{meta.host}</b> · {meta.arch}</span>
          <span>up {fmtDuration(meta.uptime_s)}</span>
          {meta.power_mode && <span>pwr {meta.power_mode}</span>}
          {meta.jetson_model && <span>{meta.jetson_model}</span>}
        </>}
      </div>
      <div className="spacer" />
      <div className={`health ${tone}`}>
        <div>
          <div style={{ fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".1em" }}>Health</div>
          <div className="drivers">{drivers || "all clear"}</div>
        </div>
        <div className="score">{score ?? "—"}<span style={{ fontSize: 11, color: "var(--fg-3)" }}>/100</span></div>
      </div>
    </div>
  );
}

// ───── health (unified single-pane view: USE + RED + anomalies + correlations) ─────
function HealthView({ meta, sys, jetson, procs, health }) {
  const [anomalies] = usePoll("/api/anomalies?history_limit=0", 5000);
  const [correlations] = usePoll("/api/correlate?window=300&top=10", 15000);
  const [leaks] = usePoll("/api/leaks", 10000);
  const [crashes] = usePoll("/api/crashes?window=24h", 30000);
  const [errorLogs] = usePoll("/api/logs?since=900&limit=5", 10000);

  const score = health?.score;
  const tone = score == null ? "" : score >= 85 ? "ok" : score >= 60 ? "warn" : "err";
  const drivers = health?.drivers || [];
  const memPct = sys?.mem?.total ? 100 * sys.mem.used / sys.mem.total : 0;
  const diskHot = (sys?.disks || []).reduce((a, b) => (b.pct > (a?.pct ?? 0) ? b : a), null);
  const psiMem = sys?.pressure?.memory?.some_avg10 ?? null;
  const psiCpu = sys?.pressure?.cpu?.some_avg10 ?? null;
  const psiIo = sys?.pressure?.io?.some_avg10 ?? null;
  const saturation = sys?.cpu?.saturation_pct ?? null;
  const cores = sys?.cpu?.cores || (sys?.cpu?.per_core?.length ?? 0);
  const errorCount = (crashes?.counts && Object.values(crashes.counts).reduce((a, b) => a + b, 0)) || 0;
  const leakCount = (leaks || []).filter(l => l.flagged).length;
  const anomCurrent = anomalies?.current || [];
  const topProcs = (procs || []).slice(0, 5);
  const volumeRank = correlations?.volume || [];
  const pairs = correlations?.pairs || [];

  const satTone = saturation == null ? "ok" : saturation > 150 ? "err" : saturation > 100 ? "warn" : "ok";
  const psiTone = (v) => v == null ? "ok" : v > 0.2 ? "err" : v > 0.05 ? "warn" : "ok";

  return (
    <div className="col-stack">
      <div className={`card hero ${tone}`} style={{ gridTemplateColumns: "1fr 140px" }}>
        <div className="hero-main">
          <div className="subtle">Health · unified view</div>
          <h1 style={{ fontSize: 28 }}>{score != null ? `${score} / 100` : "computing…"}</h1>
          <div className="svc-sub">
            {drivers.length === 0 && "all systems nominal"}
            {drivers.slice(0, 4).map((d, i) => (
              <span key={i} style={{ marginRight: 10 }}>
                <span className={`chip ${d.weight <= -15 ? "err" : d.weight <= -8 ? "warn" : ""}`}>
                  {d.factor}{d.count ? ` ×${d.count}` : ""} ({d.weight})
                </span>
              </span>
            ))}
          </div>
        </div>
        <div className="hero-score" style={{ fontFamily: "var(--mono)" }}>
          <div style={{ fontSize: 11, color: "var(--fg-3)" }}>anomalies</div>
          <div className={`big ${anomCurrent.length > 0 ? "err" : ""}`}
               style={{ color: anomCurrent.length ? "var(--err)" : "var(--fg)" }}>
            {anomCurrent.length}
          </div>
          <div className="sub">leaks {leakCount} · crashes {errorCount}</div>
        </div>
      </div>

      <div className="grid three">
        <div className="card">
          <h3>Utilization · USE</h3>
          <div className="kv" style={{ gridTemplateColumns: "100px 1fr" }}>
            <span className="k">cpu</span><span>{fmtPct(sys?.cpu?.total)}</span>
            <span className="k">mem</span><span>{fmtPct(memPct)} · {fmtBytes(sys?.mem?.used)}</span>
            <span className="k">disk</span><span>{diskHot ? `${diskHot.mount} ${fmtPct(diskHot.pct)}` : "—"}</span>
            {jetson && <><span className="k">gpu</span><span>{fmtPct(jetson?.gpu_load)} · {fmtBytes(jetson?.gpu_ram_used)}</span></>}
            {jetson && <><span className="k">power</span><span>{jetson?.power_w != null ? `${jetson.power_w.toFixed(1)}W` : "—"}</span></>}
          </div>
        </div>
        <div className="card">
          <h3>Saturation · USE</h3>
          <div className="kv" style={{ gridTemplateColumns: "130px 1fr" }}>
            <span className="k">cpu load / cores</span>
            <span className={`chip ${satTone}`}>
              {saturation != null ? `${saturation.toFixed(0)}%` : "—"} · load {(sys?.cpu?.load || [0])[0]?.toFixed(2)} / {cores}
            </span>
            <span className="k">psi cpu</span>
            <span className={`chip ${psiTone(psiCpu)}`}>{psiCpu != null ? psiCpu.toFixed(2) : "—"}</span>
            <span className="k">psi memory</span>
            <span className={`chip ${psiTone(psiMem)}`}>{psiMem != null ? psiMem.toFixed(2) : "—"}</span>
            <span className="k">psi io</span>
            <span className={`chip ${psiTone(psiIo)}`}>{psiIo != null ? psiIo.toFixed(2) : "—"}</span>
            <span className="k">ctx switch/s</span>
            <span>{sys?.cpu?.ctx_switch_rate != null ? Math.round(sys.cpu.ctx_switch_rate) : "—"}</span>
            {jetson?.soc_temp && <><span className="k">soc temp</span><span className={`chip ${jetson.soc_temp > 80 ? "err" : jetson.soc_temp > 70 ? "warn" : "ok"}`}>{jetson.soc_temp.toFixed(1)}°C</span></>}
          </div>
        </div>
        <div className="card">
          <h3>Errors · USE + RED</h3>
          <div className="kv" style={{ gridTemplateColumns: "100px 1fr" }}>
            <span className="k">crashes 24h</span><span className={errorCount > 0 ? "chip err" : "chip ok"}>{errorCount}</span>
            <span className="k">leaks</span><span className={leakCount > 0 ? "chip err" : "chip ok"}>{leakCount}</span>
            <span className="k">anomalies</span><span className={anomCurrent.length > 0 ? "chip warn" : "chip ok"}>{anomCurrent.length}</span>
            <span className="k">error logs</span>
            <span>{(errorLogs || []).filter(r => ["ERR", "ERROR", "CRIT", "FATAL"].includes((r.level || "").toUpperCase())).length}/5 recent</span>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>🚨 Active Anomalies ({anomCurrent.length})</h3>
        {anomCurrent.length === 0 && <div className="empty" style={{ padding: 10 }}>all metrics within normal range</div>}
        {anomCurrent.length > 0 && (
          <table>
            <thead>
              <tr><th>Metric</th><th className="num">Current</th><th className="num">Baseline</th><th className="num">σ</th><th className="num">z-score</th></tr>
            </thead>
            <tbody>
              {anomCurrent.map((a, i) => (
                <tr key={i}>
                  <td>{a.metric}</td>
                  <td className="num">{a.value}</td>
                  <td className="num">{a.mean}</td>
                  <td className="num">{a.stdev}</td>
                  <td className="num"><span className={`chip ${a.z > 5 ? "err" : "warn"}`}>{a.z}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid two">
        <div className="card">
          <h3>🔗 Correlated Metrics · last 5 min</h3>
          <div className="svc-sub" style={{ marginBottom: 8 }}>
            metrics with biggest deviation from baseline (4× window preceding)
          </div>
          {volumeRank.length === 0 && <div className="empty" style={{ padding: 10 }}>gathering data…</div>}
          {volumeRank.length > 0 && (
            <table style={{ fontSize: 11 }}>
              <thead><tr><th>Metric</th><th className="num">Baseline</th><th className="num">Now</th><th className="num">Δ%</th></tr></thead>
              <tbody>
                {volumeRank.slice(0, 8).map((c, i) => (
                  <tr key={i}>
                    <td>{c.metric}</td>
                    <td className="num">{c.baseline_mean}</td>
                    <td className="num">{c.incident_mean}</td>
                    <td className="num" style={{ color: Math.abs(c.delta_pct) > 50 ? "var(--err)" : Math.abs(c.delta_pct) > 20 ? "var(--warn)" : "var(--fg)" }}>
                      {c.delta_pct > 0 ? "+" : ""}{c.delta_pct}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h3>🔗 Metric Pairs · strong correlation |r| &gt; 0.6</h3>
          {pairs.length === 0 && <div className="empty" style={{ padding: 10 }}>no strong correlations yet</div>}
          {pairs.length > 0 && (
            <table style={{ fontSize: 11 }}>
              <thead><tr><th>A</th><th>B</th><th className="num">r</th></tr></thead>
              <tbody>
                {pairs.slice(0, 10).map((p, i) => (
                  <tr key={i}>
                    <td>{p.a}</td>
                    <td>{p.b}</td>
                    <td className="num"><span className={`chip ${Math.abs(p.r) > 0.9 ? "info" : ""}`}>{p.r > 0 ? "+" : ""}{p.r}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {meta?.host === "jetson" && jetson?.temps && Object.keys(jetson.temps).length > 0 && (
        <div className="card">
          <h3>🔥 Thermal Heatmap · all Jetson sensors</h3>
          <div className="sensor-grid">
            {Object.entries(jetson.temps).map(([k, v]) => (
              <div key={k} className="sensor-chip">
                <div className="sensor-name">{k}</div>
                <div className={`sensor-val ${v > 80 ? "err" : v > 65 ? "warn" : "ok"}`}>{v.toFixed(1)}°C</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid two">
        <div className="card">
          <h3>📊 Top Processes</h3>
          <table>
            <thead><tr><th>PID</th><th>Name</th><th className="num">CPU%</th><th className="num">RSS</th></tr></thead>
            <tbody>
              {topProcs.length === 0 && <tr><td colSpan="4" className="empty">waiting for process snapshot</td></tr>}
              {topProcs.map(p => (
                <tr key={p.pid}>
                  <td>{p.pid}</td>
                  <td>{p.name}</td>
                  <td className="num">{(p.cpu || 0).toFixed(1)}</td>
                  <td className="num">{fmtBytes(p.rss)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>📜 Recent Errors</h3>
          <div className="logs compact" style={{ maxHeight: 220 }}>
            {(errorLogs || []).length === 0 && <div className="empty">no recent errors</div>}
            {(errorLogs || []).map((r, i) => (
              <div key={i} className="log-row">
                <span className="ts">{tsToHMS(r.ts)}</span>
                <span className={`lv ${(r.level || "INFO").toUpperCase()}`}>{(r.level || "INFO").toUpperCase()}</span>
                <span className="svc">{r.service || "—"}</span>
                <span className="msg">{r.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ───── threshold settings ─────
function ThresholdSettings({ onClose }) {
  const [vals, setVals] = React.useState(null);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    fetch("/api/config/thresholds").then(r => r.json()).then(setVals).catch(() => {});
  }, []);

  const set = (k, v) => setVals(prev => ({ ...prev, [k]: parseFloat(v) }));

  const save = async () => {
    await fetch("/api/config/thresholds", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(vals),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const reset = async () => {
    const r = await fetch("/api/config/thresholds/reset", { method: "POST" });
    const d = await r.json();
    setVals(d);
  };

  if (!vals) return <div className="card" style={{ padding: 16 }}>loading…</div>;

  const row = (label, warnKey, errKey, unit = "%") => (
    <tr key={warnKey} style={{ borderTop: "1px solid var(--border)" }}>
      <td style={{ padding: "5px 8px 5px 0", fontSize: 12 }}>{label}</td>
      <td style={{ padding: "5px 4px" }}>
        <input type="number" value={vals[warnKey]} onChange={e => set(warnKey, e.target.value)}
          style={{ width: 60, textAlign: "right" }} /> {unit}
      </td>
      <td style={{ padding: "5px 4px" }}>
        <input type="number" value={vals[errKey]} onChange={e => set(errKey, e.target.value)}
          style={{ width: 60, textAlign: "right" }} /> {unit}
      </td>
    </tr>
  );

  return (
    <div className="card" style={{ padding: 16, maxWidth: 480 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Alert Thresholds</h3>
        <button className="btn" onClick={onClose}>close</button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", fontSize: 11, color: "var(--fg-2)", paddingBottom: 4 }}>metric</th>
            <th style={{ textAlign: "center", fontSize: 11, color: "var(--warn)", paddingBottom: 4 }}>warn</th>
            <th style={{ textAlign: "center", fontSize: 11, color: "var(--err)", paddingBottom: 4 }}>error</th>
          </tr>
        </thead>
        <tbody>
          {row("CPU util", "cpu_warn", "cpu_err")}
          {row("Memory util", "mem_warn", "mem_err")}
          {row("Disk usage", "disk_warn", "disk_err")}
          {row("Temperature", "temp_warn", "temp_err", "°C")}
          {row("PSI memory", "psi_mem_warn", "psi_mem_err")}
          {row("PSI I/O", "psi_io_warn", "psi_io_err")}
          {row("GPU util", "gpu_warn", "gpu_err")}
          {row("Power draw", "power_warn", "power_err", "W")}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 12, gap: 8 }}>
        <button className="btn" onClick={save}>{saved ? "saved!" : "save"}</button>
        <button className="btn" onClick={reset} style={{ color: "var(--fg-2)" }}>reset defaults</button>
      </div>
    </div>
  );
}

// ───── overview ─────
function Overview({ meta, sys, jetson }) {
  const [cpuH, pushCpu] = useSeries(120);
  const [memH, pushMem] = useSeries(120);
  const [netH, pushNet] = useSeries(120);
  const [gpuH, pushGpu] = useSeries(120);
  const [powH, pushPow] = useSeries(120);
  const [tempH, pushTemp] = useSeries(120);

  useEffect(() => {
    if (!sys) return;
    pushCpu(sys.cpu?.total ?? 0);
    const memPct = sys.mem?.total ? 100 * sys.mem.used / sys.mem.total : 0;
    pushMem(memPct);
    pushNet((sys.net?.rx_bps || 0) + (sys.net?.tx_bps || 0));
  }, [sys]);

  useEffect(() => {
    if (!jetson) return;
    pushGpu(jetson.gpu_load || 0);
    pushPow(jetson.power_w || 0);
    pushTemp(jetson.soc_temp || 0);
  }, [jetson]);

  const [showThresh, setShowThresh] = React.useState(false);
  const memPct = sys?.mem?.total ? 100 * sys.mem.used / sys.mem.total : 0;
  const hottestDisk = (sys?.disks || []).reduce((a, b) => (b.pct > (a?.pct ?? 0) ? b : a), null);
  const perCore = sys?.cpu?.per_core || [];

  return (
    <div className="col-stack">
      {showThresh && <ThresholdSettings onClose={() => setShowThresh(false)} />}
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: -8 }}>
        <button className="btn" title="Alert thresholds" onClick={() => setShowThresh(v => !v)}>
          ⚙ thresholds
        </button>
      </div>
      <div className="grid kpi">
        <div className="card">
          <h3>CPU · {perCore.length || 0} cores</h3>
          <div className="big">{fmtPct(sys?.cpu?.total)}</div>
          <div className="sub">load {(sys?.cpu?.load || []).map(v => v.toFixed(2)).join(" ")}</div>
          <div className="chart"><Spark data={cpuH} min={0} max={100} /></div>
        </div>
        <div className="card">
          <h3>Memory</h3>
          <div className="big">{fmtPct(memPct)}</div>
          <div className="sub">{fmtBytes(sys?.mem?.used)} / {fmtBytes(sys?.mem?.total)}</div>
          <div className="chart"><Spark data={memH} min={0} max={100} tone={memPct > 85 ? "warn" : "accent"} /></div>
        </div>
        <div className="card">
          <h3>Disk · {hottestDisk?.mount || "—"}</h3>
          <div className="big">{fmtPct(hottestDisk?.pct)}</div>
          <div className="sub">{fmtBytes(hottestDisk?.used)} / {fmtBytes(hottestDisk?.total)}</div>
          {(sys?.disks || []).length > 1 && (
            <div className="sub" style={{ marginTop: 6 }}>
              {sys.disks.map(d => `${d.mount} ${d.pct}%`).join("  ·  ")}
            </div>
          )}
        </div>
        <div className="card">
          <h3>Network</h3>
          <div className="big">{fmtBps((sys?.net?.rx_bps || 0) + (sys?.net?.tx_bps || 0))}</div>
          <div className="sub">↓ {fmtBps(sys?.net?.rx_bps)} · ↑ {fmtBps(sys?.net?.tx_bps)}</div>
          <div className="chart"><Spark data={netH} tone="info" /></div>
        </div>

        {meta?.host === "jetson" && <>
          <div className="card">
            <h3>GPU</h3>
            <div className="big">{fmtPct(jetson?.gpu_load)}</div>
            <div className="sub">{jetson?.gpu_ram_total ? `${fmtBytes(jetson.gpu_ram_used)} / ${fmtBytes(jetson.gpu_ram_total)}` : "—"}</div>
            <div className="chart"><Spark data={gpuH} min={0} max={100} tone="info" /></div>
          </div>
          <div className="card">
            <h3>Power</h3>
            <div className="big">{jetson?.power_w != null ? `${jetson.power_w.toFixed(1)}W` : "—"}</div>
            <div className="sub">mode {jetson?.power_mode || "—"}</div>
            <div className="chart"><Spark data={powH} tone="warn" /></div>
          </div>
          <div className="card">
            <h3>SoC temp</h3>
            <div className="big">{jetson?.soc_temp != null ? `${jetson.soc_temp.toFixed(1)}°C` : "—"}</div>
            <div className="sub">fan {fmtPct(jetson?.fan_pct)}{jetson?.emc_load ? ` · emc ${fmtPct(jetson.emc_load)}` : ""}</div>
            <div className="chart"><Spark data={tempH} tone={jetson?.soc_temp > 75 ? "err" : jetson?.soc_temp > 65 ? "warn" : "accent"} /></div>
          </div>
        </>}
      </div>

      {perCore.length > 0 && (
        <div className="card">
          <h3>CPU Cores · per-core utilization</h3>
          <div className="core-grid">
            {perCore.map((pct, i) => (
              <div key={i} className="core-bar-wrap">
                <div className="core-bar-label">C{i}</div>
                <div className="core-bar-track">
                  <div
                    className="core-bar-fill"
                    style={{
                      height: `${Math.max(2, pct || 0)}%`,
                      background: (pct || 0) > 90 ? "var(--err)" : (pct || 0) > 70 ? "var(--warn)" : "var(--accent)",
                    }}
                  />
                </div>
                <div className="core-bar-pct">{(pct || 0).toFixed(0)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ───── jetson detail ─────
function JetsonDetail({ meta, jetson }) {
  const [gpuH, pushGpu] = useSeries(120);
  const [powH, pushPow] = useSeries(120);
  const [emcH, pushEmc] = useSeries(120);

  useEffect(() => {
    if (!jetson) return;
    pushGpu(jetson.gpu_load || 0);
    pushPow(jetson.power_w || 0);
    if (jetson.emc_load != null) pushEmc(jetson.emc_load);
  }, [jetson]);

  if (meta?.host !== "jetson") return (
    <div className="card"><div className="empty">Jetson metrics not available on this host.</div></div>
  );

  const temps = jetson?.temps || {};
  const powerRails = jetson?.power_rails || {};
  const engines = jetson?.engines || {};
  const swapPct = jetson?.swap_total ? 100 * (jetson.swap_used || 0) / jetson.swap_total : null;

  return (
    <div className="col-stack">
      <div className="grid kpi">
        <div className="card">
          <h3>GPU Load</h3>
          <div className="big">{fmtPct(jetson?.gpu_load)}</div>
          <div className="sub">VRAM {fmtBytes(jetson?.gpu_ram_used)} / {fmtBytes(jetson?.gpu_ram_total)}</div>
          <div className="chart"><Spark data={gpuH} min={0} max={100} tone="info" /></div>
        </div>
        <div className="card">
          <h3>Total Power</h3>
          <div className="big">{jetson?.power_w != null ? `${jetson.power_w.toFixed(1)}W` : "—"}</div>
          <div className="sub">NVP {jetson?.power_mode || "—"} · fan {fmtPct(jetson?.fan_pct)}</div>
          <div className="chart"><Spark data={powH} tone="warn" /></div>
        </div>
        {emcH.length > 0 && (
          <div className="card">
            <h3>EMC Load</h3>
            <div className="big">{fmtPct(jetson?.emc_load)}</div>
            <div className="sub">external memory controller</div>
            <div className="chart"><Spark data={emcH} min={0} max={100} tone="accent" /></div>
          </div>
        )}
        {swapPct != null && (
          <div className="card">
            <h3>Swap</h3>
            <div className="big">{fmtPct(swapPct)}</div>
            <div className="sub">{fmtBytes(jetson.swap_used)} / {fmtBytes(jetson.swap_total)}</div>
            <div className="chart"><Spark data={[swapPct]} min={0} max={100} tone={swapPct > 80 ? "err" : swapPct > 50 ? "warn" : "accent"} /></div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Thermal Sensors</h3>
        {Object.keys(temps).length === 0
          ? <div className="empty">no thermal data yet</div>
          : (
            <div className="sensor-grid">
              {Object.entries(temps).map(([k, v]) => (
                <div key={k} className="sensor-chip">
                  <div className="sensor-name">{k}</div>
                  <div className={`sensor-val ${v > 80 ? "err" : v > 65 ? "warn" : "ok"}`}>
                    {v.toFixed(1)}°C
                  </div>
                </div>
              ))}
            </div>
          )
        }
      </div>

      {Object.keys(engines).length > 0 && (
        <div className="card">
          <h3>Engine Utilization</h3>
          <div className="sensor-grid">
            {Object.entries(engines).map(([k, v]) => (
              <div key={k} className="sensor-chip">
                <div className="sensor-name">{k}</div>
                <div className={`sensor-val ${v > 90 ? "err" : v > 70 ? "warn" : "ok"}`}>
                  {fmtPct(v)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.keys(powerRails).length > 0 && (
        <div className="card">
          <h3>Power Rails</h3>
          <div className="kv" style={{ gridTemplateColumns: "160px 1fr" }}>
            {Object.entries(powerRails).map(([k, v]) => (
              <React.Fragment key={k}>
                <span className="k">{k}</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{v.toFixed(3)} W</span>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ───── processes ─────
function Processes({ procs }) {
  const [sort, setSort] = useState({ key: "rss", dir: "desc" });
  const click = (k) => setSort(s => s.key === k ? { key: k, dir: s.dir === "desc" ? "asc" : "desc" } : { key: k, dir: "desc" });
  const sorted = useMemo(() => {
    const arr = [...(procs || [])];
    arr.sort((a, b) => {
      const va = a[sort.key], vb = b[sort.key];
      if (typeof va === "string") return sort.dir === "desc" ? vb.localeCompare(va) : va.localeCompare(vb);
      return sort.dir === "desc" ? (vb ?? 0) - (va ?? 0) : (va ?? 0) - (vb ?? 0);
    });
    return arr.slice(0, 80);
  }, [procs, sort]);
  const cls = (k) => sort.key === k ? `sort-${sort.dir}` : "";
  return (
    <div className="card" style={{ padding: 0 }}>
      <table>
        <thead>
          <tr>
            <th className={cls("pid")} onClick={() => click("pid")}>PID</th>
            <th className={cls("name")} onClick={() => click("name")}>Name</th>
            <th className={"num " + cls("cpu")} onClick={() => click("cpu")}>CPU%</th>
            <th className={"num " + cls("rss")} onClick={() => click("rss")}>RSS</th>
            <th className={"num " + cls("threads")} onClick={() => click("threads")}>Thr</th>
            <th className={"num " + cls("time_plus")} onClick={() => click("time_plus")}>Uptime</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && <tr><td colSpan="7" className="empty">waiting for first tick…</td></tr>}
          {sorted.map(p => (
            <tr key={p.pid} className={p.state === "leak" ? "leak" : ""}>
              <td>{p.pid}</td>
              <td>{p.name}</td>
              <td className="num">{p.cpu?.toFixed(1)}</td>
              <td className="num">{fmtBytes(p.rss)}</td>
              <td className="num">{p.threads}</td>
              <td className="num">{fmtDuration(p.time_plus)}</td>
              <td>{p.state === "leak" ? <span className="chip leak">leak</span> : <span className="chip">{p.state || "ok"}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ───── services ─────
function Services() {
  const [data, err] = usePoll("/api/units?window=24h&limit=200", 15000);
  const [query, setQuery] = useState("");
  const [onlyIssues, setOnlyIssues] = useState(true);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data || []).filter(r => {
      if (onlyIssues && r.status === "ok") return false;
      if (!q) return true;
      return [r.name, r.description, r.detail, r.sample].some(v => (v || "").toLowerCase().includes(q));
    });
  }, [data, query, onlyIssues]);

  return (
    <div className="grid two services-grid">
      <div className="card">
        <h3>Service State</h3>
        <div className="filters">
          <input
            placeholder="filter name or message…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{ flex: 1, minWidth: 260 }}
          />
          <button className="btn secondary" onClick={() => setOnlyIssues(v => !v)}>
            {onlyIssues ? "show all" : "issues only"}
          </button>
          <span style={{ color: "var(--fg-3)", alignSelf: "center", fontFamily: "var(--mono)", fontSize: 11 }}>
            {rows.length}/{(data || []).length} units
          </span>
        </div>
        {err && <div className="empty">failed to load services: {err}</div>}
        {!err && (
          <div className="card" style={{ padding: 0, background: "transparent", border: "none" }}>
            <table>
              <thead>
                <tr>
                  <th>Unit</th>
                  <th>State</th>
                  <th className="num">Err</th>
                  <th className="num">Warn</th>
                  <th className="num">Crash</th>
                  <th>Activity</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan="6" className="empty">no matching units</td></tr>}
                {rows.map(r => (
                  <tr key={r.name}>
                    <td>
                      <div>{r.name}</div>
                      <div className="svc-sub">{r.description}</div>
                    </td>
                    <td><span className={`chip ${r.status}`}>{r.active_state}</span></td>
                    <td className="num">{r.errors}</td>
                    <td className="num">{r.warns}</td>
                    <td className="num">{r.crashes}</td>
                    <td>
                      <div>{r.detail}</div>
                      <div className="svc-sub">{r.sample || r.sub_state}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="card">
        <h3>Service Snapshot</h3>
        <div className="kv">
          <span className="k">problem units</span><span>{(data || []).filter(r => r.status !== "ok").length}</span>
          <span className="k">failed</span><span>{(data || []).filter(r => r.active_state === "failed").length}</span>
          <span className="k">error logs</span><span>{(data || []).reduce((n, r) => n + (r.errors || 0), 0)}</span>
          <span className="k">warn logs</span><span>{(data || []).reduce((n, r) => n + (r.warns || 0), 0)}</span>
          <span className="k">crashes</span><span>{(data || []).reduce((n, r) => n + (r.crashes || 0), 0)}</span>
        </div>
        <div className="diagnose-out" style={{ marginTop: 14 }}>
          {(data || []).slice(0, 6).map(r => (
            <div key={r.name} style={{ marginBottom: 10 }}>
              <b>{r.name}</b> <span className={`chip ${r.status}`} style={{ marginLeft: 8 }}>{r.detail}</span>
              <div style={{ color: "var(--fg-2)" }}>{r.description}</div>
            </div>
          ))}
          {(!data || data.length === 0) && <div>systemd data unavailable on this host</div>}
        </div>
      </div>
    </div>
  );
}

// ───── app focus ─────
function AppFocus({ meta }) {
  const [apps] = usePoll("/api/apps?window=6h", 10000);
  const [selected, setSelected] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [analysisState, setAnalysisState] = useState("idle");
  useEffect(() => {
    if (!selected && apps?.length) setSelected(apps[0].name);
  }, [apps, selected]);
  const [detail] = usePoll(selected ? `/api/apps/${encodeURIComponent(selected)}?window=6h` : null, 10000);
  const rows = apps || [];
  const app = detail?.app || rows.find(r => r.name === selected) || null;
  const rss = (detail?.rss_history?.v || []).map(v => v / (1024 * 1024));
  const flow = detail?.flow?.keys || {};
  const flowStep = detail?.flow?.step_s || meta?.polling?.app_monitor_s || null;
  const cpuFlow = flow.cpu?.v || [];
  const threadsFlow = flow.threads?.v || [];
  const procsFlow = flow.procs?.v || [];
  const errFlow = flow.errors?.v || [];
  const warnFlow = flow.warns?.v || [];
  const crashFlow = flow.crashes?.v || [];
  const rssFlow = (flow.rss?.v || []).map(v => v / (1024 * 1024));
  const eventMax = Math.max(1, ...errFlow, ...warnFlow, ...crashFlow);

  useEffect(() => {
    if (!app) {
      setAnalysis(null);
      setAnalysisState("idle");
      return;
    }
    const ctrl = new AbortController();
    setAnalysisState("loading");
    fetch("/api/diagnose", {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({
        scope: {
          window: "15m",
          pids: app.pid ? [app.pid] : [],
          services: app.service ? [app.service] : [app.label || app.name],
        },
        question: `Analyze the selected app ${app.label || app.name}. What is wrong, what evidence supports it, and what should I do next?`,
      }),
    })
      .then(r => r.json())
      .then(j => {
        if (!ctrl.signal.aborted) {
          setAnalysis(j);
          setAnalysisState("ready");
        }
      })
      .catch(() => {
        if (!ctrl.signal.aborted) {
          setAnalysis(null);
          setAnalysisState("error");
        }
      });
    return () => ctrl.abort();
  }, [app?.name, app?.pid, app?.service, app?.label]);

  return (
    <div className="grid app-focus">
      <div className="card focus-sidebar">
        <h3>Monitored Apps</h3>
        <div className="svc-sub" style={{ marginBottom: 10 }}>
          sampled every {flowStep ? fmtDuration(flowStep) : "—"} · nmon-style app snapshots
        </div>
        <div className="focus-list">
          {rows.length === 0 && <div className="empty">no app-like processes or services detected yet</div>}
          {rows.map(r => (
            <button key={r.name} className={`focus-item ${selected === r.name ? "active" : ""}`} onClick={() => setSelected(r.name)}>
              <div className="focus-item-top">
                <span>{r.label}</span>
                <span className={`chip ${r.status === "leak" ? "leak" : r.status === "err" ? "err" : r.status === "warn" ? "warn" : "ok"}`}>{r.status}</span>
              </div>
              <div className="svc-sub">pid {r.pid || "—"} · rss {fmtBytes(r.rss)} · cpu {fmtPct(r.cpu)}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="focus-main">
        {!app && <div className="card"><div className="empty">pick an app</div></div>}
        {app && <>
          <div className="card">
            <div className="focus-header">
              <div>
                <h2>{app.label}</h2>
                <div className="svc-sub">pid {app.pid || "—"} · {app.service || "no bound unit"} · up {fmtDuration(app.time_plus)}</div>
              </div>
              <div className="focus-badges">
                <span className={`chip ${app.status === "leak" ? "leak" : app.status === "err" ? "err" : app.status === "warn" ? "warn" : "ok"}`}>{app.status}</span>
                {app.slope_mb_min != null && <span className="chip warn">slope {app.slope_mb_min.toFixed(3)} MB/min</span>}
                {app.ttl_oom_s != null && <span className="chip err">ttl {fmtDuration(app.ttl_oom_s)}</span>}
              </div>
            </div>
          </div>
          <div className="grid two">
            <div className="card">
              <h3>Memory Story</h3>
              <div className="big">{app.rss_mb != null ? `${app.rss_mb.toFixed(1)} MB` : fmtBytes(app.rss)}</div>
              <div className="sub">delta 6h {app.delta_6h_mb != null ? `${app.delta_6h_mb.toFixed(1)} MB` : "—"} · restarts {app.restarts || 0}</div>
              <div className="chart tall"><Spark data={rssFlow.length ? rssFlow : rss} tone={app.status === "leak" ? "warn" : "accent"} /></div>
            </div>
            <div className="card">
              <h3>App Health</h3>
              <div className="kv">
                <span className="k">cpu</span><span>{fmtPct(app.cpu)}</span>
                <span className="k">rss</span><span>{fmtBytes(app.rss)}</span>
                <span className="k">threads</span><span>{app.threads ?? "—"}</span>
                <span className="k">errors</span><span>{app.errors}</span>
                <span className="k">warns</span><span>{app.warns}</span>
                <span className="k">crashes</span><span>{app.crashes}</span>
              </div>
            </div>
          </div>
          <div className="grid three">
            <div className="card">
              <h3>CPU Flow</h3>
              <div className="big">{fmtPct(app.cpu)}</div>
              <div className="sub">aggregated app cpu across matching processes</div>
              <div className="chart"><Spark data={cpuFlow} min={0} max={Math.max(100, ...cpuFlow, app.cpu || 0)} tone="info" /></div>
            </div>
            <div className="card">
              <h3>Thread Flow</h3>
              <div className="big">{app.threads ?? "—"}</div>
              <div className="sub">{app.pid ? `pid ${app.pid}` : "aggregated process group"} · {(flow.procs?.v || []).at(-1) || 0} live processes</div>
              <div className="chart"><Spark data={threadsFlow.length ? threadsFlow : procsFlow} max={Math.max(1, ...threadsFlow, ...procsFlow)} /></div>
            </div>
            <div className="card">
              <h3>Incident Flow</h3>
              <div className="big">{(app.errors || 0) + (app.warns || 0) + (app.crashes || 0)}</div>
              <div className="sub">errors {app.errors} · warns {app.warns} · crashes {app.crashes}</div>
              <div className="chart">
                <Spark data={errFlow} tone="err" min={0} max={eventMax} />
                <Spark data={warnFlow} tone="warn" min={0} max={eventMax} />
                <Spark data={crashFlow} tone="info" min={0} max={eventMax} />
              </div>
            </div>
          </div>
          <div className="grid two">
            <div className="card">
              <h3>Selected App Analysis</h3>
              {analysisState === "loading" && <div className="empty">fetching scoped diagnosis…</div>}
              {analysisState === "error" && <div className="empty">failed to analyze selected app</div>}
              {analysisState === "ready" && analysis && <>
                <div className="subtle">{analysis.summary}</div>
                <div className="diagnose-out" style={{ marginTop: 10 }}>
                  <div>{analysis.llm_answer?.text || "(empty)"}</div>
                </div>
                <div style={{ marginTop: 12, color: "var(--fg-2)", fontSize: 11 }}>{analysis.context_digest}</div>
              </>}
              {analysisState === "idle" && <div className="empty">pick an app to analyze</div>}
            </div>
            <div className="card">
              <h3>Recent App Logs</h3>
              <div className="logs compact">
                {(app.recent_logs || []).length === 0 && <div className="empty">no matching app logs</div>}
                {(app.recent_logs || []).map((r, i) => (
                  <div key={i} className="log-row">
                    <span className="ts">{tsToHMS(r.ts)}</span>
                    <span className={`lv ${(r.level || "INFO").toUpperCase()}`}>{(r.level || "INFO").toUpperCase()}</span>
                    <span className="svc">{r.service || "—"}</span>
                    <span className="msg">{r.message}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <h3>Crash & Service State</h3>
              <div className="kv">
                <span className="k">service</span><span>{app.service || "—"}</span>
                <span className="k">active</span><span>{app.active_state || "—"}</span>
                <span className="k">substate</span><span>{app.sub_state || "—"}</span>
                <span className="k">restarts</span><span>{app.restarts || 0}</span>
              </div>
              <div className="diagnose-out" style={{ marginTop: 12 }}>
                {(app.recent_crashes || []).length === 0 && <div>no recent crash events</div>}
                {(app.recent_crashes || []).map((e, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <b>{e.payload?.signal || e.kind}</b> <span style={{ color: "var(--fg-3)" }}>{tsToHMS(e.ts)}</span>
                    <div style={{ color: "var(--fg-2)" }}>{e.payload?.message || "—"}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>}
      </div>
    </div>
  );
}

function NmonView({ meta }) {
  const [apps] = usePoll("/api/apps?window=24h", 10000);
  const [selected, setSelected] = useState("");
  const [cfg, setCfg] = useState({ system_s: "", process_s: "", app_monitor_s: "" });
  const [livePolling, setLivePolling] = useState(meta?.polling || null);
  const [saveState, setSaveState] = useState("idle");

  const [pinnedApps, setPinnedApps] = useState([]);
  const [newApp, setNewApp] = useState("");
  const [pinState, setPinState] = useState("idle");

  useEffect(() => {
    fetch("/api/config/apps").then(r => r.json()).then(d => setPinnedApps(d.pinned || [])).catch(() => {});
  }, []);

  const addApp = async () => {
    const name = newApp.trim();
    if (!name) return;
    setPinState("saving");
    try {
      const res = await fetch("/api/config/apps", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const d = await res.json();
      setPinnedApps(d.pinned || []);
      setNewApp("");
      setPinState("saved");
      setTimeout(() => setPinState("idle"), 1500);
    } catch { setPinState("error"); }
  };

  const removeApp = async (name) => {
    const res = await fetch(`/api/config/apps/${encodeURIComponent(name)}`, { method: "DELETE" });
    const d = await res.json();
    setPinnedApps(d.pinned || []);
  };

  const appOptions = useMemo(() => {
    const out = [];
    const seen = new Set();
    (apps || []).forEach((app) => {
      if (!app?.name || seen.has(app.name)) return;
      seen.add(app.name);
      out.push(app);
    });
    (pinnedApps || []).forEach((name) => {
      if (!name || seen.has(name)) return;
      seen.add(name);
      out.push({ name, label: `${name} (pinned)`, status: "ok" });
    });
    return out;
  }, [apps, pinnedApps]);

  useEffect(() => {
    if (!selected && appOptions.length) setSelected(appOptions[0].name);
  }, [appOptions, selected]);
  useEffect(() => {
    if (!meta?.polling) return;
    setLivePolling(meta.polling);
    setCfg({
      system_s: String(meta.polling.system_s ?? ""),
      process_s: String(meta.polling.process_s ?? ""),
      app_monitor_s: String(meta.polling.app_monitor_s ?? ""),
    });
  }, [meta?.polling?.system_s, meta?.polling?.process_s, meta?.polling?.app_monitor_s]);

  const [cpuHist] = usePoll("/api/system/history?field=cpu.total&window=6h&step=1m", 15000);
  const [memHist] = usePoll("/api/system/history?field=mem.used&window=6h&step=1m", 15000);
  const [netRxHist] = usePoll("/api/system/history?field=net.rx&window=6h&step=1m", 15000);
  const [netTxHist] = usePoll("/api/system/history?field=net.tx&window=6h&step=1m", 15000);
  const [appHist] = usePoll(selected ? `/api/apps/${encodeURIComponent(selected)}/njmon?window=6h&step=1m` : null, 10000);

  const appCpu = appHist?.app_cpu?.history?.v || [];
  const appRss = (appHist?.app_memory?.history?.v || []).map(v => v / (1024 * 1024));
  const appThreads = appHist?.app_process?.thread_history?.v || [];
  const appIoRead = appHist?.app_io?.read_bps_history?.v || [];
  const appIoWrite = appHist?.app_io?.write_bps_history?.v || [];
  const appNetConn = appHist?.app_network?.connection_history?.v || [];
  const appErrors = appHist?.app_events?.error_history?.v || [];
  const appWarns = appHist?.app_events?.warn_history?.v || [];
  const appCrashes = appHist?.app_events?.crash_history?.v || [];
  const eventMax = Math.max(1, ...appErrors, ...appWarns, ...appCrashes);
  const selectedApp = appOptions.find(a => a.name === selected) || null;
  const selectedIdentity = appHist?.identity || {};
  const latestAppCpu = appHist?.app_cpu?.pct ?? appCpu.at(-1);
  const latestAppRss = appHist?.app_memory?.rss_bytes ?? appHist?.app_memory?.history?.v?.at(-1);
  const latestReadBps = appIoRead.at(-1);
  const latestWriteBps = appIoWrite.at(-1);
  const latestNetConn = appNetConn.at(-1) ?? 0;

  const savePolling = async () => {
    setSaveState("saving");
    try {
      const res = await fetch("/api/config/polling", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          system_s: Number(cfg.system_s),
          process_s: Number(cfg.process_s),
          app_monitor_s: Number(cfg.app_monitor_s),
        }),
      });
      if (!res.ok) throw new Error("save failed");
      const out = await res.json();
      setLivePolling(out.polling);
      setCfg({
        system_s: String(out.polling.system_s ?? ""),
        process_s: String(out.polling.process_s ?? ""),
        app_monitor_s: String(out.polling.app_monitor_s ?? ""),
      });
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 1500);
    } catch {
      setSaveState("error");
    }
  };

  return (
    <div className="col-stack">
      <div className="grid two">
        <div className="card">
          <h3>NMON Graphs</h3>
          <div className="kv">
            <span className="k">mode</span><span>nmon / njmon style sampled monitoring</span>
            <span className="k">system poll</span><span>{fmtDuration(livePolling?.system_s)}</span>
            <span className="k">process poll</span><span>{fmtDuration(livePolling?.process_s)}</span>
            <span className="k">app poll</span><span>{fmtDuration(livePolling?.app_monitor_s)}</span>
            <span className="k">env vars</span><span>`SH_SYSTEM_TICK_S`, `SH_PROCESS_TICK_S`, `SH_APP_MONITOR_TICK_S`</span>
          </div>
        </div>
        <div className="card">
          <h3>Polling Config</h3>
          <div className="filters">
            <input value={cfg.system_s} onChange={e => setCfg(v => ({ ...v, system_s: e.target.value }))} placeholder="system seconds" />
            <input value={cfg.process_s} onChange={e => setCfg(v => ({ ...v, process_s: e.target.value }))} placeholder="process seconds" />
            <input value={cfg.app_monitor_s} onChange={e => setCfg(v => ({ ...v, app_monitor_s: e.target.value }))} placeholder="app seconds" />
            <button className="btn" onClick={savePolling} disabled={saveState === "saving"}>save</button>
          </div>
          <div className="kv">
            <span className="k">status</span><span>{saveState}</span>
            <span className="k">system env</span><span>SH_SYSTEM_TICK_S</span>
            <span className="k">process env</span><span>SH_PROCESS_TICK_S</span>
            <span className="k">app env</span><span>SH_APP_MONITOR_TICK_S</span>
          </div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>App Select · NJMON view</h3>
          <div className="filters">
            <select value={selected} onChange={e => setSelected(e.target.value)} style={{ flex: 1, minWidth: 200 }}>
              {!appOptions.length && <option value="">no apps detected yet</option>}
              {appOptions.map(a => (
                <option key={a.name} value={a.name}>
                  {a.label}{a.status !== "ok" ? ` [${a.status}]` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="kv" style={{ marginTop: 8 }}>
            <span className="k">selected</span><span>{appHist?.identity?.label || "—"}</span>
            <span className="k">service</span><span>{appHist?.identity?.service || "—"}</span>
            <span className="k">sample step</span><span>{fmtDuration(appHist?.timestamp?.snapshot_seconds)}</span>
            <span className="k">poll step</span><span>{fmtDuration(appHist?.timestamp?.poll_seconds)}</span>
          </div>
        </div>

        <div className="card">
          <h3>Selected App Data</h3>
          {!selected && <div className="empty">select an app to show process metrics</div>}
          {selected && (
            <>
              <div className="focus-header" style={{ marginBottom: 12 }}>
                <div>
                  <h2>{selectedIdentity.label || selectedApp?.label || selected}</h2>
                  <div className="svc-sub">
                    pid {appHist?.app_process?.pid || "—"} · {selectedIdentity.service || "no service"} · sampled {fmtDuration(appHist?.timestamp?.snapshot_seconds)}
                  </div>
                </div>
                <span className={`chip ${selectedApp?.status === "leak" ? "leak" : selectedApp?.status === "err" ? "err" : selectedApp?.status === "warn" ? "warn" : "ok"}`}>
                  {selectedApp?.status || "ok"}
                </span>
              </div>
              <div className="kv" style={{ marginTop: 12 }}>
                <span className="k">cpu</span><span>{fmtPct(latestAppCpu)}</span>
                <span className="k">rss</span><span>{fmtBytes(latestAppRss)}</span>
                <span className="k">threads</span><span>{appHist?.app_process?.threads ?? "—"}</span>
                <span className="k">processes</span><span>{appHist?.app_process?.process_count ?? "—"}</span>
                <span className="k">io read</span><span>{fmtBps(latestReadBps)}</span>
                <span className="k">io write</span><span>{fmtBps(latestWriteBps)}</span>
                <span className="k">connections</span><span>{latestNetConn}</span>
                <span className="k">events</span><span>{appHist?.app_events?.errors || 0} err · {appHist?.app_events?.warns || 0} warn · {appHist?.app_events?.crashes || 0} crash</span>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Pinned Apps · always monitor</h3>
        <div className="filters">
          <input
            placeholder="app name to pin…"
            value={newApp}
            onChange={e => setNewApp(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addApp()}
            style={{ flex: 1 }}
          />
          <button className="btn" onClick={addApp} disabled={pinState === "saving"}>
            {pinState === "saving" ? "…" : pinState === "saved" ? "✓" : "pin"}
          </button>
        </div>
        <div className="pin-list">
          {pinnedApps.length === 0 && <div className="empty" style={{ padding: "10px 0" }}>no pinned apps — auto-discovery active</div>}
          {pinnedApps.map(a => (
            <div key={a} className="pin-item">
              <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{a}</span>
              <button
                className="btn secondary"
                style={{ padding: "2px 8px", fontSize: 12 }}
                onClick={() => removeApp(a)}
              >×</button>
            </div>
          ))}
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>Host CPU 6h</h3>
          <div className="big">{fmtPct((cpuHist?.v || []).at(-1))}</div>
          <div className="chart tall"><Spark data={cpuHist?.v || []} min={0} max={100} tone="info" /></div>
        </div>
        <div className="card">
          <h3>Host Memory 6h</h3>
          <div className="big">{fmtBytes((memHist?.v || []).at(-1))}</div>
          <div className="chart tall"><Spark data={(memHist?.v || []).map(v => v / (1024 * 1024))} tone="accent" /></div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>Host Network RX 6h</h3>
          <div className="big">{fmtBps((netRxHist?.v || []).at(-1))}</div>
          <div className="chart tall"><Spark data={netRxHist?.v || []} tone="info" /></div>
        </div>
        <div className="card">
          <h3>Host Network TX 6h</h3>
          <div className="big">{fmtBps((netTxHist?.v || []).at(-1))}</div>
          <div className="chart tall"><Spark data={netTxHist?.v || []} tone="warn" /></div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>App CPU / RSS</h3>
          <div className="nmon-dual-chart">
            <div>
              <div className="sub">cpu%</div>
              <div className="chart"><Spark data={appCpu} min={0} max={Math.max(100, ...appCpu)} tone="info" /></div>
            </div>
            <div>
              <div className="sub">rss MB</div>
              <div className="chart"><Spark data={appRss} tone="accent" /></div>
            </div>
          </div>
        </div>
        <div className="card">
          <h3>App Threads / Events</h3>
          <div className="nmon-dual-chart">
            <div>
              <div className="sub">threads</div>
              <div className="chart"><Spark data={appThreads} max={Math.max(1, ...appThreads)} tone="accent" /></div>
            </div>
            <div>
              <div className="sub">errors / warns / crashes</div>
              <div className="chart">
                <Spark data={appErrors} tone="err" min={0} max={eventMax} />
                <Spark data={appWarns} tone="warn" min={0} max={eventMax} />
                <Spark data={appCrashes} tone="info" min={0} max={eventMax} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>App IO Read / Write</h3>
          <div className="nmon-dual-chart">
            <div>
              <div className="sub">read bytes/s</div>
              <div className="chart"><Spark data={appIoRead} tone="info" /></div>
            </div>
            <div>
              <div className="sub">write bytes/s</div>
              <div className="chart"><Spark data={appIoWrite} tone="warn" /></div>
            </div>
          </div>
        </div>
        <div className="card">
          <h3>App Network Activity</h3>
          <div className="big">{(appNetConn || []).at(-1) ?? 0}</div>
          <div className="sub">open inet connections for matched app processes</div>
          <div className="chart tall"><Spark data={appNetConn} max={Math.max(1, ...appNetConn)} tone="info" /></div>
        </div>
      </div>
    </div>
  );
}

// ───── briefing ─────
function Briefing() {
  const [data] = usePoll("/api/briefing?window=6h", 15000);
  const featured = data?.featured_incident || {};
  return (
    <div className="col-stack">
      <div className="card hero">
        <div className="hero-main">
          <div className="subtle">Briefing</div>
          <h1>{data?.headline || "Building briefing…"}</h1>
          <div className="svc-sub">{data?.context_digest || "Waiting for enough metrics and logs to summarize."}</div>
        </div>
        <div className="hero-score">
          <div className="big">{data?.health?.score ?? "—"}</div>
          <div className="sub">health / 100</div>
        </div>
      </div>
      <div className="grid two">
        <div className="card">
          <h3>Featured Incident</h3>
          {!featured?.app && <div className="empty">no current incident</div>}
          {featured?.app && <>
            <div className="section-head">{featured.app.label}</div>
            <p>{featured.probable_cause}</p>
            <p>{featured.impact}</p>
            <ol className="steps">
              {(featured.suggested_steps || []).map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </>}
        </div>
        <div className="card">
          <h3>Watched Apps</h3>
          <div className="kv">
            {(data?.apps || []).slice(0, 6).map(a => (
              <React.Fragment key={a.name}>
                <span className="k">{a.label}</span>
                <span>{a.status} · {fmtBytes(a.rss)}</span>
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Critical Log Clusters</h3>
        <div className="grid three">
          {(data?.clusters || []).map((c, i) => (
            <div key={i} className="cluster-card">
              <div className="subtle">{c.count} events · {c.service || "—"}</div>
              <div className="section-head">{c.level || "LOG"}</div>
              <div>{c.sample}</div>
            </div>
          ))}
          {(!data?.clusters || data.clusters.length === 0) && <div className="empty">no critical clusters</div>}
        </div>
      </div>
    </div>
  );
}

// ───── terminal ─────
function TerminalView({ meta, sys, jetson, procs }) {
  const [units] = usePoll("/api/units?window=24h&limit=8", 15000);
  const [logRows] = usePoll("/api/logs?since=300&limit=8", 5000);
  const top = (procs || []).slice(0, 8);
  return (
    <div className="terminal-view">
      <div className="terminal-bar">edge@{meta?.host || "host"}:~$ systemhealth --watch</div>
      <div className="grid two">
        <div className="card terminal-card">
          <div className="terminal-head">CPU / MEM / EDGE</div>
          <pre>{[
            `CPU   ${fmtPct(sys?.cpu?.total)}   load ${(sys?.cpu?.load || []).map(v => (v || 0).toFixed(2)).join(" ")}`,
            `MEM   ${fmtBytes(sys?.mem?.used)} / ${fmtBytes(sys?.mem?.total)}`,
            `NET   rx ${fmtBps(sys?.net?.rx_bps)}   tx ${fmtBps(sys?.net?.tx_bps)}`,
            meta?.host === "jetson" ? `GPU   ${fmtPct(jetson?.gpu_load)}   temp ${jetson?.soc_temp?.toFixed?.(1) || "—"}C` : `DISK  ${(sys?.disks || []).map(d => `${d.mount}:${d.pct}%`).join("  ")}`,
          ].join("\n")}</pre>
        </div>
        <div className="card terminal-card">
          <div className="terminal-head">TOP PROCESSES</div>
          <pre>{top.map(p => `${String(p.pid).padStart(5)}  ${String((p.cpu || 0).toFixed(1)).padStart(5)}  ${fmtBytes(p.rss).padStart(6)}  ${p.name}`).join("\n") || "waiting for first process snapshot…"}</pre>
        </div>
      </div>
      <div className="grid two">
        <div className="card terminal-card">
          <div className="terminal-head">SYSTEMD UNITS</div>
          <pre>{(units || []).slice(0, 8).map(u => `${(u.status || "ok").padEnd(5)}  ${String(u.name).padEnd(28)}  ${u.detail || u.sub_state || "—"}`).join("\n") || "systemd data unavailable"}</pre>
        </div>
        <div className="card terminal-card">
          <div className="terminal-head">LIVE LOG TAIL</div>
          <pre>{(logRows || []).slice(0, 8).map(r => `${tsToHMS(r.ts)} ${(r.level || "INFO").padEnd(5)} ${(r.service || "—").padEnd(18)} ${r.message}`).join("\n") || "waiting for logs…"}</pre>
        </div>
      </div>
    </div>
  );
}

// ───── leak hunter ─────
function LeakHunter() {
  const [apps] = usePoll("/api/apps?window=24h", 10000);
  const rows = (apps || []).filter(a => a.rss || a.errors || a.crashes).slice(0, 12);
  return (
    <div className="col-stack">
      <div className="card">
        <h3>Memory Health Per App</h3>
        <table>
          <thead>
            <tr>
              <th>App</th>
              <th className="num">RSS</th>
              <th className="num">Slope</th>
              <th className="num">TTL→OOM</th>
              <th className="num">Err</th>
              <th className="num">Crash</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan="7" className="empty">no app summaries yet</td></tr>}
            {rows.map(r => (
              <tr key={r.name} className={r.status === "leak" ? "leak" : ""}>
                <td>{r.label}<div className="svc-sub">pid {r.pid || "—"} · restarts {r.restarts || 0}</div></td>
                <td className="num">{fmtBytes(r.rss)}</td>
                <td className="num">{r.slope_mb_min != null ? r.slope_mb_min.toFixed(3) : "—"}</td>
                <td className="num">{r.ttl_oom_s != null ? fmtDuration(r.ttl_oom_s) : "—"}</td>
                <td className="num">{r.errors}</td>
                <td className="num">{r.crashes}</td>
                <td><span className={`chip ${r.status === "leak" ? "leak" : r.status === "err" ? "err" : r.status === "warn" ? "warn" : "ok"}`}>{r.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ───── leaks ─────
function Leaks() {
  const [data] = usePoll("/api/leaks", 5000);
  const rows = (data || []).filter(r => r.slope_mb_min > 0.05);
  return (
    <div className="card" style={{ padding: 0 }}>
      <table>
        <thead>
          <tr>
            <th>PID</th><th>Name</th>
            <th className="num">RSS</th><th className="num">Slope MB/min</th>
            <th className="num">r²</th><th className="num">TTL→OOM</th>
            <th className="num">Δ6h MB</th><th className="num">samples</th><th>flag</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan="9" className="empty">no leaks detected — needs ≥15m of process history</td></tr>}
          {rows.map(r => (
            <tr key={r.pid} className={r.flagged ? "leak" : ""}>
              <td>{r.pid}</td>
              <td>{r.name}</td>
              <td className="num">{r.rss_mb.toFixed(1)} MB</td>
              <td className="num">{r.slope_mb_min.toFixed(3)}</td>
              <td className="num">{r.r2.toFixed(2)}</td>
              <td className="num">{r.ttl_oom_s != null ? fmtDuration(r.ttl_oom_s) : "—"}</td>
              <td className="num">{r.delta_6h_mb != null ? r.delta_6h_mb.toFixed(1) : "—"}</td>
              <td className="num">{r.samples}</td>
              <td>{r.flagged ? <span className="chip leak">LEAK</span> : <span className="chip">watch</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ───── logs ─────
function Logs() {
  const [buffer, setBuffer] = useState([]);
  const [paused, setPaused] = useState(false);
  const [level, setLevel] = useState("");
  const [service, setService] = useState("");
  const [regex, setRegex] = useState("");
  const [window, setWindow] = useState("15m");
  const [limit, setLimit] = useState("200");
  const [clusterWindow, setClusterWindow] = useState("15m");
  const [clusterLimit, setClusterLimit] = useState("20");
  const [histWindow, setHistWindow] = useState("1h");
  const [bucket, setBucket] = useState("1m");
  const bufRef = useRef([]);
  useWS("/ws/logs", (env) => {
    if (paused) return;
    const row = env.data;
    bufRef.current.push(row);
    if (bufRef.current.length > 500) bufRef.current.shift();
    setBuffer([...bufRef.current]);
  });

  const queryUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (level) params.set("level", level);
    if (service) params.set("service", service);
    if (regex) params.set("regex", regex);
    if (window) params.set("since", window);
    if (limit) params.set("limit", limit);
    return `/api/logs?${params.toString()}`;
  }, [level, service, regex, window, limit]);

  const clusterUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (clusterWindow) params.set("since", clusterWindow);
    if (clusterLimit) params.set("limit", clusterLimit);
    return `/api/logs/cluster?${params.toString()}`;
  }, [clusterWindow, clusterLimit]);

  const histogramUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (bucket) params.set("bucket", bucket);
    if (histWindow) params.set("window", histWindow);
    return `/api/logs/histogram?${params.toString()}`;
  }, [bucket, histWindow]);

  const [queryRows, queryErr] = usePoll(queryUrl, 5000);
  const [clusters, clusterErr] = usePoll(clusterUrl, 10000);
  const [histRows, histErr] = usePoll(histogramUrl, 15000);

  const rx = useMemo(() => { try { return regex ? new RegExp(regex, "i") : null; } catch { return null; } }, [regex]);
  const filtered = buffer.filter(r => {
    if (level && (r.level || "").toUpperCase() !== level.toUpperCase()) return false;
    if (service && !(r.service || "").includes(service)) return false;
    if (rx && !rx.test(r.message || "")) return false;
    return true;
  }).slice(-300);

  const histBuckets = useMemo(() => {
    const grouped = new Map();
    for (const row of histRows || []) {
      const key = row.bucket;
      const item = grouped.get(key) || { bucket: key, ERROR: 0, WARN: 0, INFO: 0, DEBUG: 0, OTHER: 0 };
      const lvl = (row.level || "INFO").toUpperCase();
      if (["ERR", "ERROR", "CRIT", "FATAL"].includes(lvl)) item.ERROR += row.count || 0;
      else if (lvl === "WARN") item.WARN += row.count || 0;
      else if (lvl === "INFO" || lvl === "NOTICE") item.INFO += row.count || 0;
      else if (lvl === "DEBUG") item.DEBUG += row.count || 0;
      else item.OTHER += row.count || 0;
      grouped.set(key, item);
    }
    return Array.from(grouped.values()).sort((a, b) => a.bucket.localeCompare(b.bucket));
  }, [histRows]);

  const querySummary = useMemo(() => {
    const rows = queryRows || [];
    const summary = { total: rows.length, error: 0, warn: 0, services: new Set() };
    for (const row of rows) {
      const lvl = (row.level || "").toUpperCase();
      if (["ERR", "ERROR", "CRIT", "FATAL"].includes(lvl)) summary.error += 1;
      if (lvl === "WARN") summary.warn += 1;
      if (row.service) summary.services.add(row.service);
    }
    return { ...summary, services: summary.services.size };
  }, [queryRows]);

  return (
    <div className="col-stack">
      <div className="filters">
        <select value={level} onChange={e => setLevel(e.target.value)}>
          <option value="">all levels</option>
          <option value="ERR">ERR</option>
          <option value="WARN">WARN</option>
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
        </select>
        <input placeholder="service (exact for history, contains for live)…" value={service} onChange={e => setService(e.target.value)} />
        <input placeholder="regex" value={regex} onChange={e => setRegex(e.target.value)} style={{ minWidth: 220 }} />
        <select value={window} onChange={e => setWindow(e.target.value)}>
          {["1m", "5m", "15m", "1h", "6h", "24h"].map(s => <option key={s} value={s}>history {s}</option>)}
        </select>
        <select value={limit} onChange={e => setLimit(e.target.value)}>
          {["50", "100", "200", "500", "1000"].map(s => <option key={s} value={s}>limit {s}</option>)}
        </select>
        <button className="btn secondary" onClick={() => setPaused(p => !p)}>{paused ? "▶ resume" : "⏸ pause"}</button>
        <button className="btn secondary" onClick={() => { bufRef.current = []; setBuffer([]); }}>clear</button>
        <span style={{ color: "var(--fg-3)", alignSelf: "center", fontFamily: "var(--mono)", fontSize: 11 }}>{filtered.length}/{buffer.length} rows</span>
      </div>

      <div className="grid three log-summary-grid">
        <div className="card">
          <h3>Historical Search</h3>
          <div className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
            <span className="k">rows</span><span>{querySummary.total}</span>
            <span className="k">errors</span><span className={querySummary.error ? "chip err" : "chip ok"}>{querySummary.error}</span>
            <span className="k">warns</span><span className={querySummary.warn ? "chip warn" : "chip ok"}>{querySummary.warn}</span>
            <span className="k">services</span><span>{querySummary.services}</span>
          </div>
          {queryErr && <div className="svc-sub" style={{ color: "var(--err)", marginTop: 10 }}>{queryErr}</div>}
        </div>
        <div className="card">
          <h3>Error Clusters</h3>
          <div className="filters" style={{ marginBottom: 0 }}>
            <select value={clusterWindow} onChange={e => setClusterWindow(e.target.value)}>
              {["5m", "15m", "1h", "6h", "24h"].map(s => <option key={s} value={s}>last {s}</option>)}
            </select>
            <select value={clusterLimit} onChange={e => setClusterLimit(e.target.value)}>
              {["10", "20", "40", "80"].map(s => <option key={s} value={s}>top {s}</option>)}
            </select>
          </div>
          <div className="svc-sub">{(clusters || []).length} grouped signatures</div>
          {clusterErr && <div className="svc-sub" style={{ color: "var(--err)" }}>{clusterErr}</div>}
        </div>
        <div className="card">
          <h3>Histogram</h3>
          <div className="filters" style={{ marginBottom: 0 }}>
            <select value={histWindow} onChange={e => setHistWindow(e.target.value)}>
              {["15m", "1h", "6h", "24h"].map(s => <option key={s} value={s}>window {s}</option>)}
            </select>
            <select value={bucket} onChange={e => setBucket(e.target.value)}>
              {["1m", "5m", "1h"].map(s => <option key={s} value={s}>bucket {s}</option>)}
            </select>
          </div>
          <div className="svc-sub">{histBuckets.length} time buckets</div>
          {histErr && <div className="svc-sub" style={{ color: "var(--err)" }}>{histErr}</div>}
        </div>
      </div>

      <div className="grid two log-analysis-grid">
        <div className="card">
          <h3>Historical Results</h3>
          <div className="logs">
            {(queryRows || []).length === 0 && <div className="empty">no matching stored log lines</div>}
            {(queryRows || []).map((r, i) => (
              <div key={i} className="log-row">
                <span className="ts">{tsToHMS(r.ts)}</span>
                <span className={`lv ${(r.level || "INFO").toUpperCase()}`}>{(r.level || "INFO").toUpperCase()}</span>
                <span className="svc">{r.service || "—"}</span>
                <span className="msg">{r.message}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Clustered Errors</h3>
          <div className="cluster-list">
            {(!clusters || clusters.length === 0) && <div className="empty">no clusters for the selected window</div>}
            {(clusters || []).map((c, i) => (
              <div key={i} className="cluster-card">
                <div className="cluster-top">
                  <span className={`chip ${["ERR", "ERROR", "CRIT", "FATAL"].includes((c.level || "").toUpperCase()) ? "err" : (c.level || "").toUpperCase() === "WARN" ? "warn" : "info"}`}>
                    {c.level || "LOG"}
                  </span>
                  <span className="cluster-meta">{c.count} events</span>
                  <span className="cluster-meta">{c.service || "—"}</span>
                </div>
                <div className="cluster-sample">{c.sample}</div>
                <div className="svc-sub">first {tsToHMS(c.first)} · last {tsToHMS(c.last)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid two log-analysis-grid">
        <div className="card">
          <h3>Log Histogram</h3>
          <table style={{ fontSize: 11 }}>
            <thead>
              <tr>
                <th>Bucket</th>
                <th className="num">Errors</th>
                <th className="num">Warns</th>
                <th className="num">Info</th>
                <th className="num">Debug</th>
                <th className="num">Other</th>
              </tr>
            </thead>
            <tbody>
              {histBuckets.length === 0 && <tr><td colSpan="6" className="empty">no histogram data</td></tr>}
              {histBuckets.map((row, i) => (
                <tr key={i}>
                  <td>{tsToHMS(row.bucket)}</td>
                  <td className="num">{row.ERROR}</td>
                  <td className="num">{row.WARN}</td>
                  <td className="num">{row.INFO}</td>
                  <td className="num">{row.DEBUG}</td>
                  <td className="num">{row.OTHER}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>Live Tail</h3>
          <div className="logs">
            {filtered.length === 0 && <div className="empty">no matching live log lines</div>}
            {filtered.map((r, i) => (
              <div key={i} className="log-row">
                <span className="ts">{tsToHMS(r.ts)}</span>
                <span className={`lv ${(r.level || "INFO").toUpperCase()}`}>{(r.level || "INFO").toUpperCase()}</span>
                <span className="svc">{r.service || "—"}</span>
                <span className="msg">{r.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ───── diagnose ─────
function Diagnose() {
  const [scope, setScope] = useState("5m");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [out, setOut] = useState(null);
  const [err, setErr] = useState(null);
  const [correlations] = usePoll("/api/correlate?window=300&top=10", 20000);
  const volumeRank = correlations?.volume || [];
  const pairs = correlations?.pairs || [];
  const run = async () => {
    setLoading(true); setErr(null); setOut(null);
    try {
      const r = await fetch("/api/diagnose", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ scope: { window: scope }, question: question || null }),
      });
      const j = await r.json();
      setOut(j);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  };
  return (
    <div className="card">
      <h3>Diagnose · local LLM</h3>
      <div className="filters" style={{ marginBottom: 10 }}>
        <select value={scope} onChange={e => setScope(e.target.value)}>
          {["1m", "5m", "15m", "1h", "6h", "24h"].map(s => <option key={s} value={s}>last {s}</option>)}
        </select>
        <input
          placeholder="optional question (e.g. 'why is RSS climbing?')"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          style={{ flex: 1, minWidth: 280 }}
        />
        <button className="btn" onClick={run} disabled={loading}>{loading ? "running…" : "▸ diagnose now"}</button>
      </div>
      {err && <div className="diagnose-out" style={{ color: "var(--err)" }}>{err}</div>}
      {out && (
        <div className="diagnose-out">
          <h4>summary</h4>
          <div>{out.summary}</div>
          <h4>llm answer <span style={{ color: "var(--fg-3)" }}>({out.llm_answer?.backend || "—"} · {out.latency_ms}ms)</span></h4>
          <div>{out.llm_answer?.text || "(empty)"}</div>
          {out.matches?.length > 0 && <>
            <h4>kb matches</h4>
            {out.matches.map((m, i) => (
              <div key={i} style={{ marginBottom: 6 }}>
                <b>{m.title}</b> <span style={{ color: "var(--fg-3)" }}>score {m.score.toFixed(2)}</span>
                {m.steps?.length > 0 && <ol style={{ margin: "4px 0 0 20px" }}>{m.steps.map((s, j) => <li key={j}>{s}</li>)}</ol>}
              </div>
            ))}
          </>}
          <h4>context digest</h4>
          <div style={{ color: "var(--fg-2)", fontSize: 11 }}>{out.context_digest}</div>
        </div>
      )}
      <div style={{ marginTop: 16 }}>
        <h4 style={{ marginBottom: 6 }}>Metric Correlation · last 5 min window</h4>
        <div className="grid two" style={{ gap: 12 }}>
          <div className="card" style={{ padding: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 12 }}>Volume Rank · % change vs baseline</div>
            {volumeRank.length === 0
              ? <div className="empty">collecting baseline…</div>
              : <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", paddingBottom: 4, color: "var(--fg-2)" }}>metric</th>
                    <th style={{ textAlign: "right", color: "var(--fg-2)" }}>baseline</th>
                    <th style={{ textAlign: "right", color: "var(--fg-2)" }}>incident</th>
                    <th style={{ textAlign: "right", color: "var(--fg-2)" }}>Δ%</th>
                  </tr></thead>
                  <tbody>{volumeRank.slice(0, 8).map((r, i) => (
                    <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "3px 0" }}>{r.metric}</td>
                      <td style={{ textAlign: "right", color: "var(--fg-2)" }}>{r.baseline_mean}</td>
                      <td style={{ textAlign: "right" }}>{r.incident_mean}</td>
                      <td style={{ textAlign: "right", color: Math.abs(r.delta_pct) > 20 ? "var(--err)" : "var(--warn)" }}>
                        {r.delta_pct > 0 ? "+" : ""}{r.delta_pct}%
                      </td>
                    </tr>
                  ))}</tbody>
                </table>
            }
          </div>
          <div className="card" style={{ padding: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 12 }}>Correlated Pairs · |r| &gt; 0.6</div>
            {pairs.length === 0
              ? <div className="empty">no strong correlations</div>
              : <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", paddingBottom: 4, color: "var(--fg-2)" }}>metric A</th>
                    <th style={{ textAlign: "left", color: "var(--fg-2)" }}>metric B</th>
                    <th style={{ textAlign: "right", color: "var(--fg-2)" }}>|r|</th>
                  </tr></thead>
                  <tbody>{pairs.slice(0, 8).map((p, i) => (
                    <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "3px 0" }}>{p.a}</td>
                      <td>{p.b}</td>
                      <td style={{ textAlign: "right", color: p.abs_r > 0.9 ? "var(--err)" : "var(--warn)" }}>{p.r}</td>
                    </tr>
                  ))}</tbody>
                </table>
            }
          </div>
        </div>
      </div>
    </div>
  );
}

// ───── crashes ─────
function Crashes() {
  const [data] = usePoll("/api/crashes?window=24h", 10000);
  const counts = data?.counts || {};
  const recent = data?.events_24h || [];
  return (
    <div className="grid two">
      <div className="card">
        <h3>Crashes · last 24h</h3>
        {Object.keys(counts).length === 0 ? <div className="empty">no crashes — clean</div> :
          <div className="kv">
            {Object.entries(counts).map(([k, v]) => <React.Fragment key={k}><span className="k">{k}</span><span>{v}</span></React.Fragment>)}
          </div>
        }
      </div>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Time</th><th>Signal</th><th>Unit</th><th>Message</th></tr></thead>
          <tbody>
            {recent.length === 0 && <tr><td colSpan="4" className="empty">none</td></tr>}
            {recent.slice(0, 30).map((e, i) => (
              <tr key={i}>
                <td>{tsToHMS(e.ts)}</td>
                <td><span className="chip err">{e.payload?.signal}</span></td>
                <td>{e.payload?.unit || "—"}</td>
                <td style={{ color: "var(--fg-2)" }}>{e.payload?.message?.slice(0, 80)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ───── agent chat panel ─────
function AgentChat({ open, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [scope, setScope] = useState("5m");
  const bottomRef = useRef(null);

  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    const userMsg = { role: "user", content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: next, scope: { window: scope } }),
      });
      const j = await r.json();
      setMessages(m => [...m, { role: "assistant", content: j.answer || "(empty)", latency_ms: j.latency_ms, backend: j.backend }]);
    } catch (e) {
      setMessages(m => [...m, { role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const onKey = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };

  const clear = () => setMessages([]);

  if (!open) return null;

  return (
    <div style={{
      position: "fixed", top: 0, right: 0, bottom: 0, width: 340,
      background: "var(--paper)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column", zIndex: 200,
      boxShadow: "-4px 0 16px rgba(0,0,0,0.15)",
    }}>
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 13, flex: 1 }}>Agent Chat</span>
        <select value={scope} onChange={e => setScope(e.target.value)} style={{ fontSize: 11, padding: "2px 4px" }}>
          {["1m","5m","15m","1h","6h","24h"].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="btn" onClick={clear} style={{ fontSize: 11, padding: "2px 8px" }}>clear</button>
        <button className="btn" onClick={onClose} style={{ fontSize: 11, padding: "2px 8px" }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--fg-3)", fontSize: 12, textAlign: "center", marginTop: 40 }}>
            Ask anything about the system.<br/>
            <span style={{ fontSize: 11 }}>e.g. "why is memory climbing?" or "what's using the most CPU?"</span>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "90%",
          }}>
            <div style={{
              padding: "8px 11px",
              borderRadius: m.role === "user" ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
              background: m.role === "user" ? "var(--teal)" : "var(--bg-2, #f0f0f0)",
              color: m.role === "user" ? "#fff" : "var(--ink)",
              fontSize: 12, lineHeight: 1.5,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {m.content}
            </div>
            {m.latency_ms && (
              <div style={{ fontSize: 10, color: "var(--fg-3)", textAlign: m.role === "assistant" ? "left" : "right", marginTop: 2 }}>
                {m.backend} · {m.latency_ms}ms
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: "flex-start", padding: "8px 11px", borderRadius: "12px 12px 12px 2px",
            background: "var(--bg-2, #f0f0f0)", fontSize: 12, color: "var(--fg-2)" }}>
            thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: "10px 12px", borderTop: "1px solid var(--border)", display: "flex", gap: 6 }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask the agent… (Enter to send)"
          rows={2}
          style={{ flex: 1, resize: "none", fontSize: 12, padding: "6px 8px",
            border: "1px solid var(--border)", borderRadius: 6, fontFamily: "inherit" }}
        />
        <button className="btn" onClick={send} disabled={loading || !input.trim()}
          style={{ alignSelf: "flex-end", padding: "6px 12px" }}>
          ↑
        </button>
      </div>
    </div>
  );
}

// ───── app ─────
function App() {
  const [meta, setMeta] = useState(null);
  const [sys, setSys] = useState(null);
  const [jetson, setJetson] = useState(null);
  const [procs, setProcs] = useState(null);
  const [health, setHealth] = useState(null);
  const [tab, setTab] = useState("overview");
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    fetch("/api/meta").then(r => r.json()).then(setMeta).catch(() => {});
    fetch("/api/health").then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  const sysStatus = useWS("/ws/system", env => setSys(env.data));
  useWS("/ws/processes", env => setProcs(env.data?.procs));
  useWS("/ws/jetson", env => setJetson(env.data));
  useWS("/ws/health", env => setHealth(env.data));

  return (
    <div className="app" style={{ marginRight: chatOpen ? 340 : 0, transition: "margin-right 0.2s" }}>
      <TopBar meta={meta} health={health} wsStatus={sysStatus} />
      <div className="tabs">
        {(meta?.host === "jetson"
          ? ["health", "overview", "jetson", "nmon", "focus", "terminal", "briefing", "hunter", "processes", "services", "leaks", "logs", "crashes", "diagnose"]
          : ["health", "overview", "nmon", "focus", "terminal", "briefing", "hunter", "processes", "services", "leaks", "logs", "crashes", "diagnose"]
        ).map(t =>
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        )}
        <div style={{ flex: 1 }} />
        <button
          className="btn"
          onClick={() => setChatOpen(v => !v)}
          style={{ alignSelf: "center", marginRight: 8, background: chatOpen ? "var(--teal)" : undefined, color: chatOpen ? "#fff" : undefined }}
        >
          💬 agent
        </button>
        <a href="/SystemHealth%20Wireframes.html" style={{ alignSelf: "center", padding: "0 14px", color: "var(--fg-3)", fontSize: 12 }}>wireframes →</a>
      </div>
      <div className="content">
        {tab === "health" && <HealthView meta={meta} sys={sys} jetson={jetson} procs={procs} health={health} />}
        {tab === "overview" && <Overview meta={meta} sys={sys} jetson={jetson} />}
        {tab === "jetson" && <JetsonDetail meta={meta} jetson={jetson} />}
        {tab === "nmon" && <NmonView meta={meta} />}
        {tab === "focus" && <AppFocus meta={meta} />}
        {tab === "terminal" && <TerminalView meta={meta} sys={sys} jetson={jetson} procs={procs} />}
        {tab === "briefing" && <Briefing />}
        {tab === "hunter" && <LeakHunter />}
        {tab === "processes" && <Processes procs={procs} />}
        {tab === "services" && <Services />}
        {tab === "leaks" && <Leaks />}
        {tab === "logs" && <Logs />}
        {tab === "crashes" && <Crashes />}
        {tab === "diagnose" && <Diagnose />}
      </div>
      <AgentChat open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
