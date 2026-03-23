/**
 * Formata duração em segundos para display.
 */
export function formatDuration(seconds) {
  if (!seconds) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const min = Math.floor(seconds / 60);
  const sec = Math.round(seconds % 60);
  return `${min}m ${sec}s`;
}

/**
 * Formata data ISO para display BR.
 */
export function formatDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Formata números grandes.
 */
export function formatNumber(n) {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR");
}

/**
 * Cores e labels por status.
 */
export const STATUS_CONFIG = {
  draft: { color: "#6b7280", bg: "#6b728015", label: "Rascunho" },
  active: { color: "#10b981", bg: "#10b98115", label: "Ativo" },
  paused: { color: "#f59e0b", bg: "#f59e0b15", label: "Pausado" },
  error: { color: "#ef4444", bg: "#ef444415", label: "Com Erro" },
  pending: { color: "#6b7280", bg: "#6b728015", label: "Pendente" },
  running: { color: "#3b82f6", bg: "#3b82f615", label: "Executando" },
  success: { color: "#10b981", bg: "#10b98115", label: "Sucesso" },
  failed: { color: "#ef4444", bg: "#ef444415", label: "Falhou" },
};

/**
 * Ícones por step do agente.
 */
export const STEP_ICONS = {
  classify: "🔍",
  quality: "📊",
  plan: "📋",
  execute: "⚙️",
  validate: "✅",
};
