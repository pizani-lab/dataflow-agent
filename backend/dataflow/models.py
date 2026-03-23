"""
DataFlow Agent — Domain Models

Camadas de dados: bronze (raw) → silver (clean) → gold (aggregated)
O agente LLM decide o plano de transformação para cada pipeline run.
"""
import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Base abstrata com timestamps automáticos."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ──────────────────────────────────────────────
# Pipeline & Data Sources
# ──────────────────────────────────────────────


class Pipeline(TimeStampedModel):
    """
    Um pipeline representa um fluxo de dados completo:
    ingestão → classificação → transformação → carga.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        ACTIVE = "active", "Ativo"
        PAUSED = "paused", "Pausado"
        ERROR = "error", "Com Erro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    schedule_cron = models.CharField(
        max_length=100,
        blank=True,
        help_text="Expressão cron para execução agendada (ex: '0 */6 * * *')",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configurações extras do pipeline (target schema, etc.)",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.status})"


class DataSource(TimeStampedModel):
    """
    Fonte de dados conectada a um pipeline.
    Suporta: file_upload, api_endpoint, webhook, database.
    """

    class SourceType(models.TextChoices):
        FILE_UPLOAD = "file_upload", "Upload de Arquivo"
        API_ENDPOINT = "api_endpoint", "Endpoint de API"
        WEBHOOK = "webhook", "Webhook"
        DATABASE = "database", "Banco de Dados"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    config = models.JSONField(
        default=dict,
        help_text="Configuração da fonte (URL, headers, file_path, etc.)",
    )
    detected_schema = models.JSONField(
        null=True,
        blank=True,
        help_text="Schema detectado automaticamente pelo agente.",
    )

    def __str__(self):
        return f"{self.name} ({self.source_type})"


# ──────────────────────────────────────────────
# Processing Runs & Agent Decisions
# ──────────────────────────────────────────────


class ProcessingRun(TimeStampedModel):
    """
    Uma execução do pipeline. Rastreia métricas de volume e duração.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        RUNNING = "running", "Executando"
        SUCCESS = "success", "Sucesso"
        FAILED = "failed", "Falhou"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    rows_in = models.IntegerField(default=0)
    rows_out = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    trigger = models.CharField(
        max_length=50,
        default="manual",
        help_text="O que disparou esta execução (manual, schedule, webhook).",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id.hex[:8]} — {self.status}"

    @property
    def duration_seconds(self):
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None


class AgentDecision(TimeStampedModel):
    """
    Registro de cada decisão tomada pelo agente LLM durante um run.
    Funciona como um log de raciocínio auditável.
    """

    class Step(models.TextChoices):
        CLASSIFY = "classify", "Classificação de Schema"
        QUALITY = "quality", "Análise de Qualidade"
        PLAN = "plan", "Planejamento de Transformação"
        EXECUTE = "execute", "Execução de Transformação"
        VALIDATE = "validate", "Validação Final"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="decisions")
    step = models.CharField(max_length=20, choices=Step.choices)
    reasoning = models.TextField(help_text="Raciocínio do agente em linguagem natural.")
    action = models.JSONField(help_text="Ação decidida pelo agente (tool call, transform, etc.).")
    tokens_used = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.step}] {self.reasoning[:80]}..."


# ──────────────────────────────────────────────
# Data Layers (Bronze / Silver / Gold)
# ──────────────────────────────────────────────


class DataLayer(TimeStampedModel):
    """
    Armazena uma amostra e estatísticas dos dados em cada camada do pipeline.

    bronze → dados raw como recebidos
    silver → dados limpos após transformações do agente
    gold   → métricas agregadas e transformações aplicadas
    """

    class Layer(models.TextChoices):
        BRONZE = "bronze", "Bronze (Raw)"
        SILVER = "silver", "Silver (Clean)"
        GOLD   = "gold",   "Gold (Aggregated)"

    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run       = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="layers")
    layer     = models.CharField(max_length=10, choices=Layer.choices)
    row_count = models.IntegerField(default=0)
    schema    = models.JSONField(default=dict, help_text="Colunas e tipos detectados.")
    sample    = models.JSONField(default=list, help_text="Primeiras 10 linhas como lista de dicts.")
    stats     = models.JSONField(default=dict, help_text="Estatísticas resumidas da camada.")

    class Meta:
        ordering = ["created_at"]
        unique_together = [("run", "layer")]

    def __str__(self):
        return f"[{self.layer.upper()}] Run {self.run.id.hex[:8]} — {self.row_count} rows"


# ──────────────────────────────────────────────
# Quality Reports
# ──────────────────────────────────────────────


class QualityReport(TimeStampedModel):
    """
    Relatório de qualidade gerado pelo agente para cada run.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.OneToOneField(ProcessingRun, on_delete=models.CASCADE, related_name="quality_report")
    null_percentage = models.FloatField(default=0.0)
    duplicate_percentage = models.FloatField(default=0.0)
    schema_drift_detected = models.BooleanField(default=False)
    quality_score = models.FloatField(
        default=0.0,
        help_text="Score de 0 a 100 atribuído pelo agente.",
    )
    details = models.JSONField(
        default=dict,
        help_text="Detalhes granulares por coluna.",
    )

    def __str__(self):
        return f"Quality: {self.quality_score:.1f}/100 — Run {self.run.id.hex[:8]}"
