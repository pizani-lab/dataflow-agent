import { useCallback, useEffect, useRef, useState } from "react";

/* ─── Ollama Status Indicator ─── */

function OllamaStatus() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    checkOllamaHealth()
      .then(data => {
        setStatus(data);
        if (data.error) setError(data.error);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
        <span className="pulse">⏳</span> Verificando Ollama...
      </div>
    );
  }

  const isHealthy = status?.status === "healthy";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{
        width: 8, height: 8, borderRadius: "50%",
        background: isHealthy ? "var(--success)" : "var(--danger)",
      }} />
      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
        Ollama: {isHealthy ? "OK" : "Erro"}
      </span>
      {!isHealthy && error && (
        <div title={error} style={{
          fontSize: 10, color: "var(--danger)", cursor: "help",
          maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}>
          {error}
        </div>
      )}
    </div>
  );
}
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, PieChart, Pie, Cell,
} from "recharts";
import { useApi, uploadFile, triggerPipeline, pausePipeline, resumePipeline, createPipeline, getToken, setToken, clearToken, checkOllamaHealth } from "./hooks/useApi";
import {
  formatDate, formatDuration, formatNumber,
  STATUS_CONFIG, STEP_ICONS,
} from "./utils/formatters";

/* ─── Global Styles ─── */
const THEMES = {
  dark: `
    --bg: #08080c; --surface: #111118; --surface2: #1a1a24;
    --border: #25253a; --fg: #e4e4ec; --muted: #7a7a96;
    --accent: #4f8ff7; --accent-dim: #4f8ff720;
    --success: #34d399; --warning: #fbbf24; --danger: #f87171;
  `,
  light: `
    --bg: #f4f4f8; --surface: #ffffff; --surface2: #eaeaf2;
    --border: #d8d8e8; --fg: #1a1a2e; --muted: #6b6b8a;
    --accent: #3b7de8; --accent-dim: #3b7de818;
    --success: #10b981; --warning: #d97706; --danger: #ef4444;
  `,
};

const globalCSS = (theme) => `
  :root {
    ${THEMES[theme]}
    --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
    --font-mono: 'IBM Plex Mono', 'SF Mono', monospace;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--font-sans); background: var(--bg); color: var(--fg); transition: background 0.2s, color 0.2s; }
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  .fade-up { animation: fadeUp 0.4s ease-out both; }
  .pulse { animation: pulse 2s ease-in-out infinite; }
`;

/* ─── Reusable Components ─── */

function Badge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px", borderRadius: 4,
      fontSize: 11, fontWeight: 600, fontFamily: "var(--font-mono)",
      color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}25`,
    }}>{cfg.label}</span>
  );
}

function MetricCard({ label, value, sub, color = "var(--accent)" }) {
  return (
    <div style={{
      padding: "18px 20px", background: "var(--surface)", borderRadius: 8,
      border: "1px solid var(--border)", flex: 1, minWidth: 160,
    }}>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6, letterSpacing: 0.5, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "var(--font-mono)", color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function QualityGauge({ score }) {
  const sweep = 240;
  const filled = (score / 100) * sweep;
  const empty  = sweep - filled;
  const gap    = 360 - sweep;

  const color =
    score >= 80 ? "var(--success)" :
    score >= 60 ? "var(--warning)" :
    "var(--danger)";

  const label =
    score >= 80 ? "Excelente" :
    score >= 60 ? "Regular"   :
    "Crítico";

  return (
    <div style={{ position: "relative", width: 160, height: 160, flexShrink: 0 }}>
      <PieChart width={160} height={160}>
        <Pie
          data={[{ v: filled }, { v: empty }, { v: gap }]}
          cx={75} cy={80}
          startAngle={210} endAngle={-30}
          innerRadius={52} outerRadius={68}
          dataKey="v" strokeWidth={0} paddingAngle={0}
        >
          <Cell fill={color} />
          <Cell fill="var(--border)" />
          <Cell fill="transparent" />
        </Pie>
      </PieChart>
      <div style={{
        position: "absolute", top: "46%", left: "50%",
        transform: "translate(-50%, -50%)", textAlign: "center", pointerEvents: "none",
      }}>
        <div style={{ fontSize: 30, fontWeight: 700, fontFamily: "var(--font-mono)", color, lineHeight: 1 }}>
          {score}
        </div>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 1, marginTop: 2 }}>
          / 100
        </div>
        <div style={{ fontSize: 10, color, marginTop: 4, fontWeight: 600 }}>
          {label}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ icon, title, desc }) {
  return (
    <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--muted)" }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 13 }}>{desc}</div>
    </div>
  );
}

/* ─── New Pipeline Modal ─── */

function NewPipelineModal({ onClose, onCreated }) {
  const [name, setName]               = useState("");
  const [description, setDescription] = useState("");
  const [cron, setCron]               = useState("");
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await createPipeline({ name, description, schedule_cron: cron });
      onCreated();
    } catch (err) {
      const detail = err.detail || {};
      const msg = detail.name?.[0] || detail.non_field_errors?.[0] || err.message;
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = {
    width: "100%", padding: "9px 12px", background: "var(--surface2)",
    border: "1px solid var(--border)", borderRadius: 6,
    color: "var(--fg)", fontSize: 13, fontFamily: "var(--font-sans)", outline: "none",
  };

  const labelStyle = {
    display: "block", fontSize: 11, color: "var(--muted)",
    marginBottom: 5, textTransform: "uppercase", letterSpacing: 0.5,
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "#00000070",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="fade-up" style={{
        width: 440, padding: "32px 36px", background: "var(--surface)",
        borderRadius: 12, border: "1px solid var(--border)",
      }}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 24 }}>Nova Pipeline</div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Nome *</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Ex: Pipeline de Vendas"
              required
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Descrição</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Descreva o objetivo deste pipeline..."
              rows={3}
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={labelStyle}>Cron Schedule</label>
            <input
              value={cron}
              onChange={e => setCron(e.target.value)}
              placeholder="Ex: 0 6 * * 1  (opcional)"
              style={inputStyle}
            />
          </div>

          {error && (
            <div style={{
              marginBottom: 16, padding: "9px 12px", background: "#ef444415",
              border: "1px solid #ef444430", borderRadius: 6,
              fontSize: 13, color: "var(--danger)",
            }}>
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "9px 18px", background: "transparent",
                border: "1px solid var(--border)", borderRadius: 6,
                color: "var(--muted)", fontSize: 13, cursor: "pointer",
              }}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: "9px 20px", background: "var(--accent)",
                border: "none", borderRadius: 6, color: "#fff",
                fontSize: 13, fontWeight: 600,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Criando..." : "Criar Pipeline"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ─── Pipeline List View ─── */

function PipelineList({ pipelines, onSelect, onPause, onResume }) {
  if (!pipelines?.results?.length) {
    return <EmptyState icon="📦" title="Nenhum pipeline ainda" desc="Crie seu primeiro pipeline para começar." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {pipelines.results.map((p, i) => (
        <div
          key={p.id}
          className="fade-up"
          style={{ animationDelay: `${i * 60}ms`, cursor: "pointer" }}
          onClick={() => onSelect(p.id)}
        >
          <div style={{
            padding: "16px 20px", background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)", display: "flex", justifyContent: "space-between",
            alignItems: "center", transition: "border-color 0.2s",
          }}
            onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
            onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
          >
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{p.name}</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>
                {p.source_count} fonte{p.source_count !== 1 ? "s" : ""} · {p.total_runs} execuç{p.total_runs !== 1 ? "ões" : "ão"} · {formatDate(p.created_at)}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {p.last_run_status && <Badge status={p.last_run_status} />}
              <Badge status={p.status} />
              {p.status === "active" && (
                <button
                  onClick={e => { e.stopPropagation(); onPause(p.id); }}
                  title="Pausar pipeline"
                  style={{
                    padding: "4px 12px", background: "transparent",
                    border: "1px solid var(--warning)", borderRadius: 4,
                    color: "var(--warning)", fontSize: 11, fontWeight: 600,
                    cursor: "pointer", whiteSpace: "nowrap",
                  }}
                >
                  Pausar
                </button>
              )}
              {p.status === "paused" && (
                <button
                  onClick={e => { e.stopPropagation(); onResume(p.id); }}
                  title="Reativar pipeline"
                  style={{
                    padding: "4px 12px", background: "transparent",
                    border: "1px solid var(--success)", borderRadius: 4,
                    color: "var(--success)", fontSize: 11, fontWeight: 600,
                    cursor: "pointer", whiteSpace: "nowrap",
                  }}
                >
                  Reativar
                </button>
              )}
              <span style={{ color: "var(--muted)", fontSize: 18 }}>→</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Run Timeline ─── */

function RunTimeline({ runs, onSelect }) {
  if (!runs?.length) return null;

  const ordered = [...runs].reverse();

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 14, color: "var(--muted)", letterSpacing: 0.5, textTransform: "uppercase" }}>
        Timeline
      </div>
      <div style={{ overflowX: "auto", paddingBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", minWidth: "max-content", gap: 0, position: "relative" }}>
          {ordered.map((run, i) => {
            const cfg = STATUS_CONFIG[run.status] || STATUS_CONFIG.draft;
            return (
              <div key={run.id} style={{ display: "flex", alignItems: "center" }}>
                {/* Dot + label */}
                <div
                  onClick={() => onSelect(run.id)}
                  title={`${run.id.slice(0, 8)} · ${run.status}`}
                  style={{ display: "flex", flexDirection: "column", alignItems: "center", cursor: "pointer", gap: 6 }}
                >
                  <div style={{
                    width: 14, height: 14, borderRadius: "50%",
                    background: cfg.color, border: `2px solid var(--bg)`,
                    boxShadow: `0 0 0 2px ${cfg.color}50`,
                    transition: "transform 0.15s",
                  }}
                    onMouseEnter={e => e.currentTarget.style.transform = "scale(1.4)"}
                    onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}
                  />
                  <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--muted)", textAlign: "center" }}>
                    <div>{run.id.slice(0, 6)}</div>
                    <div style={{ color: cfg.color }}>{run.status}</div>
                  </div>
                </div>
                {/* Connector */}
                {i < ordered.length - 1 && (
                  <div style={{ width: 48, height: 2, background: "var(--border)", flexShrink: 0 }} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ─── WebSocket Hook ─── */

function usePipelineSocket(pipelineId, onUpdate) {
  useEffect(() => {
    if (!pipelineId) return;

    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${location.host}/ws/pipelines/${pipelineId}/`);

    ws.onmessage = (e) => {
      try { onUpdate(JSON.parse(e.data)); } catch {}
    };
    ws.onerror = () => {}; // silencia erros de conexão (Redis offline em dev)

    return () => ws.close();
  }, [pipelineId, onUpdate]);
}

/* ─── Analytics Section (DuckDB) ─── */

const STEP_COLORS = {
  classify: "#4f8ff7",
  quality:  "#34d399",
  plan:     "#fbbf24",
  execute:  "#a78bfa",
  validate: "#f87171",
};

function AnalyticsSection({ pipelineId }) {
  const { data: analytics } = useApi(`/pipelines/${pipelineId}/analytics/`);

  if (!analytics) return null;
  const { quality_trend, step_stats, retention, cost_trend } = analytics;
  if (!quality_trend?.length && !step_stats?.length) return null;

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontSize: 12, fontWeight: 600, marginBottom: 16,
        color: "var(--muted)", letterSpacing: 0.5, textTransform: "uppercase",
      }}>
        Analytics — DuckDB
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>

        {/* Quality Score Trend + Moving Average */}
        {quality_trend.length > 0 && (
          <div style={{
            background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)", padding: 20,
          }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Score de Qualidade
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={quality_trend}>
                <XAxis
                  dataKey="run_num"
                  tick={{ fill: "#7a7a96", fontSize: 10 }}
                  axisLine={false} tickLine={false}
                  tickFormatter={v => `#${v}`}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: "#7a7a96", fontSize: 10 }}
                  axisLine={false} tickLine={false}
                />
                <Tooltip
                  contentStyle={{ background: "#1a1a24", border: "1px solid #25253a", borderRadius: 6, fontSize: 11 }}
                  formatter={(v, n) => [v, n === "quality_score" ? "Score" : "Média Móvel (3)"]}
                />
                <Area
                  type="monotone" dataKey="quality_score"
                  stroke="#4f8ff7" fill="#4f8ff715" strokeWidth={2}
                  dot={{ r: 3, fill: "#4f8ff7" }}
                />
                <Area
                  type="monotone" dataKey="moving_avg"
                  stroke="#34d399" fill="none"
                  strokeWidth={1.5} strokeDasharray="4 2" dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Tokens por Step */}
        {step_stats.length > 0 && (
          <div style={{
            background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)", padding: 20,
          }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Tokens por Step
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={step_stats} layout="vertical">
                <XAxis
                  type="number"
                  tick={{ fill: "#7a7a96", fontSize: 10 }}
                  axisLine={false} tickLine={false}
                />
                <YAxis
                  type="category" dataKey="step"
                  tick={{ fill: "#7a7a96", fontSize: 10 }}
                  axisLine={false} tickLine={false} width={62}
                />
                <Tooltip
                  contentStyle={{ background: "#1a1a24", border: "1px solid #25253a", borderRadius: 6, fontSize: 11 }}
                  formatter={(v, n) => [v, n === "total_tokens" ? "Tokens" : n]}
                />
                <Bar dataKey="total_tokens" radius={[0, 4, 4, 0]}>
                  {step_stats.map((entry) => (
                    <Cell key={entry.step} fill={STEP_COLORS[entry.step] || "#4f8ff7"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Custo por Run */}
        {cost_trend?.length > 0 && (
          <div style={{
            background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)", padding: 20,
          }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Custo Est. por Execução (USD)
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={cost_trend}>
                <XAxis dataKey="run_num" tick={{ fill: "#7a7a96", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `#${v}`} />
                <YAxis tick={{ fill: "#7a7a96", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toFixed(3)}`} />
                <Tooltip
                  contentStyle={{ background: "#1a1a24", border: "1px solid #25253a", borderRadius: 6, fontSize: 11 }}
                  formatter={(v, n) => [`$${v.toFixed(4)}`, n === "cost_usd" ? "Custo" : "Acumulado"]}
                />
                <Area type="monotone" dataKey="cost_usd" stroke="#a78bfa" fill="#a78bfa15" strokeWidth={2} dot={{ r: 3, fill: "#a78bfa" }} />
                <Area type="monotone" dataKey="cumulative_cost_usd" stroke="#a78bfa60" fill="none" strokeWidth={1.5} strokeDasharray="4 2" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Retenção de Dados */}
        {retention.length > 0 && (
          <div style={{
            background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)", padding: 20,
            gridColumn: "1 / -1",
          }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Retenção de Linhas por Execução (%)
            </div>
            <ResponsiveContainer width="100%" height={130}>
              <AreaChart data={retention}>
                <XAxis
                  dataKey="run_num"
                  tick={{ fill: "#7a7a96", fontSize: 10 }}
                  axisLine={false} tickLine={false}
                  tickFormatter={v => `#${v}`}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: "#7a7a96", fontSize: 10 }}
                  axisLine={false} tickLine={false}
                />
                <Tooltip
                  contentStyle={{ background: "#1a1a24", border: "1px solid #25253a", borderRadius: 6, fontSize: 11 }}
                  formatter={(v) => [`${v}%`, "Retenção"]}
                />
                <Area
                  type="monotone" dataKey="retention_pct"
                  stroke="#fbbf24" fill="#fbbf2415" strokeWidth={2}
                  dot={{ r: 3, fill: "#fbbf24" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

      </div>
    </div>
  );
}

/* ─── Pipeline Detail View ─── */

function PipelineDetail({ pipelineId, onBack }) {
  const { data: pipeline, loading, refetch } = useApi(`/pipelines/${pipelineId}/`);
  const { data: stats } = useApi(`/pipelines/${pipelineId}/stats/`);
  const [uploading, setUploading] = useState(false);
  const [selectedRun, setSelectedRun] = useState(null);
  const fileRef = useRef(null);

  const handleUpload = useCallback(async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadFile(pipelineId, file);
      setTimeout(refetch, 1500);
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
    }
  }, [pipelineId, refetch]);

  const handleTrigger = useCallback(async () => {
    try {
      await triggerPipeline(pipelineId);
      setTimeout(refetch, 1500);
    } catch (err) {
      console.error(err);
    }
  }, [pipelineId, refetch]);

  const handleSocketUpdate = useCallback(() => {
    refetch();
  }, [refetch]);

  usePipelineSocket(pipelineId, handleSocketUpdate);

  if (loading || !pipeline) {
    return <div className="pulse" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>Carregando pipeline...</div>;
  }

  if (selectedRun) {
    return <RunDetail runId={selectedRun} onBack={() => setSelectedRun(null)} />;
  }

  // Chart data from recent runs
  const chartData = (pipeline.recent_runs || []).slice().reverse().map((r, i) => ({
    name: `#${i + 1}`,
    entrada: r.rows_in,
    saida: r.rows_out,
    duracao: r.duration_seconds || 0,
  }));

  return (
    <div className="fade-up">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <button onClick={onBack} style={{
            background: "none", border: "none", color: "var(--accent)", cursor: "pointer",
            fontFamily: "var(--font-sans)", fontSize: 12, marginBottom: 8, padding: 0,
          }}>← Voltar</button>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ fontSize: 22, fontWeight: 700 }}>{pipeline.name}</h2>
            <span title="Atualizações em tempo real ativas" style={{
              width: 8, height: 8, borderRadius: "50%",
              background: "var(--success)", display: "inline-block",
              boxShadow: "0 0 6px var(--success)",
            }} className="pulse" />
          </div>
          <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 4, maxWidth: 500 }}>{pipeline.description}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input ref={fileRef} type="file" accept=".csv,.json,.xlsx,.xls,.parquet" onChange={handleUpload} style={{ display: "none" }} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{
              padding: "8px 16px", background: "var(--accent-dim)", border: "1px solid var(--accent)40",
              color: "var(--accent)", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600,
              fontFamily: "var(--font-sans)",
            }}
          >{uploading ? "Enviando..." : "↑ Upload"}</button>
          <button
            onClick={handleTrigger}
            style={{
              padding: "8px 16px", background: "var(--accent)", border: "none",
              color: "#fff", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600,
              fontFamily: "var(--font-sans)",
            }}
          >▶ Executar</button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div style={{ display: "flex", gap: 10, marginBottom: 24, flexWrap: "wrap" }}>
          <MetricCard label="Execuções" value={stats.total_runs} />
          <MetricCard label="Taxa de Sucesso" value={`${stats.success_rate}%`} color="var(--success)" />
          <MetricCard label="Linhas Processadas" value={formatNumber(stats.total_rows_processed)} />
          <MetricCard label="Tokens Usados" value={formatNumber(stats.total_tokens_used)} color="var(--warning)" />
          <MetricCard label="Custo Est." value={`$${(stats.total_cost_usd ?? 0).toFixed(4)}`} color="#a78bfa" />
        </div>
      )}

      {/* Chart */}
      {chartData.length > 0 && (
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: 20, marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16, color: "var(--muted)", letterSpacing: 0.5, textTransform: "uppercase" }}>Volume por Execução</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
              <XAxis dataKey="name" tick={{ fill: "#7a7a96", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#7a7a96", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid #25253a", borderRadius: 6, fontSize: 12 }} />
              <Bar dataKey="entrada" fill="#4f8ff740" radius={[4, 4, 0, 0]} />
              <Bar dataKey="saida" fill="#4f8ff7" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Timeline */}
      <RunTimeline runs={pipeline.recent_runs} onSelect={setSelectedRun} />

      {/* DuckDB Analytics */}
      <AnalyticsSection pipelineId={pipelineId} />

      {/* Recent Runs */}
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 12, color: "var(--muted)", letterSpacing: 0.5, textTransform: "uppercase" }}>Últimas Execuções</div>
      {(pipeline.recent_runs || []).length === 0 ? (
        <EmptyState icon="🚀" title="Nenhuma execução" desc="Faça upload de um arquivo ou dispare uma execução." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {pipeline.recent_runs.map((run) => (
            <div
              key={run.id}
              onClick={() => setSelectedRun(run.id)}
              style={{
                padding: "14px 18px", background: "var(--surface)", borderRadius: 8,
                border: "1px solid var(--border)", cursor: "pointer",
                display: "flex", justifyContent: "space-between", alignItems: "center",
                transition: "border-color 0.2s",
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <Badge status={run.status} />
                <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
                  {run.id.slice(0, 8)}
                </span>
              </div>
              <div style={{ display: "flex", gap: 24, fontSize: 12, color: "var(--muted)" }}>
                <span>{formatNumber(run.rows_in)} → {formatNumber(run.rows_out)} linhas</span>
                <span>{formatDuration(run.duration_seconds)}</span>
                <span>{run.decision_count} decisões</span>
                <span>{formatDate(run.created_at)}</span>
                <span style={{ color: "var(--accent)" }}>→</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Run Detail View (Agent Decisions) ─── */

function RunDetail({ runId, onBack }) {
  const { data: run, loading } = useApi(`/runs/${runId}/`);

  if (loading || !run) {
    return <div className="pulse" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>Carregando execução...</div>;
  }

  const totalTokens = (run.decisions || []).reduce((sum, d) => sum + d.tokens_used, 0);
  const totalLatency = (run.decisions || []).reduce((sum, d) => sum + d.latency_ms, 0);

  return (
    <div className="fade-up">
      <button onClick={onBack} style={{
        background: "none", border: "none", color: "var(--accent)", cursor: "pointer",
        fontFamily: "var(--font-sans)", fontSize: 12, marginBottom: 16, padding: 0,
      }}>← Voltar ao pipeline</button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700 }}>Execução {run.id.slice(0, 8)}</h2>
          <div style={{ display: "flex", gap: 12, marginTop: 8, alignItems: "center" }}>
            <Badge status={run.status} />
            <span style={{ fontSize: 12, color: "var(--muted)" }}>Trigger: {run.trigger}</span>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>{formatDate(run.created_at)}</span>
          </div>
        </div>

        {run.status === "success" && (
          <div style={{ display: "flex", gap: 8 }}>
            <a
              href={`/api/runs/${run.id}/export/?format=csv`}
              download
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "7px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "var(--accent-dim)", color: "var(--accent)",
                border: "1px solid var(--accent)40", textDecoration: "none",
                transition: "background 0.15s",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--accent)25"}
              onMouseLeave={e => e.currentTarget.style.background = "var(--accent-dim)"}
            >
              ↓ CSV
            </a>
            <a
              href={`/api/runs/${run.id}/export/?format=parquet`}
              download
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "7px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "#a78bfa20", color: "#a78bfa",
                border: "1px solid #a78bfa40", textDecoration: "none",
                transition: "background 0.15s",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "#a78bfa30"}
              onMouseLeave={e => e.currentTarget.style.background = "#a78bfa20"}
            >
              ↓ Parquet
            </a>
          </div>
        )}
      </div>

      {/* Metrics */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
        {run.quality_report && (
          <div style={{
            background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)", padding: "12px 20px",
            display: "flex", flexDirection: "column", alignItems: "center",
          }}>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
              Qualidade
            </div>
            <QualityGauge score={Math.round(run.quality_report.quality_score)} />
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1, minWidth: 200 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <MetricCard label="Linhas Entrada" value={formatNumber(run.rows_in)} />
            <MetricCard label="Linhas Saída" value={formatNumber(run.rows_out)} color="var(--success)" />
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <MetricCard label="Duração" value={formatDuration(run.duration_seconds)} />
            <MetricCard label="Tokens" value={formatNumber(totalTokens)} color="var(--warning)" />
            <MetricCard label="Custo Est." value={`$${(run.quality_report?.details?.cost_usd ?? 0).toFixed(4)}`} color="#a78bfa" />
          </div>
        </div>
      </div>

      {/* Data Layers */}
      {run.layers?.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 12, color: "var(--muted)", letterSpacing: 0.5, textTransform: "uppercase" }}>
            Camadas de Dados
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {run.layers.map((layer) => {
              const cfg = {
                bronze: { color: "#cd7f32", bg: "#cd7f3215", label: "Bronze", icon: "⬡", desc: "Raw" },
                silver: { color: "#a8a9ad", bg: "#a8a9ad15", label: "Silver", icon: "⬡", desc: "Clean" },
                gold:   { color: "#fbbf24", bg: "#fbbf2415", label: "Gold",   icon: "⬡", desc: "Aggregated" },
              }[layer.layer] || {};

              return (
                <div key={layer.id} style={{
                  padding: "16px 18px", background: cfg.bg,
                  borderRadius: 8, border: `1px solid ${cfg.color}30`,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <span style={{ color: cfg.color, fontSize: 18 }}>{cfg.icon}</span>
                    <span style={{ fontWeight: 700, fontSize: 13, color: cfg.color }}>{cfg.label}</span>
                    <span style={{ fontSize: 10, color: "var(--muted)", marginLeft: "auto", textTransform: "uppercase", letterSpacing: 0.5 }}>{cfg.desc}</span>
                  </div>

                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-mono)", color: cfg.color, marginBottom: 8 }}>
                    {formatNumber(layer.row_count)} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}>linhas</span>
                  </div>

                  {layer.layer !== "gold" && layer.stats && (
                    <div style={{ fontSize: 11, color: "var(--muted)", display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>{layer.stats.column_count} colunas</span>
                      <span>{layer.stats.null_count} nulos · {layer.stats.duplicate_count} duplicatas</span>
                    </div>
                  )}

                  {layer.layer === "gold" && layer.stats && (
                    <div style={{ fontSize: 11, color: "var(--muted)", display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>Score: <span style={{ color: cfg.color }}>{layer.stats.quality_score}/100</span></span>
                      {layer.stats.transformations_applied?.length > 0 && (
                        <span>{layer.stats.transformations_applied.join(", ")}</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Agent Decision Timeline */}
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16, color: "var(--muted)", letterSpacing: 0.5, textTransform: "uppercase" }}>
        Log do Agente — Raciocínio Completo
      </div>

      <div style={{ position: "relative", paddingLeft: 28 }}>
        {/* Vertical line */}
        <div style={{
          position: "absolute", left: 11, top: 8, bottom: 8, width: 2,
          background: "linear-gradient(to bottom, var(--accent), var(--success))",
          borderRadius: 1, opacity: 0.3,
        }} />

        {(run.decisions || []).map((d, i) => (
          <div
            key={d.id}
            className="fade-up"
            style={{ animationDelay: `${i * 100}ms`, marginBottom: 16, position: "relative" }}
          >
            {/* Dot */}
            <div style={{
              position: "absolute", left: -22, top: 6, width: 10, height: 10,
              borderRadius: "50%", background: "var(--accent)", border: "2px solid var(--bg)",
            }} />

            <div style={{
              padding: "16px 20px", background: "var(--surface)", borderRadius: 8,
              border: "1px solid var(--border)",
            }}>
              {/* Step header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 16 }}>{STEP_ICONS[d.step] || "•"}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, textTransform: "uppercase",
                    letterSpacing: 1, color: "var(--accent)",
                  }}>{d.step}</span>
                </div>
                <div style={{ display: "flex", gap: 12, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
                  <span>{d.tokens_used} tok</span>
                  <span>{d.latency_ms}ms</span>
                </div>
              </div>

              {/* Reasoning */}
              <p style={{ fontSize: 13, lineHeight: 1.7, color: "var(--fg)", whiteSpace: "pre-wrap" }}>
                {d.reasoning}
              </p>

              {/* Action details */}
              {d.action?.tool && (
                <div style={{
                  marginTop: 10, padding: "8px 12px", background: "var(--surface2)",
                  borderRadius: 4, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--muted)",
                }}>
                  tool: <span style={{ color: "var(--accent)" }}>{d.action.tool}</span>
                  {d.action.output && (
                    <span> → {JSON.stringify(d.action.output).slice(0, 100)}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Error message if failed */}
      {run.error_message && (
        <div style={{
          marginTop: 16, padding: "14px 18px", background: "#ef444415",
          border: "1px solid #ef444430", borderRadius: 8, fontSize: 13,
          fontFamily: "var(--font-mono)", color: "var(--danger)",
        }}>
          {run.error_message}
        </div>
      )}
    </div>
  );
}

/* ─── Login Screen ─── */

function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState(null);
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("https://api-dataflow.pizani.ia.br/api/auth/token/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Credenciais inválidas.");
      }
      const { access } = await res.json();
      onLogin(access);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
      <div style={{ width: 360, padding: "40px 36px", background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8, background: "var(--accent-dim)",
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--accent)30", fontSize: 18,
          }}>⚡</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>DataFlow Agent</div>
            <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>Pipeline Orquestrador</div>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 11, color: "var(--muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Usuário
            </label>
            <input
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              required
              style={{
                width: "100%", padding: "10px 12px", background: "var(--surface2)",
                border: "1px solid var(--border)", borderRadius: 6,
                color: "var(--fg)", fontSize: 14, fontFamily: "var(--font-sans)", outline: "none",
              }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: "block", fontSize: 11, color: "var(--muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Senha
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              style={{
                width: "100%", padding: "10px 12px", background: "var(--surface2)",
                border: "1px solid var(--border)", borderRadius: 6,
                color: "var(--fg)", fontSize: 14, fontFamily: "var(--font-sans)", outline: "none",
              }}
            />
          </div>

          {error && (
            <div style={{
              marginBottom: 16, padding: "10px 12px", background: "#ef444415",
              border: "1px solid #ef444430", borderRadius: 6,
              fontSize: 13, color: "var(--danger)",
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%", padding: "11px 0", background: "var(--accent)",
              border: "none", borderRadius: 6, color: "#fff",
              fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1, transition: "opacity 0.2s",
            }}
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ─── Main App ─── */

export default function App() {
  const [authToken, setAuthToken]         = useState(() => getToken());
  const [search, setSearch]               = useState("");
  const [statusFilter, setStatusFilter]   = useState("");
  const [page, setPage]                   = useState(1);

  const apiParams = {};
  if (search)       apiParams.search = search;
  if (statusFilter) apiParams.status = statusFilter;
  if (page > 1)     apiParams.page   = page;

  const { data: pipelines, loading, refetch } = useApi("/pipelines/", { enabled: !!authToken, params: apiParams });
  const [selectedPipeline, setSelectedPipeline] = useState(null);
  const [currentTime, setCurrentTime]     = useState(new Date());
  const [theme, setTheme]                 = useState("dark");
  const [showNewModal, setShowNewModal]   = useState(false);

  // Escuta evento de logout disparado pelo apiFetch (401)
  useEffect(() => {
    const handler = () => setAuthToken(null);
    window.addEventListener("df:logout", handler);
    return () => window.removeEventListener("df:logout", handler);
  }, []);

  // Reset página ao mudar filtros
  useEffect(() => { setPage(1); }, [search, statusFilter]);

  // Clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);

  function handleLogin(access) {
    setToken(access);
    setAuthToken(access);
  }

  function handleLogout() {
    clearToken();
    setAuthToken(null);
    setSelectedPipeline(null);
  }

  async function handlePause(id) {
    try { await pausePipeline(id); refetch(); } catch {}
  }

  async function handleResume(id) {
    try { await resumePipeline(id); refetch(); } catch {}
  }

  return (
    <>
      <style>{globalCSS(theme)}</style>

      {!authToken && <LoginScreen onLogin={handleLogin} />}

      {authToken && showNewModal && (
        <NewPipelineModal
          onClose={() => setShowNewModal(false)}
          onCreated={() => { setShowNewModal(false); refetch(); }}
        />
      )}

      {authToken && (
      <div style={{ minHeight: "100vh", maxWidth: 1100, margin: "0 auto", padding: "0 24px" }}>
        {/* Header */}
        <header style={{
          padding: "20px 0", borderBottom: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginBottom: 28,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8, background: "var(--accent-dim)",
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid var(--accent)30", fontSize: 18,
            }}>⚡</div>
            <div>
              <h1 style={{ fontSize: 17, fontWeight: 700, letterSpacing: -0.3 }}>DataFlow Agent</h1>
              <p style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>Pipeline Orquestrador Autônomo</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <OllamaStatus />
            <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
              {currentTime.toLocaleString("pt-BR", { weekday: "short", hour: "2-digit", minute: "2-digit" })}
            </div>
            <button
              onClick={() => setTheme(t => t === "dark" ? "light" : "dark")}
              title={theme === "dark" ? "Modo claro" : "Modo escuro"}
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 6, cursor: "pointer", width: 32, height: 32,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 15, transition: "border-color 0.2s",
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
            >
              {theme === "dark" ? "☀︎" : "☽"}
            </button>
            <button
              onClick={handleLogout}
              title="Sair"
              style={{
                background: "transparent", border: "1px solid var(--border)",
                borderRadius: 6, cursor: "pointer", padding: "0 12px", height: 32,
                fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-mono)",
                transition: "border-color 0.2s, color 0.2s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--danger)"; e.currentTarget.style.color = "var(--danger)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--muted)"; }}
            >
              sair
            </button>
          </div>
        </header>

        {/* Content */}
        <main>
          {selectedPipeline ? (
            <PipelineDetail
              pipelineId={selectedPipeline}
              onBack={() => { setSelectedPipeline(null); refetch(); }}
            />
          ) : (
            <>
              {/* Toolbar */}
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
                <h2 style={{ fontSize: 16, fontWeight: 600, marginRight: 4 }}>Pipelines</h2>

                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar por nome..."
                  style={{
                    flex: 1, minWidth: 160, maxWidth: 300, padding: "7px 12px",
                    background: "var(--surface)", border: "1px solid var(--border)",
                    borderRadius: 6, color: "var(--fg)", fontSize: 13,
                    fontFamily: "var(--font-sans)", outline: "none",
                  }}
                />

                <select
                  value={statusFilter}
                  onChange={e => setStatusFilter(e.target.value)}
                  style={{
                    padding: "7px 10px", background: "var(--surface)",
                    border: "1px solid var(--border)", borderRadius: 6,
                    color: statusFilter ? "var(--fg)" : "var(--muted)",
                    fontSize: 13, fontFamily: "var(--font-sans)", outline: "none", cursor: "pointer",
                  }}
                >
                  <option value="">Todos os status</option>
                  <option value="draft">Rascunho</option>
                  <option value="active">Ativo</option>
                  <option value="paused">Pausado</option>
                  <option value="error">Com Erro</option>
                </select>

                <button
                  onClick={() => setShowNewModal(true)}
                  style={{
                    padding: "7px 14px", background: "var(--accent)",
                    border: "none", borderRadius: 6, color: "#fff",
                    fontSize: 13, fontWeight: 600, cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  + Nova Pipeline
                </button>

                <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: "auto" }}>
                  {pipelines?.count ?? 0} pipeline{(pipelines?.count ?? 0) !== 1 ? "s" : ""}
                </span>
              </div>

              {loading ? (
                <div className="pulse" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>Carregando...</div>
              ) : (
                <>
                  <PipelineList
                    pipelines={pipelines}
                    onSelect={setSelectedPipeline}
                    onPause={handlePause}
                    onResume={handleResume}
                  />

                  {/* Paginação */}
                  {(pipelines?.previous || pipelines?.next) && (
                    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginTop: 20 }}>
                      <button
                        onClick={() => setPage(p => p - 1)}
                        disabled={!pipelines.previous}
                        style={{
                          padding: "7px 18px", background: "var(--surface)", border: "1px solid var(--border)",
                          borderRadius: 6, color: pipelines.previous ? "var(--fg)" : "var(--muted)",
                          fontSize: 12, cursor: pipelines.previous ? "pointer" : "not-allowed",
                          fontFamily: "var(--font-sans)",
                        }}
                      >← Anterior</button>
                      <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                        página {page}
                      </span>
                      <button
                        onClick={() => setPage(p => p + 1)}
                        disabled={!pipelines.next}
                        style={{
                          padding: "7px 18px", background: "var(--surface)", border: "1px solid var(--border)",
                          borderRadius: 6, color: pipelines.next ? "var(--fg)" : "var(--muted)",
                          fontSize: 12, cursor: pipelines.next ? "pointer" : "not-allowed",
                          fontFamily: "var(--font-sans)",
                        }}
                      >Próxima →</button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </main>

        {/* Footer */}
        <footer style={{
          padding: "20px 0", marginTop: 40, borderTop: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", fontSize: 11,
          color: "var(--muted)", fontFamily: "var(--font-mono)",
        }}>
          <span>DataFlow Agent v1.0 </span>
          <span>Daniel Pizani · 2026</span>
        </footer>
      </div>
      )}
    </>
  );
}
