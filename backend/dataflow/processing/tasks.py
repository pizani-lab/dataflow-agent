"""
DataFlow Agent — Celery Tasks

Tasks assíncronas para processamento de pipelines.
O Celery worker executa o agente LLM e registra resultados.
"""
import io
import logging

import pandas as pd
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_pipeline_task(self, run_id: str, data_content: str, context: str = ""):
    """
    Task principal: executa o agente LLM para processar dados.

    Args:
        run_id: UUID do ProcessingRun.
        data_content: Conteúdo dos dados (CSV/JSON string).
        context: Contexto adicional para o agente.
    """
    from dataflow.agent import DataFlowAgent
    from dataflow.models import AgentDecision, ProcessingRun, QualityReport

    # Busca o run
    try:
        run = ProcessingRun.objects.select_related("pipeline").get(id=run_id)
    except ProcessingRun.DoesNotExist:
        logger.error(f"Run {run_id} não encontrado.")
        return {"error": "Run não encontrado."}

    # Marca como running
    run.status = ProcessingRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    _broadcast_run(run)

    try:
        # rows_in já definido pelo upload view; atualiza apenas se ainda for 0
        if run.rows_in == 0:
            lines = data_content.strip().split("\n")
            run.rows_in = max(len(lines) - 1, 0)

        # Bronze: dados raw antes de qualquer transformação
        _save_bronze_layer(run, data_content)

        # Executa o agente
        agent = DataFlowAgent()
        result = agent.process(sample_data=data_content, context=context)

        # Salva as decisões do agente no banco
        for decision_data in result.get("decisions", []):
            AgentDecision.objects.create(
                run=run,
                step=decision_data.get("step", "execute"),
                reasoning=decision_data.get("reasoning", ""),
                action=decision_data.get("action", {}),
                tokens_used=decision_data.get("tokens_used", 0),
                latency_ms=decision_data.get("latency_ms", 0),
            )

        # Extrai métricas do validate_output (última decisão de validação)
        validate_metrics = _extract_validate_output(result)
        rows_out = validate_metrics.get("row_count", run.rows_in)

        # Recupera CSV processado do export store (gerado pelo validate_output)
        session_id = _extract_session_id(result)
        from dataflow.agent.tools import get_export_csv
        processed_csv = get_export_csv(session_id) if session_id else None

        # Silver: dados limpos após transformações do agente
        _save_silver_layer(run, processed_csv)

        # Gold: métricas agregadas e transformações aplicadas
        _save_gold_layer(run, validate_metrics, result.get("decisions", []))

        # Cria relatório de qualidade
        total_tokens = result.get("total_tokens", 0)
        from dataflow.analytics.costs import compute_cost
        QualityReport.objects.create(
            run=run,
            quality_score=result.get("quality_score", 0),
            null_percentage=validate_metrics.get("null_pct", 0.0),
            duplicate_percentage=validate_metrics.get("duplicate_pct", 0.0),
            schema_drift_detected=validate_metrics.get("schema_drift_detected", False),
            details={
                "total_tokens": total_tokens,
                "cost_usd": compute_cost(total_tokens),
                "iterations": result.get("iterations", 0),
                "row_count_after": rows_out,
                "processed_csv": processed_csv,
            },
        )

        # Finaliza com sucesso
        run.status = ProcessingRun.Status.SUCCESS
        run.rows_out = rows_out
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "rows_in", "rows_out", "ended_at"])
        _broadcast_run(run, extra={"quality_score": result.get("quality_score", 0)})

        logger.info(
            f"Run {run_id} concluído: {result.get('iterations', 0)} iterações, "
            f"{result.get('total_tokens', 0)} tokens."
        )

        return {
            "status": "success",
            "run_id": run_id,
            "iterations": result.get("iterations", 0),
            "total_tokens": result.get("total_tokens", 0),
            "quality_score": result.get("quality_score", 0),
        }

    except Exception as exc:
        run.status = ProcessingRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "error_message", "ended_at"])
        _broadcast_run(run)

        logger.exception(f"Run {run_id} falhou: {exc}")

        # Retry se possível
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {"status": "failed", "error": str(exc)}


def _broadcast_run(run, extra: dict | None = None) -> None:
    """
    Envia atualização de status do run para o grupo WebSocket do pipeline.

    Silencia erros para não quebrar o fluxo se Redis estiver indisponível.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        payload = {
            "type": "run_update",
            "run_id": str(run.id),
            "status": run.status,
            "rows_in": run.rows_in,
            "rows_out": run.rows_out,
        }
        if extra:
            payload.update(extra)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"pipeline_{run.pipeline_id}",
            {"type": "run.update", "data": payload},
        )
    except Exception as exc:
        logger.warning(f"WebSocket broadcast falhou (non-fatal): {exc}")


def _df_to_sample(df: pd.DataFrame) -> list:
    """Converte as primeiras 10 linhas para lista de dicts serializável em JSON."""
    return df.head(10).fillna("").astype(str).to_dict("records")


def _save_bronze_layer(run, data_content: str) -> None:
    """Salva camada bronze com os dados raw antes de qualquer transformação."""
    from dataflow.models import DataLayer

    try:
        content = data_content.strip()
        if content.startswith("[") or content.startswith("{"):
            import json
            records = json.loads(content)
            df = pd.DataFrame(records if isinstance(records, list) else [records])
        else:
            df = pd.read_csv(io.StringIO(content))
    except Exception:
        return

    DataLayer.objects.create(
        run=run,
        layer=DataLayer.Layer.BRONZE,
        row_count=len(df),
        schema={col: str(dtype) for col, dtype in df.dtypes.items()},
        sample=_df_to_sample(df),
        stats={
            "column_count": len(df.columns),
            "null_count": int(df.isnull().sum().sum()),
            "duplicate_count": int(df.duplicated().sum()),
        },
    )


def _save_silver_layer(run, processed_csv: str | None) -> None:
    """Salva camada silver com os dados limpos pelo agente."""
    from dataflow.models import DataLayer

    if not processed_csv:
        return

    try:
        df = pd.read_csv(io.StringIO(processed_csv))
    except Exception:
        return

    DataLayer.objects.create(
        run=run,
        layer=DataLayer.Layer.SILVER,
        row_count=len(df),
        schema={col: str(dtype) for col, dtype in df.dtypes.items()},
        sample=_df_to_sample(df),
        stats={
            "column_count": len(df.columns),
            "null_count": int(df.isnull().sum().sum()),
            "duplicate_count": int(df.duplicated().sum()),
        },
    )


def _save_gold_layer(run, validate_metrics: dict, decisions: list) -> None:
    """Salva camada gold com métricas agregadas e transformações aplicadas."""
    from dataflow.models import DataLayer

    transformations = [
        d.get("action", {}).get("input", {}).get("operation")
        for d in decisions
        if d.get("action", {}).get("tool") == "execute_transform"
    ]

    DataLayer.objects.create(
        run=run,
        layer=DataLayer.Layer.GOLD,
        row_count=validate_metrics.get("row_count", 0),
        schema={},
        sample=[],
        stats={
            "quality_score": validate_metrics.get("quality_score", 0),
            "null_percentage": validate_metrics.get("null_pct", 0),
            "duplicate_percentage": validate_metrics.get("duplicate_pct", 0),
            "transformations_applied": [t for t in transformations if t],
            "total_tokens": sum(d.get("tokens_used", 0) for d in decisions),
        },
    )


def _extract_validate_output(result: dict) -> dict:
    """
    Extrai métricas do último validate_output nas decisões do agente.

    Retorna null_pct, duplicate_pct, schema_drift_detected e row_count.
    """
    for decision in reversed(result.get("decisions", [])):
        action = decision.get("action", {})
        if isinstance(action, dict) and action.get("tool") == "validate_output":
            output = action.get("output", {})
            if isinstance(output, dict) and "quality_score" in output:
                return output
    return {}


def _extract_session_id(result: dict) -> str | None:
    """
    Extrai o session_id do input do validate_output nas decisões do agente.

    Necessário para recuperar o CSV processado do export store.
    """
    for decision in reversed(result.get("decisions", [])):
        action = decision.get("action", {})
        if isinstance(action, dict) and action.get("tool") == "validate_output":
            return action.get("input", {}).get("session_id")
    return None
