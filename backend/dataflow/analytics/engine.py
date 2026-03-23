"""
DataFlow Agent — DuckDB Analytics Engine

Executa queries analíticas in-memory sobre dados do pipeline
usando DuckDB, com suporte a window functions e aggregations.
"""
import duckdb
import pandas as pd
from django.conf import settings

from dataflow.models import AgentDecision, ProcessingRun, QualityReport


class DuckDBAnalytics:
    """
    Engine de analytics in-memory usando DuckDB.

    Carrega dados do ORM Django em DataFrames e executa queries
    analíticas com window functions e aggregations.
    """

    def pipeline_analytics(self, pipeline_id: str) -> dict:
        """
        Retorna métricas analíticas agregadas para um pipeline.

        Carrega runs com status 'success', quality reports e agent decisions
        em DuckDB in-memory e executa 3 queries analíticas:
        - Tendência de qualidade com média móvel de 3 runs
        - Tokens e latência agrupados por step do agente
        - Retenção de dados (rows_out / rows_in) por run

        Args:
            pipeline_id: UUID do pipeline como string.

        Returns:
            Dicionário com chaves quality_trend, step_stats e retention.
        """
        runs_qs = (
            ProcessingRun.objects
            .filter(pipeline_id=pipeline_id, status=ProcessingRun.Status.SUCCESS)
            .order_by("created_at")
            .values("id", "started_at", "created_at", "rows_in", "rows_out")
        )
        runs_data = list(runs_qs)

        if not runs_data:
            return {"quality_trend": [], "step_stats": [], "retention": [], "cost_trend": []}

        blended_rate = getattr(settings, "ANTHROPIC_BLENDED_COST_PER_M", 5.40)

        run_ids = [str(r["id"]) for r in runs_data]

        quality_data = list(
            QualityReport.objects
            .filter(run_id__in=run_ids)
            .values("run_id", "quality_score", "null_percentage", "duplicate_percentage")
        )

        decisions_data = list(
            AgentDecision.objects
            .filter(run_id__in=run_ids)
            .values("run_id", "step", "tokens_used", "latency_ms")
        )

        # Converte UUIDs para string (DuckDB não suporta objetos UUID nativos)
        for r in runs_data:
            r["id"] = str(r["id"])
        for q in quality_data:
            q["run_id"] = str(q["run_id"])
        for d in decisions_data:
            d["run_id"] = str(d["run_id"])

        runs_df = pd.DataFrame(runs_data)
        quality_df = pd.DataFrame(quality_data) if quality_data else pd.DataFrame(
            columns=["run_id", "quality_score", "null_percentage", "duplicate_percentage"]
        )
        decisions_df = pd.DataFrame(decisions_data) if decisions_data else pd.DataFrame(
            columns=["run_id", "step", "tokens_used", "latency_ms"]
        )

        con = duckdb.connect()
        try:
            con.register("runs", runs_df)
            con.register("quality", quality_df)
            con.register("decisions", decisions_df)

            # Tendência de qualidade com média móvel de 3 runs (window function)
            quality_trend = con.execute("""
                SELECT
                    ROW_NUMBER() OVER (ORDER BY r.created_at)    AS run_num,
                    COALESCE(q.quality_score, 0)                  AS quality_score,
                    ROUND(
                        AVG(COALESCE(q.quality_score, 0)) OVER (
                            ORDER BY r.created_at
                            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                        ), 1
                    )                                             AS moving_avg,
                    COALESCE(q.null_percentage, 0)               AS null_pct,
                    COALESCE(q.duplicate_percentage, 0)          AS dup_pct
                FROM runs r
                LEFT JOIN quality q ON q.run_id = r.id
                ORDER BY r.created_at
            """).df().to_dict("records")

            # Tokens e latência por step do agente
            if not decisions_df.empty:
                step_stats = con.execute("""
                    SELECT
                        step,
                        SUM(tokens_used)          AS total_tokens,
                        ROUND(AVG(latency_ms), 0) AS avg_latency_ms,
                        COUNT(*)                  AS call_count
                    FROM decisions
                    GROUP BY step
                    ORDER BY total_tokens DESC
                """).df().to_dict("records")
            else:
                step_stats = []

            # Retenção de dados por run (rows_out / rows_in)
            retention = con.execute("""
                SELECT
                    ROW_NUMBER() OVER (ORDER BY started_at) AS run_num,
                    rows_in,
                    rows_out,
                    ROUND(
                        rows_out * 100.0 / NULLIF(rows_in, 0), 1
                    ) AS retention_pct
                FROM runs
                ORDER BY created_at
            """).df().to_dict("records")

            # Custo por run e custo acumulado (window sum)
            if not decisions_df.empty:
                con.execute(f"SET VARIABLE blended_rate = {blended_rate}")
                cost_trend = con.execute("""
                    SELECT
                        ROW_NUMBER() OVER (ORDER BY r.created_at)      AS run_num,
                        SUM(d.tokens_used)                              AS tokens,
                        ROUND(
                            SUM(d.tokens_used) * getvariable('blended_rate') / 1000000, 6
                        )                                               AS cost_usd,
                        ROUND(
                            SUM(SUM(d.tokens_used)) OVER (
                                ORDER BY r.created_at
                            ) * getvariable('blended_rate') / 1000000, 6
                        )                                               AS cumulative_cost_usd
                    FROM runs r
                    JOIN decisions d ON d.run_id = r.id
                    GROUP BY r.id, r.created_at
                    ORDER BY r.created_at
                """).df().to_dict("records")
            else:
                cost_trend = []

        finally:
            con.close()

        return {
            "quality_trend": quality_trend,
            "step_stats": step_stats,
            "retention": retention,
            "cost_trend": cost_trend,
        }
