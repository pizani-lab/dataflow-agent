"""
DataFlow Agent — Tool Definitions

Cada tool é uma função que o agente pode chamar via tool_use.
O estado dos DataFrames entre chamadas é mantido em _SESSION_STORE,
indexado pelo session_id retornado por detect_schema.

Suporta Ollama local e cloud com OpenAI-compatible API.
"""
import io
import re
import threading
import time
import uuid
from collections import OrderedDict
from functools import wraps
from typing import Any

import pandas as pd

# Tenta importar settings, se falhar usa defaults
try:
    from django.conf import settings
    _SESSION_TTL_SECONDS = getattr(settings, "AGENT_SESSION_TTL", 3600)
    _EXPORT_CHAR_LIMIT = getattr(settings, "AGENT_EXPORT_LIMIT", 1_000_000)
    _AGENT_MAX_SESSIONS = getattr(settings, "AGENT_MAX_SESSIONS", 100)
except Exception:
    _SESSION_TTL_SECONDS = 3600
    _EXPORT_CHAR_LIMIT = 1_000_000
    _AGENT_MAX_SESSIONS = 100

# Thread-safe session store com TTL
class _SessionStore:
    """Thread-safe session store com expirable entries."""

    def __init__(self, maxsize: int = 100, ttl: int = 3600):
        self._store: OrderedDict[str, tuple[pd.DataFrame, float]] = OrderedDict()
        self._lock = threading.RLock()
        self._maxsize = maxsize
        self._ttl = ttl

    def __contains__(self, key: str) -> bool:
        """Suporte a 'key in store'."""
        with self._lock:
            if key not in self._store:
                return False
            _, timestamp = self._store[key]
            if time.time() - timestamp > self._ttl:
                del self._store[key]
                return False
            return True

    def __getitem__(self, key: str) -> pd.DataFrame:
        """Suporte a store[key]."""
        df = self.get(key)
        if df is None:
            raise KeyError(key)
        return df

    def get(self, key: str, default=None) -> pd.DataFrame | None:
        """Get com suporte a default (para compatibilidade com testes)."""
        with self._lock:
            if key not in self._store:
                return default
            df, timestamp = self._store[key]
            if time.time() - timestamp > self._ttl:
                del self._store[key]
                return default
            # Move to end (most recently used)
            self._store.move_to_end(key)
            return df

    def set(self, key: str, df: pd.DataFrame):
        with self._lock:
            # Evict oldest if at capacity
            while len(self._store) >= self._maxsize:
                self._store.popitem(last=False)
            self._store[key] = (df, time.time())
            self._store.move_to_end(key)

    def pop(self, key: str, default=None) -> pd.DataFrame | None:
        """Pop com suporte a default (para compatibilidade com testes)."""
        with self._lock:
            if key not in self._store:
                return default
            df, _ = self._store.pop(key)
            return df

    def cleanup_expired(self):
        """Remove entries older than TTL."""
        with self._lock:
            now = time.time()
            expired = [
                k for k, (_, ts) in self._store.items()
                if now - ts > self._ttl
            ]
            for k in expired:
                del self._store[k]

    def clear(self):
        with self._lock:
            self._store.clear()

    def keys(self):
        """Retorna chaves ativas (não expiradas)."""
        with self._lock:
            now = time.time()
            return [
                k for k, (_, ts) in self._store.items()
                if now - ts <= self._ttl
            ]


_SESSION_STORE = _SessionStore(
    maxsize=_AGENT_MAX_SESSIONS,
    ttl=_SESSION_TTL_SECONDS,
)

# Thread-safe export store
_EXPORT_STORE: dict[str, str] = {}
_EXPORT_LOCK = threading.RLock()


def get_export_csv(session_id: str) -> str | None:
    """
    Recupera e remove o CSV processado do export store.

    Deve ser chamada pelo Celery task após agent.process().
    """
    with _EXPORT_LOCK:
        return _EXPORT_STORE.pop(session_id, None)


# ──────────────────────────────────────────────
# Tool Schemas (enviados na API call)
# ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "detect_schema",
        "description": (
            "Analisa uma amostra de dados e retorna o schema detectado: "
            "nomes de colunas, tipos inferidos e estatísticas básicas. "
            "IMPORTANTE: retorna um session_id que DEVE ser passado para todas as tools seguintes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sample_data": {
                    "type": "string",
                    "description": "Primeiras linhas dos dados em formato CSV ou JSON.",
                },
            },
            "required": ["sample_data"],
        },
    },
    {
        "name": "assess_quality",
        "description": (
            "Avalia a qualidade dos dados: porcentagem de nulos por coluna, "
            "duplicatas e outliers (método IQR para colunas numéricas)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ID da sessão retornado pelo detect_schema.",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "plan_transformation",
        "description": (
            "Registra e valida o plano de transformação com steps ordenados. "
            "Cada step deve ter: operation, params e rationale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ID da sessão retornado pelo detect_schema.",
                },
                "quality_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de problemas de qualidade a serem resolvidos.",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string"},
                            "params": {"type": "object"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["operation", "params"],
                    },
                    "description": "Steps do plano de transformação.",
                },
            },
            "required": ["session_id", "quality_issues", "steps"],
        },
    },
    {
        "name": "execute_transform",
        "description": (
            "Executa uma transformação específica nos dados. "
            "Retorna métricas da operação (linhas antes/depois). "
            "Chame uma vez por operação do plano."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ID da sessão retornado pelo detect_schema.",
                },
                "operation": {
                    "type": "string",
                    "enum": [
                        "drop_nulls",
                        "rename_columns",
                        "cast_types",
                        "deduplicate",
                        "filter_rows",
                        "normalize",
                        "fill_nulls",
                    ],
                    "description": "Tipo de operação a executar.",
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Parâmetros da operação. Exemplos: "
                        "drop_nulls: {columns: [col1]} | "
                        "rename_columns: {mapping: {old: new}} | "
                        "cast_types: {column: col1, dtype: int} | "
                        "deduplicate: {subset: [col1, col2]} | "
                        "filter_rows: {expr: 'age > 0'} | "
                        "normalize: {columns: [col1]} | "
                        "fill_nulls: {column: col1, value: 0}"
                    ),
                },
            },
            "required": ["session_id", "operation", "params"],
        },
    },
    {
        "name": "validate_output",
        "description": (
            "Valida os dados transformados e calcula o quality_score final. "
            "Deve ser chamada como último step. Libera a sessão da memória."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ID da sessão retornado pelo detect_schema.",
                },
                "expected_schema": {
                    "type": "object",
                    "description": "Schema esperado após transformações (opcional).",
                },
            },
            "required": ["session_id"],
        },
    },
]


# ──────────────────────────────────────────────
# Tool Implementations (executadas localmente)
# ──────────────────────────────────────────────

def detect_schema(sample_data: str) -> dict:
    """
    Detecta schema a partir de uma amostra CSV/JSON.

    Armazena o DataFrame no session store e retorna session_id
    para uso nas ferramentas subsequentes.

    Args:
        sample_data: Dados brutos em formato CSV ou JSON.

    Returns:
        Dict com session_id, columns, row_count e size_bytes.
    """
    trimmed = sample_data.strip()
    if trimmed.startswith(("[", "{")):
        try:
            df = pd.read_json(io.StringIO(sample_data))
        except Exception:
            return {"error": "Formato não reconhecido. Envie CSV ou JSON."}
    else:
        try:
            df = pd.read_csv(io.StringIO(sample_data))
        except Exception:
            try:
                df = pd.read_json(io.StringIO(sample_data))
            except Exception:
                return {"error": "Formato não reconhecido. Envie CSV ou JSON."}

    if df.empty:
        return {"error": "Dados vazios ou sem linhas de conteúdo."}

    session_id = str(uuid.uuid4())
    _SESSION_STORE.set(session_id, df)

    columns = []
    for col in df.columns:
        col_info: dict = {
            "name": col,
            "dtype": str(df[col].dtype),
            "null_count": int(df[col].isnull().sum()),
            "null_pct": round(float(df[col].isnull().mean() * 100), 2),
            "unique_count": int(df[col].nunique()),
            "sample_values": [
                v.item() if hasattr(v, "item") else v
                for v in df[col].dropna().head(3).tolist()
            ],
        }
        if pd.api.types.is_numeric_dtype(df[col]) and not df[col].isnull().all():
            col_info["min"] = float(df[col].min())
            col_info["max"] = float(df[col].max())
            col_info["mean"] = round(float(df[col].mean()), 4)
        columns.append(col_info)

    return {
        "session_id": session_id,
        "columns": columns,
        "row_count": len(df),
        "column_count": len(df.columns),
        "size_bytes": int(df.memory_usage(deep=True).sum()),
    }


def assess_quality(session_id: str) -> dict:
    """
    Avalia a qualidade dos dados usando pandas.

    Calcula nulos por coluna, duplicatas e outliers (IQR) a partir
    do DataFrame armazenado no session store.

    Args:
        session_id: ID da sessão retornado por detect_schema.

    Returns:
        Dict com métricas de qualidade e lista de quality_issues.
    """
    df = _SESSION_STORE.get(session_id)
    if df is None:
        return {"error": f"Sessão '{session_id}' não encontrada ou expirada. Execute detect_schema primeiro."}

    total_rows = len(df)
    duplicate_count = int(df.duplicated().sum())
    duplicate_pct = round(float(duplicate_count / total_rows * 100), 2) if total_rows > 0 else 0.0

    columns_quality = []
    total_null_count = 0
    quality_issues: list[str] = []

    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        null_pct = round(float(null_count / total_rows * 100), 2) if total_rows > 0 else 0.0
        total_null_count += null_count

        col_info: dict = {
            "name": col,
            "null_count": null_count,
            "null_pct": null_pct,
        }

        if null_pct > 0:
            quality_issues.append(
                f"Coluna '{col}' tem {null_pct}% de valores nulos ({null_count} linhas)"
            )

        # Outliers para colunas numéricas via IQR
        if pd.api.types.is_numeric_dtype(df[col]) and null_count < total_rows:
            q1 = float(df[col].quantile(0.25))
            q3 = float(df[col].quantile(0.75))
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outlier_count = int(((df[col] < lower) | (df[col] > upper)).sum())
            col_info["outlier_count"] = outlier_count
            col_info["outlier_pct"] = round(float(outlier_count / total_rows * 100), 2)
            if outlier_count > 0:
                quality_issues.append(
                    f"Coluna '{col}' tem {outlier_count} outliers "
                    f"(intervalo esperado: [{lower:.2f}, {upper:.2f}])"
                )

        columns_quality.append(col_info)

    total_cells = total_rows * len(df.columns)
    overall_null_pct = round(float(total_null_count / total_cells * 100), 2) if total_cells > 0 else 0.0

    if duplicate_count > 0:
        quality_issues.append(f"{duplicate_count} linhas duplicadas ({duplicate_pct}%)")

    return {
        "total_rows": total_rows,
        "total_columns": len(df.columns),
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "overall_null_pct": overall_null_pct,
        "columns_quality": columns_quality,
        "quality_issues": quality_issues,
        "has_issues": len(quality_issues) > 0,
    }


def plan_transformation(session_id: str, quality_issues: list, steps: list) -> dict:
    """
    Registra e valida o plano de transformação.

    Verifica que a sessão existe e que cada step tem operação válida.

    Args:
        session_id: ID da sessão retornado por detect_schema.
        quality_issues: Problemas identificados no assess_quality.
        steps: Lista de steps com operation, params e rationale.

    Returns:
        Dict com plano validado e warnings sobre operações desconhecidas.
    """
    df = _SESSION_STORE.get(session_id)
    if df is None:
        return {"error": f"Sessão '{session_id}' não encontrada ou expirada."}

    valid_operations = {
        "drop_nulls", "rename_columns", "cast_types",
        "deduplicate", "filter_rows", "normalize", "fill_nulls",
    }

    validated_steps = []
    warnings: list[str] = []

    for i, step in enumerate(steps):
        op = step.get("operation", "")
        if op not in valid_operations:
            warnings.append(f"Step {i + 1}: operação '{op}' não reconhecida, será ignorada.")
        else:
            validated_steps.append(step)

    return {
        "status": "plan_validated",
        "total_steps": len(validated_steps),
        "issues_addressed": len(quality_issues),
        "current_rows": len(df),
        "current_columns": len(df.columns),
        "validated_steps": validated_steps,
        "warnings": warnings,
    }


def _sanitize_filter_expr(expr: str, available_columns: list[str]) -> str:
    """
    Sanitiza expressão para filter_rows, prevenindo injeção.

    Permite apenas identifiers, números, operadores python e espaços.
    """
    if not expr:
        return expr

    # Extrai todas as colunas usadas na expressão
    col_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b'
    used_cols = re.findall(col_pattern, expr)

    # Valida que todas as colunas usadas existem no DataFrame
    for col in used_cols:
        if col not in available_columns and col not in ('True', 'False', 'and', 'or', 'not', 'in', 'is', 'None', 'NaN'):
            raise ValueError(f"Coluna '{col}' não existe no dataset")

    # Permite apenas caracteres seguros para expressões pandas
    safe_pattern = r'^[\w\s\+\-\*\/\%\=\<\>\!\(\)\[\]\{\}\,\.\'\"]+$'
    if not re.match(safe_pattern, expr):
        raise ValueError("Expressão contém caracteres não permitidos")

    return expr


def execute_transform(session_id: str, operation: str, params: dict) -> dict:
    """
    Executa uma transformação no DataFrame armazenado na sessão.

    Operações disponíveis:
        - drop_nulls: remove linhas com nulos (params: {columns: [...]})
        - rename_columns: renomeia colunas (params: {mapping: {old: new}})
        - cast_types: converte tipo de coluna (params: {column: str, dtype: str})
        - deduplicate: remove duplicatas (params: {subset: [...]} opcional)
        - filter_rows: filtra linhas (params: {expr: 'age > 0'})
        - normalize: normalização min-max (params: {columns: [...]})
        - fill_nulls: preenche nulos (params: {column: str, value: any})

    Args:
        session_id: ID da sessão retornado por detect_schema.
        operation: Nome da operação a executar.
        params: Parâmetros da operação.

    Returns:
        Dict com status, rows_before, rows_after e rows_affected.
    """
    df = _SESSION_STORE.get(session_id)
    if df is None:
        return {"error": f"Sessão '{session_id}' não encontrada ou expirada."}

    rows_before = len(df)
    available_columns = list(df.columns)

    try:
        if operation == "drop_nulls":
            subset = params.get("columns") or params.get("subset")
            df = df.dropna(subset=subset)

        elif operation == "rename_columns":
            mapping = params.get("mapping", {})
            df = df.rename(columns=mapping)

        elif operation == "cast_types":
            column = params.get("column") or params.get("col")
            dtype = params.get("dtype", "str")
            if not column or column not in df.columns:
                return {"error": f"Coluna '{column}' não encontrada."}
            try:
                df = df.assign(**{column: df[column].astype(dtype)})
            except Exception as e:
                return {"error": f"Erro ao converter tipo: {str(e)}"}

        elif operation == "deduplicate":
            subset = params.get("subset") or params.get("columns")
            df = df.drop_duplicates(subset=subset)

        elif operation == "filter_rows":
            expr = params.get("expr", "")
            if not expr:
                return {"error": "Parâmetro 'expr' obrigatório para filter_rows."}
            expr = _sanitize_filter_expr(expr, available_columns)
            df = df.query(expr)

        elif operation == "normalize":
            cols_to_normalize = params.get("columns", [])
            updates: dict = {}
            for col in cols_to_normalize:
                if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                    col_min = df[col].min()
                    col_max = df[col].max()
                    # Evita divisão por zero - mantém valor original se min==max
                    if col_max != col_min:
                        updates[col] = (df[col] - col_min) / (col_max - col_min)
                    else:
                        # Quando não há variação, usa 0.5 como valor neutro
                        updates[col] = 0.5
            df = df.assign(**updates) if updates else df

        elif operation == "fill_nulls":
            column = params.get("column")
            value = params.get("value")
            if column:
                if column not in df.columns:
                    return {"error": f"Coluna '{column}' não encontrada."}
                df = df.assign(**{column: df[column].fillna(value)})
            else:
                df = df.fillna(value)

        else:
            return {"error": f"Operação '{operation}' não implementada."}

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Erro ao executar '{operation}': {str(e)}"}

    rows_after = len(df)
    _SESSION_STORE.set(session_id, df)

    return {
        "status": "success",
        "operation": operation,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_affected": rows_before - rows_after,
        "columns": list(df.columns),
        "column_count": len(df.columns),
    }


def validate_output(session_id: str, expected_schema: dict | None = None) -> dict:
    """
    Valida os dados finais e calcula o quality_score real.

    Score = 100 - (null_pct × 0.5) - (dup_pct × 0.3) - (schema_drift_penalty × 0.2)

    Limpa a sessão do store após validação.

    Args:
        session_id: ID da sessão retornado por detect_schema.
        expected_schema: Schema esperado para verificar drift (opcional).

    Returns:
        Dict com quality_score, null_pct, duplicate_pct e schema_drift_detected.
    """
    df = _SESSION_STORE.get(session_id)
    if df is None:
        return {"error": f"Sessão '{session_id}' não encontrada ou expirada."}

    total_rows = len(df)
    total_cells = total_rows * len(df.columns)
    null_count = int(df.isnull().sum().sum())
    null_pct = round(float(null_count / total_cells * 100), 2) if total_cells > 0 else 0.0

    dup_count = int(df.duplicated().sum())
    dup_pct = round(float(dup_count / total_rows * 100), 2) if total_rows > 0 else 0.0

    schema_drift = False
    schema_drift_penalty = 0.0
    if expected_schema and "columns" in expected_schema:
        expected_cols = {c["name"] for c in expected_schema["columns"]}
        actual_cols = set(df.columns)
        missing = expected_cols - actual_cols
        extra = actual_cols - expected_cols
        if missing or extra:
            schema_drift = True
            schema_drift_penalty = min(20.0, len(missing) * 5.0 + len(extra) * 2.0)

    quality_score = max(0.0, 100.0 - (null_pct * 0.5) - (dup_pct * 0.3) - schema_drift_penalty)
    quality_score = round(quality_score, 2)

    # Salva CSV processado para download antes de limpar a sessão
    csv_data = df.to_csv(index=False)
    if len(csv_data) > _EXPORT_CHAR_LIMIT:
        csv_data = csv_data[:_EXPORT_CHAR_LIMIT]

    with _EXPORT_LOCK:
        _EXPORT_STORE[session_id] = csv_data

    # Libera a sessão da memória
    _SESSION_STORE.pop(session_id, None)

    issues_remaining: list[str] = []
    if null_pct > 0:
        issues_remaining.append(f"Ainda há {null_pct}% de nulos")
    if dup_pct > 0:
        issues_remaining.append(f"Ainda há {dup_pct}% de duplicatas")
    if schema_drift:
        issues_remaining.append("Schema drift detectado")

    return {
        "status": "validated",
        "row_count": total_rows,
        "column_count": len(df.columns),
        "null_pct": null_pct,
        "duplicate_pct": dup_pct,
        "schema_drift_detected": schema_drift,
        "quality_score": quality_score,
        "issues_remaining": issues_remaining,
    }


# Mapa de nome → função para dispatch
TOOL_HANDLERS = {
    "detect_schema": detect_schema,
    "assess_quality": assess_quality,
    "plan_transformation": plan_transformation,
    "execute_transform": execute_transform,
    "validate_output": validate_output,
}
