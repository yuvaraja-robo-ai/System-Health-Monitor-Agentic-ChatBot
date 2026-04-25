/* global React */
// Shared low-fi wireframe primitives.

const { useMemo } = React;

// --- deterministic pseudo-random so layouts don't jitter on re-render
function seedRand(seed) {
  let s = seed | 0 || 1;
  return () => {
    s = (s * 1664525 + 1013904223) | 0;
    return ((s >>> 0) % 100000) / 100000;
  };
}

// Hand-drawn-ish polyline sparkline
function Sparkline({ seed = 1, points = 40, height = 60, min = 0.2, max = 0.9, trend = "flat", showAxis = false, className = "" }) {
  const data = useMemo(() => {
    const rand = seedRand(seed);
    const arr = [];
    let v = (min + max) / 2;
    for (let i = 0; i < points; i++) {
      const drift =
        trend === "up" ? 0.012 :
        trend === "down" ? -0.012 :
        trend === "spike" && i > points * 0.7 ? 0.05 :
        trend === "leak" ? 0.008 + i * 0.0004 :
        0;
      v += (rand() - 0.5) * 0.08 + drift;
      v = Math.max(min, Math.min(max, v));
      arr.push(v);
    }
    return arr;
  }, [seed, points, trend, min, max]);

  const W = 200, H = height;
  const step = W / (points - 1);
  const path = data.map((y, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${(H - y * H).toFixed(1)}`).join(" ");
  const fillPath = path + ` L ${W} ${H} L 0 ${H} Z`;

  return (
    <svg className={`spark ${className}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {showAxis && <line className="axis" x1="0" y1={H - 0.5} x2={W} y2={H - 0.5} />}
      <path className="fill" d={fillPath} />
      <path d={path} />
    </svg>
  );
}

// Tiny bar histogram (for things like log volume per minute)
function BarHisto({ seed = 1, bars = 30, height = 40, spikeAt = null, className = "" }) {
  const data = useMemo(() => {
    const rand = seedRand(seed);
    return Array.from({ length: bars }, (_, i) => {
      let v = 0.2 + rand() * 0.5;
      if (spikeAt !== null && Math.abs(i - spikeAt) < 2) v = 0.85 + rand() * 0.15;
      return v;
    });
  }, [seed, bars, spikeAt]);
  const W = 200, H = height;
  const bw = W / bars;
  return (
    <svg className={`spark ${className}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {data.map((v, i) => (
        <rect key={i} x={i * bw + 0.4} y={H - v * H} width={bw - 0.8} height={v * H} fill="currentColor" opacity="0.75" />
      ))}
    </svg>
  );
}

// Bar with fill percentage
function UsageBar({ pct = 50, tone = "ink", label, value }) {
  const toneClass = tone === "teal" ? "teal" : tone === "amber" ? "amber" : tone === "rose" ? "rose" : "";
  return (
    <div>
      {(label || value) && (
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 11, marginBottom: 4 }}>
          <span className="muted">{label}</span>
          <span>{value}</span>
        </div>
      )}
      <div className={`bar ${toneClass}`}>
        <div className="fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
    </div>
  );
}

// Log line
function LogLine({ ts, lvl = "INFO", svc, msg, tone }) {
  const color =
    lvl === "ERR"  || lvl === "ERROR" ? "rose" :
    lvl === "WARN" ? "amber" :
    lvl === "OK"   ? "teal" : "";
  return (
    <div className="log">
      <span className="ts">{ts}</span>{" "}
      <span className={`chip soft ${color}`} style={{ padding: "0 4px", fontSize: 9 }}>{lvl}</span>{" "}
      <span className="svc">{svc}</span>{" "}
      <span style={{ color: tone === "dim" ? "var(--ink-3)" : "var(--ink)" }}>{msg}</span>
    </div>
  );
}

// App row (for app-picker lists)
function AppRow({ on = true, name, pid, cpu, mem, trend = "flat", leak = false }) {
  return (
    <tr>
      <td><span className={`chk ${on ? "on" : ""}`} /></td>
      <td style={{ fontWeight: 500 }}>{name}{leak && <span className="chip rose" style={{ marginLeft: 6, fontSize: 9 }}>LEAK?</span>}</td>
      <td className="muted">{pid}</td>
      <td className="num">{cpu}%</td>
      <td className="num">{mem}</td>
      <td style={{ width: 80 }}>
        <div style={{ height: 16 }}>
          <Sparkline seed={pid} points={24} height={16} trend={trend} className={leak ? "rose" : ""} />
        </div>
      </td>
    </tr>
  );
}

// Host pill (Ubuntu x86 vs Jetson Orin)
function HostPill({ host }) {
  return (
    <span className="chip" style={{ fontFamily: "var(--font-mono)" }}>
      <span className="live-dot" />
      {host === "jetson" ? "jetson-orin-nano · aarch64" : "ubuntu-x86 · 22.04 LTS"}
    </span>
  );
}

// Window/browser chrome for the wireframe
function WireframeFrame({ children, title, meta, host = "jetson" }) {
  return (
    <div className="wf">
      <div className="ticks" />
      <div className="wf-header">
        <div>
          <div className="title-row">
            <h1>{title}</h1>
            <span className="hand" style={{ fontSize: 18, color: "var(--ink-3)" }}>/ wireframe</span>
          </div>
          <div className="sub">{meta}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <HostPill host={host} />
          <span className="chip soft">live · 5m</span>
          <span className="chip soft">▾</span>
        </div>
      </div>
      {children}
    </div>
  );
}

Object.assign(window, {
  seedRand, Sparkline, BarHisto, UsageBar, LogLine, AppRow, HostPill, WireframeFrame,
});
