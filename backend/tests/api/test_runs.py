"""
Testes de integração para ProcessingRunViewSet.

Cobre: listagem, filtros, detalhe, autenticação.
"""
import pytest

from tests.api.factories import (
    AgentDecisionFactory,
    PipelineFactory,
    ProcessingRunFactory,
    QualityReportFactory,
)


@pytest.mark.django_db
class TestRunAutenticacao:
    def test_list_sem_token_retorna_401(self, anon_client):
        resp = anon_client.get("/api/runs/")
        assert resp.status_code == 401

    def test_detail_sem_token_retorna_401(self, anon_client):
        run = ProcessingRunFactory()
        resp = anon_client.get(f"/api/runs/{run.id}/")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestRunList:
    def test_retorna_200_com_lista_paginada(self, auth_client):
        ProcessingRunFactory.create_batch(3)
        resp = auth_client.get("/api/runs/")
        assert resp.status_code == 200
        assert resp.data["count"] == 3

    def test_campos_obrigatorios_presentes(self, auth_client):
        ProcessingRunFactory()
        resp = auth_client.get("/api/runs/")
        item = resp.data["results"][0]
        for campo in ("id", "status", "trigger", "rows_in", "rows_out"):
            assert campo in item, f"Campo '{campo}' ausente na listagem"


@pytest.mark.django_db
class TestRunFiltros:
    def test_filtra_por_pipeline(self, auth_client):
        p1 = PipelineFactory()
        p2 = PipelineFactory()
        ProcessingRunFactory.create_batch(2, pipeline=p1)
        ProcessingRunFactory(pipeline=p2)
        resp = auth_client.get(f"/api/runs/?pipeline={p1.id}")
        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_filtra_por_status_success(self, auth_client):
        ProcessingRunFactory(status="success")
        ProcessingRunFactory(status="failed")
        ProcessingRunFactory(status="pending")
        resp = auth_client.get("/api/runs/?status=success")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_filtra_por_status_failed(self, auth_client):
        ProcessingRunFactory.create_batch(2, status="failed")
        ProcessingRunFactory(status="success")
        resp = auth_client.get("/api/runs/?status=failed")
        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_filtro_pipeline_inexistente_retorna_vazio(self, auth_client):
        import uuid
        ProcessingRunFactory.create_batch(2)
        resp = auth_client.get(f"/api/runs/?pipeline={uuid.uuid4()}")
        assert resp.status_code == 200
        assert resp.data["count"] == 0


@pytest.mark.django_db
class TestRunDetail:
    def test_retorna_run_por_id(self, auth_client):
        run = ProcessingRunFactory()
        resp = auth_client.get(f"/api/runs/{run.id}/")
        assert resp.status_code == 200
        assert resp.data["id"] == str(run.id)

    def test_id_inexistente_retorna_404(self, auth_client):
        import uuid
        resp = auth_client.get(f"/api/runs/{uuid.uuid4()}/")
        assert resp.status_code == 404

    def test_detalhe_inclui_decisions(self, auth_client):
        run = ProcessingRunFactory()
        AgentDecisionFactory.create_batch(3, run=run)
        resp = auth_client.get(f"/api/runs/{run.id}/")
        assert resp.status_code == 200
        assert len(resp.data["decisions"]) == 3

    def test_detalhe_inclui_quality_report(self, auth_client):
        run = ProcessingRunFactory()
        QualityReportFactory(run=run, quality_score=78.5)
        resp = auth_client.get(f"/api/runs/{run.id}/")
        assert resp.status_code == 200
        assert resp.data["quality_report"]["quality_score"] == 78.5

    def test_detalhe_sem_decisions_retorna_lista_vazia(self, auth_client):
        run = ProcessingRunFactory()
        resp = auth_client.get(f"/api/runs/{run.id}/")
        assert resp.status_code == 200
        assert resp.data["decisions"] == []

    def test_duration_seconds_calculado(self, auth_client):
        from django.utils import timezone
        import datetime
        run = ProcessingRunFactory(
            started_at=timezone.now() - datetime.timedelta(seconds=30),
            ended_at=timezone.now(),
        )
        resp = auth_client.get(f"/api/runs/{run.id}/")
        assert resp.status_code == 200
        assert resp.data["duration_seconds"] == pytest.approx(30, abs=2)
