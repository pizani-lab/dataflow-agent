"""
Testes para o endpoint de health check do Ollama.
"""
import pytest
from django.test import override_settings
from unittest.mock import patch, MagicMock

from dataflow.api.views import health_check


class TestHealthCheck:
    """Testes para o endpoint /api/health/"""

    @patch("dataflow.api.views.httpx.get")
    def test_retorna_healthy_quando_ollama_responde(self, mock_get):
        """Testa que retorna status healthy quando Ollama está acessível."""
        # Mock da resposta do Ollama com modelos disponíveis
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5:3b"},
                {"name": "llama3:8b"},
            ]
        }
        mock_get.return_value = mock_response

        request = MagicMock()
        response = health_check(request)

        assert response.status_code == 200
        assert response.data["status"] == "healthy"
        assert response.data["ollama_url"] == "http://0.0.0.0:11434"

    @patch("dataflow.api.views.httpx.get")
    def test_retorna_unhealthy_quando_nao_conecta(self, mock_get):
        """Testa que retorna status unhealthy quando Ollama não responde."""
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection failed")

        request = MagicMock()
        response = health_check(request)

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"
        assert "Connection failed" in response.data["error"]

    @patch("dataflow.api.views.httpx.get")
    def test_retorna_unhealthy_com_timeout(self, mock_get):
        """Testa que retorna status unhealthy com timeout."""
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        request = MagicMock()
        response = health_check(request)

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"
        assert "Timeout" in response.data["error"]

    @patch("dataflow.api.views.httpx.get")
    def test_retorna_unhealthy_modelo_nao_encontrado(self, mock_get):
        """Testa que retorna warning quando modelo não está disponível."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:8b"},  # Modelo configurado não está na lista
            ]
        }
        mock_get.return_value = mock_response

        request = MagicMock()
        response = health_check(request)

        assert response.status_code == 200  # Still 200, mas com warning
        assert response.data["status"] == "healthy"  # Servidor responde
        assert response.data["error"] is not None
        assert "não encontrado" in response.data["error"]

    @patch("dataflow.api.views.httpx.get")
    def test_retorna_unhealthy_status_code_erro(self, mock_get):
        """Testa que retorna unhealthy quando Ollama retorna erro."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        request = MagicMock()
        response = health_check(request)

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"

    def test_retorna_configuracoes_corretas(self):
        """Testa que retorna as configurações do settings."""
        with override_settings(OLLAMA_URL="http://custom:11434", OLLAMA_MODEL="custom-model"):
            with patch("dataflow.api.views.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"models": []}
                mock_get.return_value = mock_response

                request = MagicMock()
                response = health_check(request)

                assert response.data["ollama_url"] == "http://custom:11434"
                assert response.data["ollama_model"] == "custom-model"