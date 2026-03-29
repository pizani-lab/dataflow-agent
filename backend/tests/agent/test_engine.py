"""
Testes para o engine do DataFlow Agent - comunicação com Ollama.

Estes testes usam mock para evitar chamadas reais ao Ollama.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import override_settings


class TestDataFlowAgent:
    """Testes para o DataFlowAgent."""

    @override_settings(OLLAMA_URL="http://localhost:11434", OLLAMA_MODEL="qwen2.5:3b")
    @patch("dataflow.agent.engine.httpx.post")
    @patch("dataflow.agent.engine._get_openai_tools")
    def test_agent_faz_chamada_para_ollama(self, mock_tools, mock_post):
        """Testa que o agente faz chamada HTTP para o Ollama."""
        from dataflow.agent.engine import DataFlowAgent

        # Mock das tools
        mock_tools.return_value = [
            {"type": "function", "function": {"name": "detect_schema"}}
        ]

        # Mock da resposta do Ollama
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Analisando os dados...",
                    "tool_calls": []
                }
            }],
            "usage": {"total_tokens": 100},
        }
        mock_post.return_value = mock_response

        agent = DataFlowAgent()
        result = agent.process(sample_data="nome,idade\nAlice,30", context="")

        # Verifica que fez a chamada
        mock_post.assert_called_once()

        # Verifica que recebeu uma resposta
        assert result is not None
        assert "iterations" in result

    @override_settings(OLLAMA_URL="http://localhost:11434", OLLAMA_MODEL="qwen2.5:3b")
    @patch("dataflow.agent.engine.httpx.post")
    @patch("dataflow.agent.engine._get_openai_tools")
    def test_agent_trata_erro_de_conexao(self, mock_tools, mock_post):
        """Testa que o agente trata erro de conexão com Ollama."""
        import httpx
        from dataflow.agent.engine import DataFlowAgent

        mock_tools.return_value = []
        mock_post.side_effect = httpx.ConnectError("Connection failed")

        agent = DataFlowAgent()
        result = agent.process(sample_data="nome,idade\nAlice,30", context="")

        assert "error" in result

    @override_settings(OLLAMA_URL="http://localhost:11434", OLLAMA_MODEL="qwen2.5:3b")
    @patch("dataflow.agent.engine.httpx.post")
    @patch("dataflow.agent.engine._get_openai_tools")
    def test_agent_faz_retry_em_erro_http(self, mock_tools, mock_post):
        """Testa que o agente faz retry em caso de erro HTTP."""
        import httpx
        from dataflow.agent.engine import DataFlowAgent

        mock_tools.return_value = []

        # Primeira chamada falha, segunda succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 429
        mock_response_fail.response = MagicMock()
        mock_response_fail.response.status_code = 429

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "OK", "tool_calls": []}}],
            "usage": {"total_tokens": 10},
        }

        mock_post.side_effect = [
            httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=mock_response_fail),
            mock_response_success
        ]

        agent = DataFlowAgent()
        result = agent.process(sample_data="nome,idade\nAlice,30", context="")

        # Deve ter tentado 2 vezes
        assert mock_post.call_count == 2


class TestRetryWithBackoff:
    """Testes para o decorator _retry_with_backoff."""

    @patch("dataflow.agent.engine.time.sleep")
    def test_retry_sucesso_na_primeira_tentativa(self, mock_sleep):
        """Testa que não faz retry quando funciona na primeira."""
        from dataflow.agent.engine import _retry_with_backoff

        @_retry_with_backoff(max_attempts=3, backoff=0.1)
        def funcao_sucesso():
            return "ok"

        result = funcao_sucesso()
        assert result == "ok"
        mock_sleep.assert_not_called()

    @patch("dataflow.agent.engine.time.sleep")
    def test_retry_falha_e_tenta_novamente(self, mock_sleep):
        """Testa que faz retry após falha."""
        import httpx
        from dataflow.agent.engine import _retry_with_backoff

        @_retry_with_backoff(max_attempts=3, backoff=0.1)
        def funcao_falha_primeiro():
            if not hasattr(funcao_falha_primeiro, 'called'):
                funcao_falha_primeiro.called = False
            if not funcao_falha_primeiro.called:
                funcao_falha_primeiro.called = True
                raise httpx.RequestError("fail")
            return "ok"

        result = funcao_falha_primeiro()
        assert result == "ok"
        assert mock_sleep.call_count == 1

    @patch("dataflow.agent.engine.time.sleep")
    def test_retry_esgota_todas_tentativas(self, mock_sleep):
        """Testa que lança exceção após todas as tentativas falharem."""
        import httpx
        from dataflow.agent.engine import _retry_with_backoff

        @_retry_with_backoff(max_attempts=3, backoff=0.1)
        def funcao_sempre_falha():
            raise httpx.RequestError("fail")

        with pytest.raises(httpx.RequestError):
            funcao_sempre_falha()

        # Deve ter tentado 3 vezes (2 sleeps entre tentativas)
        assert mock_sleep.call_count == 2


class TestOllamaConfiguration:
    """Testes para validar configuração do Ollama."""

    def test_valida_url_padrao(self):
        """Testa que a URL padrão está correta."""
        from django.conf import settings
        url = getattr(settings, "OLLAMA_URL", None)
        assert url == "http://0.0.0.0:11434"

    def test_valida_modelo_padrao(self):
        """Testa que o modelo padrão está configurado."""
        from django.conf import settings
        model = getattr(settings, "OLLAMA_MODEL", None)
        assert model == "qwen2.5:3b"

    @override_settings(OLLAMA_MODEL="custom-model")
    def test_pode_sobrescrever_modelo(self):
        """Testa que o modelo pode ser sobrescrito."""
        from django.conf import settings
        model = getattr(settings, "OLLAMA_MODEL", None)
        assert model == "custom-model"