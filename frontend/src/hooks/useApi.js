import { useCallback, useEffect, useState } from "react";

const BASE_URL = "/api";
console.log(BASE_URL)
/* ─── Token helpers ─── */

export const getToken  = ()  => localStorage.getItem("df_token");
export const setToken  = (t) => localStorage.setItem("df_token", t);
export const clearToken = () => {
  localStorage.removeItem("df_token");
  window.dispatchEvent(new Event("df:logout"));
};

/* ─── apiFetch — wrapper com Authorization header e tratamento de 401 ─── */

async function apiFetch(url, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    throw new Error("Sessão expirada. Faça login novamente.");
  }

  return res;
}

/**
 * Hook genérico para chamadas à API.
 *
 * @param {string} endpoint - Ex: "/pipelines/"
 * @param {object} options - { autoFetch, params, enabled }
 */
export function useApi(endpoint, options = {}) {
  const { autoFetch = true, params = {}, enabled = true } = options;
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const queryString = new URLSearchParams(params).toString();
  const url = `${BASE_URL}${endpoint}${queryString ? `?${queryString}` : ""}`;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    if (autoFetch && enabled) fetchData();
  }, [autoFetch, enabled, fetchData]);

  return { data, loading, error, refetch: fetchData };
}

/**
 * Upload de arquivo para um pipeline.
 */
export async function uploadFile(pipelineId, file, context = "") {
  const form = new FormData();
  form.append("file", file);
  if (context) form.append("context", context);

  const res = await apiFetch(`${BASE_URL}/pipelines/${pipelineId}/upload/`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) throw new Error(`Upload falhou: HTTP ${res.status}`);
  return res.json();
}

/**
 * Cria um novo pipeline.
 */
export async function createPipeline(data) {
  const res = await apiFetch(`${BASE_URL}/pipelines/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error("Erro ao criar pipeline."), { detail: err });
  }
  return res.json();
}

/**
 * Pausa um pipeline ativo.
 */
export async function pausePipeline(pipelineId) {
  const res = await apiFetch(`${BASE_URL}/pipelines/${pipelineId}/pause/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Pause falhou: HTTP ${res.status}`);
  return res.json();
}

/**
 * Reativa um pipeline pausado.
 */
export async function resumePipeline(pipelineId) {
  const res = await apiFetch(`${BASE_URL}/pipelines/${pipelineId}/resume/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Resume falhou: HTTP ${res.status}`);
  return res.json();
}

/**
 * Dispara execução manual de um pipeline.
 */
export async function triggerPipeline(pipelineId) {
  const res = await apiFetch(`${BASE_URL}/pipelines/${pipelineId}/trigger/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) throw new Error(`Trigger falhou: HTTP ${res.status}`);
  return res.json();
}

/**
 * Verifica o health check do Ollama.
 * Retorna: { ollama_url, ollama_model, status, error }
 */
export async function checkOllamaHealth() {
  const res = await fetch(`${BASE_URL}/health/`);
  const data = await res.json();
  return data;
}
