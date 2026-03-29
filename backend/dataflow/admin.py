from django.contrib import admin

from .models import AgentDecision, DataSource, Pipeline, ProcessingRun, QualityReport


class DataSourceInline(admin.TabularInline):
    model = DataSource
    extra = 0
    fields = ["name", "source_type", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "source_count", "run_count", "created_at"]
    list_filter = ["status"]
    search_fields = ["name"]
    inlines = [DataSourceInline]

    def source_count(self, obj):
        return obj.sources.count()
    source_count.short_description = "Fontes"

    def run_count(self, obj):
        return obj.runs.count()
    run_count.short_description = "Execuções"


@admin.register(ProcessingRun)
class ProcessingRunAdmin(admin.ModelAdmin):
    list_display = ["short_id", "pipeline", "status", "rows_in", "rows_out", "duration", "created_at"]
    list_filter = ["status", "trigger"]
    readonly_fields = ["started_at", "ended_at"]

    def short_id(self, obj):
        return obj.id.hex[:8]
    short_id.short_description = "ID"

    def duration(self, obj):
        d = obj.duration_seconds
        return f"{d:.1f}s" if d else "—"
    duration.short_description = "Duração"


@admin.register(AgentDecision)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ["step", "short_reasoning", "tokens_used", "latency_ms", "created_at"]
    list_filter = ["step"]

    def short_reasoning(self, obj):
        return obj.reasoning[:100]
    short_reasoning.short_description = "Raciocínio"


@admin.register(QualityReport)
class QualityReportAdmin(admin.ModelAdmin):
    list_display = ["run", "quality_score", "null_percentage", "duplicate_percentage", "schema_drift_detected"]
