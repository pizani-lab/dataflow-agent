"""
DataFlow Agent — API Serializers
"""
from rest_framework import serializers

from dataflow.models import (
    AgentDecision,
    DataLayer,
    DataSource,
    Pipeline,
    ProcessingRun,
    QualityReport,
)


# ──────────────────────────────────────────────
# Nested / Read-only
# ──────────────────────────────────────────────


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = [
            "id", "name", "source_type", "config",
            "detected_schema", "created_at",
        ]
        read_only_fields = ["id", "detected_schema", "created_at"]


class AgentDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentDecision
        fields = [
            "id", "step", "reasoning", "action",
            "tokens_used", "latency_ms", "created_at",
        ]


class DataLayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataLayer
        fields = ["id", "layer", "row_count", "schema", "sample", "stats", "created_at"]


class QualityReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityReport
        fields = [
            "id", "null_percentage", "duplicate_percentage",
            "schema_drift_detected", "quality_score", "details",
        ]


# ──────────────────────────────────────────────
# Processing Run
# ──────────────────────────────────────────────


class ProcessingRunListSerializer(serializers.ModelSerializer):
    """Versão compacta para listagem."""

    duration_seconds = serializers.ReadOnlyField()
    decision_count = serializers.SerializerMethodField()

    class Meta:
        model = ProcessingRun
        fields = [
            "id", "status", "trigger", "rows_in", "rows_out",
            "duration_seconds", "decision_count",
            "started_at", "ended_at", "created_at",
        ]

    def get_decision_count(self, obj):
        return obj.decisions.count()


class ProcessingRunDetailSerializer(serializers.ModelSerializer):
    """Versão completa com decisões, camadas e relatório de qualidade."""

    decisions = AgentDecisionSerializer(many=True, read_only=True)
    quality_report = QualityReportSerializer(read_only=True)
    layers = DataLayerSerializer(many=True, read_only=True)
    duration_seconds = serializers.ReadOnlyField()

    class Meta:
        model = ProcessingRun
        fields = [
            "id", "pipeline", "status", "trigger",
            "rows_in", "rows_out", "error_message",
            "duration_seconds", "started_at", "ended_at",
            "decisions", "quality_report", "layers", "created_at",
        ]


# ──────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────


class PipelineListSerializer(serializers.ModelSerializer):
    """Versão compacta para listagem."""

    source_count = serializers.SerializerMethodField()
    last_run_status = serializers.SerializerMethodField()
    total_runs = serializers.SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = [
            "id", "name", "description", "status",
            "schedule_cron", "source_count", "last_run_status",
            "total_runs", "created_at", "updated_at",
        ]

    def get_source_count(self, obj):
        return obj.sources.count()

    def get_last_run_status(self, obj):
        last = obj.runs.first()
        return last.status if last else None

    def get_total_runs(self, obj):
        return obj.runs.count()


class PipelineDetailSerializer(serializers.ModelSerializer):
    """Versão completa com fontes e últimos runs."""

    sources = DataSourceSerializer(many=True, read_only=True)
    recent_runs = serializers.SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = [
            "id", "name", "description", "status",
            "schedule_cron", "config", "sources",
            "recent_runs", "created_at", "updated_at",
        ]

    def get_recent_runs(self, obj):
        runs = obj.runs.all()[:5]
        return ProcessingRunListSerializer(runs, many=True).data


class PipelineCreateSerializer(serializers.ModelSerializer):
    """Para criação/edição de pipelines."""

    class Meta:
        model = Pipeline
        fields = ["id", "name", "description", "schedule_cron", "config"]
        read_only_fields = ["id"]


# ──────────────────────────────────────────────
# Upload (ação especial)
# ──────────────────────────────────────────────


class FileUploadSerializer(serializers.Serializer):
    """Serializer para upload de arquivos no pipeline."""

    file = serializers.FileField(help_text="Arquivo CSV ou JSON para processar.")
    context = serializers.CharField(
        required=False,
        default="",
        help_text="Contexto adicional sobre os dados.",
    )
