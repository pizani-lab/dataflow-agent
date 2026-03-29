"""
Seed demo data para desenvolvimento.

Usage:
    python manage.py seed_demo
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from dataflow.models import (
    AgentDecision,
    DataSource,
    Pipeline,
    ProcessingRun,
    QualityReport,
)


class Command(BaseCommand):
    help = "Popula o banco com dados demo para desenvolvimento."

    def handle(self, *args, **options):
        self.stdout.write("Criando dados demo...")

        # Pipeline 1: Vendas
        p1 = Pipeline.objects.create(
            name="Pipeline de Vendas",
            description="Processa CSVs de vendas mensais, limpa e agrega por região.",
            status=Pipeline.Status.ACTIVE,
            schedule_cron="0 6 * * 1",
        )
        DataSource.objects.create(
            pipeline=p1,
            name="vendas_2024.csv",
            source_type=DataSource.SourceType.FILE_UPLOAD,
            config={"original_filename": "vendas_2024.csv", "size_bytes": 245000},
            detected_schema={
                "columns": [
                    {"name": "data", "dtype": "datetime64", "null_pct": 0},
                    {"name": "regiao", "dtype": "object", "null_pct": 2.1},
                    {"name": "produto", "dtype": "object", "null_pct": 0},
                    {"name": "valor", "dtype": "float64", "null_pct": 0.5},
                    {"name": "quantidade", "dtype": "int64", "null_pct": 0},
                ],
            },
        )

        # Run com sucesso
        run1 = ProcessingRun.objects.create(
            pipeline=p1,
            status=ProcessingRun.Status.SUCCESS,
            started_at=timezone.now(),
            ended_at=timezone.now(),
            rows_in=15420,
            rows_out=15380,
            trigger="upload",
        )
        AgentDecision.objects.create(
            run=run1, step="classify",
            reasoning="Detectei um CSV com 5 colunas: data, regiao, produto, valor, quantidade. Schema parece ser de vendas transacionais.",
            action={"tool": "detect_schema", "output": {"columns": 5, "rows": 15420}},
            tokens_used=340, latency_ms=820,
        )
        AgentDecision.objects.create(
            run=run1, step="quality",
            reasoning="Encontrei 2.1% de nulos na coluna 'regiao' e 0.5% em 'valor'. Sem duplicatas detectadas. Qualidade geral boa.",
            action={"tool": "assess_quality", "output": {"null_pct": 2.1, "dup_pct": 0}},
            tokens_used=280, latency_ms=650,
        )
        AgentDecision.objects.create(
            run=run1, step="plan",
            reasoning="Plano: 1) Preencher nulos de 'regiao' com 'Não informado'. 2) Remover linhas com 'valor' nulo. 3) Cast 'data' para datetime.",
            action={"tool": "plan_transformation", "output": {"steps": 3}},
            tokens_used=420, latency_ms=900,
        )
        AgentDecision.objects.create(
            run=run1, step="validate",
            reasoning="Dados validados. 15380 linhas de 15420 (40 removidas por valor nulo). Score de qualidade: 92/100.",
            action={"tool": "validate_output", "output": {"quality_score": 92.0}},
            tokens_used=190, latency_ms=450,
        )
        QualityReport.objects.create(
            run=run1, quality_score=92.0,
            null_percentage=2.1, duplicate_percentage=0,
            details={"removed_rows": 40, "filled_nulls": 324},
        )

        # Pipeline 2: Logs de API
        p2 = Pipeline.objects.create(
            name="Pipeline de Logs",
            description="Ingere e analisa logs de API para detectar padrões de erro.",
            status=Pipeline.Status.ACTIVE,
        )
        DataSource.objects.create(
            pipeline=p2,
            name="api_logs_endpoint",
            source_type=DataSource.SourceType.API_ENDPOINT,
            config={"url": "https://api.example.com/logs", "method": "GET"},
        )

        # Pipeline 3: Draft
        Pipeline.objects.create(
            name="Pipeline de Clientes",
            description="Unifica dados de clientes de múltiplas fontes.",
            status=Pipeline.Status.DRAFT,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Demo criado: {Pipeline.objects.count()} pipelines, "
            f"{ProcessingRun.objects.count()} runs, "
            f"{AgentDecision.objects.count()} decisões."
        ))
