"""
Testes de integração para PipelineViewSet.

Cobre: CRUD, stats, autenticação.
"""
import pytest

from tests.api.factories import PipelineFactory, ProcessingRunFactory


@pytest.mark.django_db
class TestPipelineAutenticacao:
    """Requisições sem token devem retornar 401."""

    def test_list_sem_token_retorna_401(self, anon_client):
        resp = anon_client.get("/api/pipelines/")
        assert resp.status_code == 401

    def test_create_sem_token_retorna_401(self, anon_client):
        resp = anon_client.post("/api/pipelines/", {"name": "Teste"})
        assert resp.status_code == 401


@pytest.mark.django_db
class TestPipelineList:
    def test_retorna_200_com_lista_paginada(self, auth_client):
        PipelineFactory.create_batch(3)
        resp = auth_client.get("/api/pipelines/")
        assert resp.status_code == 200
        assert resp.data["count"] == 3

    def test_lista_vazia_retorna_count_zero(self, auth_client):
        resp = auth_client.get("/api/pipelines/")
        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_campos_obrigatorios_presentes(self, auth_client):
        PipelineFactory()
        resp = auth_client.get("/api/pipelines/")
        item = resp.data["results"][0]
        for campo in ("id", "name", "status", "total_runs", "source_count"):
            assert campo in item, f"Campo '{campo}' ausente na listagem"


@pytest.mark.django_db
class TestPipelineCreate:
    def test_cria_com_dados_validos(self, auth_client):
        payload = {"name": "Pipeline ETL", "description": "Teste de criação"}
        resp = auth_client.post("/api/pipelines/", payload)
        assert resp.status_code == 201
        assert resp.data["name"] == "Pipeline ETL"

    def test_nome_obrigatorio(self, auth_client):
        resp = auth_client.post("/api/pipelines/", {"description": "sem nome"})
        assert resp.status_code == 400
        assert "name" in resp.data

    def test_status_padrao_e_draft(self, auth_client):
        resp = auth_client.post("/api/pipelines/", {"name": "Novo"})
        from dataflow.models import Pipeline
        assert resp.data.get("id") is not None
        pipeline = Pipeline.objects.get(id=resp.data["id"])
        assert pipeline.status == Pipeline.Status.DRAFT


@pytest.mark.django_db
class TestPipelineDetail:
    def test_retorna_pipeline_por_id(self, auth_client):
        pipeline = PipelineFactory()
        resp = auth_client.get(f"/api/pipelines/{pipeline.id}/")
        assert resp.status_code == 200
        assert resp.data["id"] == str(pipeline.id)
        assert resp.data["name"] == pipeline.name

    def test_id_inexistente_retorna_404(self, auth_client):
        import uuid
        resp = auth_client.get(f"/api/pipelines/{uuid.uuid4()}/")
        assert resp.status_code == 404

    def test_detalhe_inclui_recent_runs(self, auth_client):
        pipeline = PipelineFactory()
        ProcessingRunFactory.create_batch(2, pipeline=pipeline)
        resp = auth_client.get(f"/api/pipelines/{pipeline.id}/")
        assert "recent_runs" in resp.data
        assert len(resp.data["recent_runs"]) == 2


@pytest.mark.django_db
class TestPipelineUpdate:
    def test_patch_atualiza_nome(self, auth_client):
        pipeline = PipelineFactory(name="Antigo")
        resp = auth_client.patch(f"/api/pipelines/{pipeline.id}/", {"name": "Novo"})
        assert resp.status_code == 200
        pipeline.refresh_from_db()
        assert pipeline.name == "Novo"

    def test_put_requer_nome(self, auth_client):
        pipeline = PipelineFactory()
        resp = auth_client.put(f"/api/pipelines/{pipeline.id}/", {"description": "só desc"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestPipelineDelete:
    def test_delete_retorna_204(self, auth_client):
        pipeline = PipelineFactory()
        resp = auth_client.delete(f"/api/pipelines/{pipeline.id}/")
        assert resp.status_code == 204

    def test_delete_remove_do_banco(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory()
        auth_client.delete(f"/api/pipelines/{pipeline.id}/")
        assert not Pipeline.objects.filter(id=pipeline.id).exists()


@pytest.mark.django_db
class TestPipelineFiltros:
    def test_busca_por_nome_parcial(self, auth_client):
        PipelineFactory(name="Vendas ETL")
        PipelineFactory(name="Marketing Feed")
        resp = auth_client.get("/api/pipelines/?search=vendas")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["name"] == "Vendas ETL"

    def test_busca_case_insensitive(self, auth_client):
        PipelineFactory(name="Vendas ETL")
        resp = auth_client.get("/api/pipelines/?search=VENDAS")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_filtra_por_status_active(self, auth_client):
        from dataflow.models import Pipeline
        PipelineFactory(status=Pipeline.Status.ACTIVE)
        PipelineFactory(status=Pipeline.Status.DRAFT)
        PipelineFactory(status=Pipeline.Status.DRAFT)
        resp = auth_client.get("/api/pipelines/?status=active")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_busca_sem_resultado_retorna_vazio(self, auth_client):
        PipelineFactory.create_batch(2)
        resp = auth_client.get("/api/pipelines/?search=xyzinexistente")
        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_busca_e_status_combinados(self, auth_client):
        from dataflow.models import Pipeline
        PipelineFactory(name="Vendas ETL", status=Pipeline.Status.ACTIVE)
        PipelineFactory(name="Vendas Log", status=Pipeline.Status.DRAFT)
        resp = auth_client.get("/api/pipelines/?search=vendas&status=active")
        assert resp.status_code == 200
        assert resp.data["count"] == 1


@pytest.mark.django_db
class TestPipelinePause:
    def test_pausa_pipeline_ativo(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory(status=Pipeline.Status.ACTIVE)
        resp = auth_client.post(f"/api/pipelines/{pipeline.id}/pause/")
        assert resp.status_code == 200
        assert resp.data["status"] == "paused"
        pipeline.refresh_from_db()
        assert pipeline.status == Pipeline.Status.PAUSED

    def test_nao_pausa_pipeline_draft(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory(status=Pipeline.Status.DRAFT)
        resp = auth_client.post(f"/api/pipelines/{pipeline.id}/pause/")
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_nao_pausa_pipeline_ja_pausado(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory(status=Pipeline.Status.PAUSED)
        resp = auth_client.post(f"/api/pipelines/{pipeline.id}/pause/")
        assert resp.status_code == 400
        assert "error" in resp.data


@pytest.mark.django_db
class TestPipelineResume:
    def test_reativa_pipeline_pausado(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory(status=Pipeline.Status.PAUSED)
        resp = auth_client.post(f"/api/pipelines/{pipeline.id}/resume/")
        assert resp.status_code == 200
        assert resp.data["status"] == "active"
        pipeline.refresh_from_db()
        assert pipeline.status == Pipeline.Status.ACTIVE

    def test_nao_reativa_pipeline_ativo(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory(status=Pipeline.Status.ACTIVE)
        resp = auth_client.post(f"/api/pipelines/{pipeline.id}/resume/")
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_nao_reativa_pipeline_draft(self, auth_client):
        from dataflow.models import Pipeline
        pipeline = PipelineFactory(status=Pipeline.Status.DRAFT)
        resp = auth_client.post(f"/api/pipelines/{pipeline.id}/resume/")
        assert resp.status_code == 400
        assert "error" in resp.data


@pytest.mark.django_db
class TestPipelineStats:
    def test_stats_pipeline_sem_runs(self, auth_client):
        pipeline = PipelineFactory()
        resp = auth_client.get(f"/api/pipelines/{pipeline.id}/stats/")
        assert resp.status_code == 200
        assert resp.data["total_runs"] == 0
        assert resp.data["success_rate"] == 0
        assert resp.data["total_cost_usd"] == 0

    def test_stats_com_runs_success_e_failed(self, auth_client):
        pipeline = PipelineFactory()
        ProcessingRunFactory(pipeline=pipeline, status="success", rows_in=100, rows_out=90)
        ProcessingRunFactory(pipeline=pipeline, status="failed",  rows_in=50,  rows_out=0)
        resp = auth_client.get(f"/api/pipelines/{pipeline.id}/stats/")
        assert resp.status_code == 200
        assert resp.data["total_runs"] == 2
        assert resp.data["success_rate"] == 50.0
        assert resp.data["failed_runs"] == 1
        assert resp.data["total_rows_processed"] == 150
