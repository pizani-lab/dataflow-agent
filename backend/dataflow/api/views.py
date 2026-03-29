"""
DataFlow Agent — API Views
"""
import io
import os

import pandas as pd
from django.http import HttpResponse
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework import permissions as drf_permissions
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from dataflow.analytics.costs import compute_cost
from dataflow.analytics.engine import DuckDBAnalytics
from dataflow.models import AgentDecision, DataSource, Pipeline, ProcessingRun
from dataflow.processing.tasks import run_pipeline_task

_SAMPLE_CHAR_LIMIT = 50_000
_SUPPORTED_EXTENSIONS = {".csv", ".json", ".xlsx", ".xls", ".parquet"}


def _parse_uploaded_file(uploaded_file) -> tuple[str, int, str]:
    """
    Converte arquivo para CSV string pronto para o pipeline.

    Suporta: .csv, .json, .xlsx, .xls, .parquet

    Args:
        uploaded_file: InMemoryUploadedFile ou similar do Django.

    Returns:
        Tupla de (csv_string, row_count, detected_format).

    Raises:
        ValueError: formato não suportado.
    """
    _, ext = os.path.splitext(uploaded_file.name.lower())

    if ext not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Formato '{ext}' não suportado. Use: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(io.BytesIO(uploaded_file.read()), engine="openpyxl")
        csv_content = df.to_csv(index=False)
        return csv_content[:_SAMPLE_CHAR_LIMIT], len(df), "excel"

    if ext == ".parquet":
        df = pd.read_parquet(io.BytesIO(uploaded_file.read()))
        csv_content = df.to_csv(index=False)
        return csv_content[:_SAMPLE_CHAR_LIMIT], len(df), "parquet"

    # CSV ou JSON — lê como texto
    content = uploaded_file.read().decode("utf-8", errors="replace")
    row_count = max(len(content.strip().split("\n")) - 1, 0)
    return content[:_SAMPLE_CHAR_LIMIT], row_count, ext.lstrip(".") or "csv"

from .serializers import (
    AgentDecisionSerializer,
    DataSourceSerializer,
    FileUploadSerializer,
    PipelineCreateSerializer,
    PipelineDetailSerializer,
    PipelineListSerializer,
    ProcessingRunDetailSerializer,
    ProcessingRunListSerializer,
)


class PipelineViewSet(viewsets.ModelViewSet):
    """
    CRUD de Pipelines + ações customizadas.

    list:   GET /api/pipelines/
    create: POST /api/pipelines/
    detail: GET /api/pipelines/{id}/
    update: PUT /api/pipelines/{id}/
    delete: DELETE /api/pipelines/{id}/
    upload: POST /api/pipelines/{id}/upload/
    trigger: POST /api/pipelines/{id}/trigger/
    stats: GET /api/pipelines/{id}/stats/
    """

    queryset = Pipeline.objects.prefetch_related("sources", "runs").all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return PipelineListSerializer
        if self.action in ("create", "update", "partial_update"):
            return PipelineCreateSerializer
        return PipelineDetailSerializer

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request, pk=None):
        """
        Upload de arquivo para um pipeline.
        Cria DataSource + dispara processamento assíncrono.
        """
        pipeline = self.get_object()
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        context = serializer.validated_data.get("context", "")

        # Converte para CSV string (suporta CSV, JSON, Excel, Parquet)
        try:
            csv_content, row_count, detected_format = _parse_uploaded_file(uploaded_file)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Cria a fonte de dados com metadados do arquivo original
        source = DataSource.objects.create(
            pipeline=pipeline,
            name=uploaded_file.name,
            source_type=DataSource.SourceType.FILE_UPLOAD,
            config={
                "original_filename": uploaded_file.name,
                "content_type": uploaded_file.content_type,
                "size_bytes": uploaded_file.size,
                "detected_format": detected_format,
                "original_row_count": row_count,
                "cached_sample": csv_content,  # usado pelo trigger action
            },
        )

        # Cria um run e dispara processamento
        run = ProcessingRun.objects.create(
            pipeline=pipeline,
            trigger="upload",
            rows_in=row_count,
        )

        # Dispara a task do Celery
        run_pipeline_task.delay(
            run_id=str(run.id),
            data_content=csv_content,
            context=context,
        )

        return Response(
            {
                "message": "Upload recebido. Processamento iniciado.",
                "source_id": str(source.id),
                "run_id": str(run.id),
                "detected_format": detected_format,
                "row_count": row_count,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def trigger(self, request, pk=None):
        """Dispara uma execução manual do pipeline."""
        pipeline = self.get_object()

        # Pega a última fonte de dados como referência
        source = pipeline.sources.first()
        if not source:
            return Response(
                {"error": "Pipeline não tem fontes de dados configuradas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run = ProcessingRun.objects.create(
            pipeline=pipeline,
            trigger="manual",
        )

        run_pipeline_task.delay(
            run_id=str(run.id),
            data_content=source.config.get("cached_sample", ""),
            context=f"Pipeline: {pipeline.name}. Re-execução manual.",
        )

        return Response(
            {
                "message": "Execução manual disparada.",
                "run_id": str(run.id),
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Pausa um pipeline ativo."""
        pipeline = self.get_object()
        if pipeline.status != Pipeline.Status.ACTIVE:
            return Response(
                {"error": "Apenas pipelines ativos podem ser pausados."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pipeline.status = Pipeline.Status.PAUSED
        pipeline.save(update_fields=["status", "updated_at"])
        return Response({"status": pipeline.status})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Reativa um pipeline pausado."""
        pipeline = self.get_object()
        if pipeline.status != Pipeline.Status.PAUSED:
            return Response(
                {"error": "Apenas pipelines pausados podem ser reativados."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pipeline.status = Pipeline.Status.ACTIVE
        pipeline.save(update_fields=["status", "updated_at"])
        return Response({"status": pipeline.status})

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        """
        Analytics analíticas via DuckDB para um pipeline.

        Retorna quality_trend (com média móvel), step_stats (tokens por step)
        e retention (retenção de linhas por run).
        """
        pipeline = self.get_object()
        engine = DuckDBAnalytics()
        data = engine.pipeline_analytics(str(pipeline.id))
        return Response(data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Estatísticas resumidas do pipeline."""
        pipeline = self.get_object()
        runs = pipeline.runs.all()

        total = runs.count()
        success = runs.filter(status=ProcessingRun.Status.SUCCESS).count()
        failed = runs.filter(status=ProcessingRun.Status.FAILED).count()

        total_rows_in = sum(r.rows_in for r in runs)
        total_rows_out = sum(r.rows_out for r in runs)
        total_tokens = sum(
            d.tokens_used
            for r in runs
            for d in r.decisions.all()
        )

        return Response({
            "total_runs": total,
            "success_rate": round(success / total * 100, 1) if total else 0,
            "failed_runs": failed,
            "total_rows_processed": total_rows_in,
            "total_rows_output": total_rows_out,
            "total_tokens_used": total_tokens,
            "total_cost_usd": compute_cost(total_tokens),
        })


class ProcessingRunViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Consulta de runs (somente leitura).

    list:   GET /api/runs/
    detail: GET /api/runs/{id}/
    export: GET /api/runs/{id}/export/?format=csv|parquet
    """

    queryset = (
        ProcessingRun.objects
        .select_related("pipeline", "quality_report")
        .prefetch_related("decisions")
        .all()
    )
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProcessingRunDetailSerializer
        return ProcessingRunListSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        pipeline_id = self.request.query_params.get("pipeline")
        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)

        run_status = self.request.query_params.get("status")
        if run_status:
            qs = qs.filter(status=run_status)

        return qs

    @action(detail=True, methods=["get"], url_path="export")
    def export(self, request, pk=None):
        """
        Download dos dados processados.

        Query params:
            format: "csv" (padrão) ou "parquet"

        Requer que o run tenha sido concluído com sucesso.
        """
        run = self.get_object()

        if run.status != ProcessingRun.Status.SUCCESS:
            return Response(
                {"error": "Export disponível apenas para runs com status 'success'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        quality_report = getattr(run, "quality_report", None)
        if not quality_report:
            return Response(
                {"error": "Relatório de qualidade não encontrado para este run."},
                status=status.HTTP_404_NOT_FOUND,
            )

        processed_csv = quality_report.details.get("processed_csv")
        if not processed_csv:
            return Response(
                {"error": "Dados processados não disponíveis. Execute um novo run."},
                status=status.HTTP_404_NOT_FOUND,
            )

        export_format = request.query_params.get("format", "csv").lower()
        pipeline_name = run.pipeline.name.replace(" ", "_").lower()
        base_filename = f"dataflow_{pipeline_name}_run_{str(run.id)[:8]}"

        if export_format == "parquet":
            df = pd.read_csv(io.StringIO(processed_csv))
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            buf.seek(0)
            response = HttpResponse(
                buf.read(),
                content_type="application/octet-stream",
            )
            response["Content-Disposition"] = f'attachment; filename="{base_filename}.parquet"'
            return response

        # Padrão: CSV
        response = HttpResponse(processed_csv, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{base_filename}.csv"'
        return response


class DataSourceViewSet(viewsets.ModelViewSet):
    """CRUD de fontes de dados."""

    queryset = DataSource.objects.select_related("pipeline").all()
    serializer_class = DataSourceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        pipeline_id = self.request.query_params.get("pipeline")
        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)
        return qs


class AgentDecisionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Consulta de decisões do agente (somente leitura)."""

    queryset = AgentDecision.objects.select_related("run").all()
    serializer_class = AgentDecisionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        run_id = self.request.query_params.get("run")
        if run_id:
            qs = qs.filter(run_id=run_id)
        return qs


# ──────────────────────────────────────────────
# Health Check - Status do Ollama
# ──────────────────────────────────────────────
from rest_framework.decorators import api_view

@api_view(["GET"])
@permission_classes([])
def health_check(request):
    """
    Endpoint de health check que verifica a comunicação com Ollama.
    Retorna o status do Ollama, URL, modelo e mensagens de erro se houver.
    """
    import httpx
    from django.conf import settings

    ollama_url = getattr(settings, "OLLAMA_URL", "http://187.77.226.47:7143")
    ollama_model = getattr(settings, "OLLAMA_MODEL", "qwen2.5:3b")
    print(ollama_model)
    print(ollama_url)

    result = {
        "ollama_url": ollama_url,
        "ollama_model": ollama_model,
        "status": "unhealthy",
        "error": None,
    }

    try:
        # Tenta fazer uma requisição simples para o Ollama
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        if resp.status_code == 200:
            result["status"] = "healthy"
            # Verifica se o modelo está disponível
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            if ollama_model not in model_names:
                result["error"] = f"Modelo '{ollama_model}' não encontrado na lista de modelos disponíveis"
                result["available_models"] = model_names
        else:
            result["error"] = f"Ollama retornou status {resp.status_code}"
    except httpx.ConnectError:
        result["error"] = f"Não foi possível conectar ao Ollama em {ollama_url}"
    except httpx.TimeoutException:
        result["error"] = f"Timeout ao conectar ao Ollama em {ollama_url}"
    except Exception as e:
        result["error"] = str(e)

    status_code = 200 if result["status"] == "healthy" else 503
    return Response(result, status=status_code)
