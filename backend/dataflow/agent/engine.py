"""
DataFlow Agent — Engine

Orquestra o agente LLM com tool use para processar dados autonomamente.
O loop principal: envia contexto → recebe tool_use → executa → retorna resultado → repete.

Suporta Ollama local e cloud (OpenAI-compatible API) com retry e cache.
"""
import json
import logging
import time
from collections import deque
from functools import lru_cache
from dotenv import load_dotenv,find_dotenv
import httpx

from config import settings
from config.settings import AGENT_MAX_DECISIONS, AGENT_RETRY_ATTEMPTS, AGENT_RETRY_BACKOFF, AGENT_TIMEOUT, \
    AGENT_MAX_ITERATIONS, AGENT_MAX_DATA_CHARS

load_dotenv(find_dotenv())


from .tools import TOOL_HANDLERS, TOOLS

logger = logging.getLogger(__name__)

# Retry com backoff exponencial
def _retry_with_backoff(max_attempts: int = 3, backoff: float = 2.0):
    """Decorator factory para retry com backoff exponencial."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff ** attempt
                        logger.warning(f"HTTP {e.response.status_code}, retry em {wait_time:.1f}s...")
                        time.sleep(wait_time)
                except httpx.RequestError as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff ** attempt
                        logger.warning(f"Request error: {e}, retry em {wait_time:.1f}s...")
                        time.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator


@lru_cache(maxsize=1)
def _get_openai_tools() -> list[dict]:
    """
    Converte schemas Anthropic → OpenAI format (cached).
    Executado uma vez na primeira chamada.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOLS
    ]


SYSTEM_PROMPT = """Você é o DataFlow Agent, um engenheiro de dados autônomo.

Sua missão: receber dados brutos e transformá-los em dados limpos e prontos para análise.

## Workflow obrigatório

1. **detect_schema** — Analise a amostra e identifique colunas, tipos e estatísticas.
2. **assess_quality** — Avalie problemas: nulos, duplicatas, tipos inconsistentes.
3. **plan_transformation** — Crie um plano de transformação com steps ordenados.
4. **execute_transform** — Execute cada step do plano (um por vez).
5. **validate_output** — Valide que o resultado final está correto.

## Regras sobre session_id

- O `detect_schema` retorna um `session_id`. Guarde-o.
- Passe o `session_id` para TODAS as ferramentas seguintes: `assess_quality`, `plan_transformation`, `execute_transform` e `validate_output`.
- Sem o `session_id` correto, as ferramentas não conseguem acessar os dados.

## Regras gerais

- SEMPRE siga os 5 steps na ordem.
- Use as tools disponíveis — nunca simule resultados.
- Explique seu raciocínio em português antes de cada tool call.
- Se encontrar erros, tente corrigir antes de falhar.
- Seja conciso e técnico nos raciocínios.
"""


class DataFlowAgent:
    """
    Agente que processa dados usando Ollama local/cloud (OpenAI-compatible API).

    Uso:
        agent = DataFlowAgent()
        result = agent.process(sample_data="col1,col2\\n1,2\\n3,4")
    """

    def __init__(self):
        self.decisions: deque = deque(maxlen=AGENT_MAX_DECISIONS)
        self.total_tokens = 0

    def process(self, sample_data: str, context: str = "") -> dict:
        """
        Executa o pipeline usando Ollama local ou cloud (OpenAI-compatible API).

        Args:
            sample_data: Dados brutos (CSV ou JSON string).
            context: Contexto adicional sobre os dados.

        Returns:
            Dict com decisions, quality_score e métricas.
        """
        ollama_url = settings.OLLAMA_URL
        ollama_model = settings.OLLAMA_MODEL
        iteration = 0

        # Usa tools cached (convertido uma vez)
        openai_tools = _get_openai_tools()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_message(sample_data, context)},
        ]

        decisions: deque = deque(maxlen=AGENT_MAX_DECISIONS)
        total_tokens: int = 0

        @_retry_with_backoff(max_attempts=AGENT_RETRY_ATTEMPTS, backoff=AGENT_RETRY_BACKOFF)
        def _call_ollama(msgs: list) -> dict:
            return httpx.post(
                f"{ollama_url}/v1/chat/completions",
                json={
                    "model": ollama_model,
                    "messages": msgs,
                    "tools": openai_tools,
                    "stream": False,
                },
                timeout=AGENT_TIMEOUT,
            )

        for iteration in range(AGENT_MAX_ITERATIONS):
            start_time = time.perf_counter()

            resp = _call_ollama(messages)
            resp.raise_for_status()
            data = resp.json()

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            usage = data.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)
            step_tokens = usage.get("completion_tokens", 100)

            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""

            # Raciocínio em texto (pode estar vazio quando há tool_calls)
            if content.strip():
                decisions.append({
                    "step": self._infer_step(iteration),
                    "reasoning": content,
                    "action": {"type": "reasoning"},
                    "tokens_used": step_tokens,
                    "latency_ms": latency_ms,
                })

            tool_calls = message.get("tool_calls") or []

            # Adiciona mensagem do assistente ao histórico
            asst_msg: dict = {"role": "assistant", "content": content}
            if tool_calls:
                asst_msg["tool_calls"] = tool_calls
            messages.append(asst_msg)

            # Executa cada tool call e devolve os resultados
            for tc in tool_calls:
                fn = tc["function"]
                tool_name = fn["name"]
                raw_args = fn.get("arguments", "{}")
                tool_input = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                handler = TOOL_HANDLERS.get(tool_name)
                tool_result = handler(**tool_input) if handler else {"error": f"Tool '{tool_name}' não encontrada."}

                logger.info(f"[Ollama] Tool '{tool_name}' executada.")

                decisions.append({
                    "step": self._infer_step_from_tool(tool_name),
                    "reasoning": f"Executou tool '{tool_name}'",
                    "action": {"tool": tool_name, "input": tool_input, "output": tool_result},
                    "tokens_used": step_tokens,
                    "latency_ms": latency_ms,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

            # Sem tool calls = agente terminou
            if not tool_calls or choice.get("finish_reason") == "stop":
                logger.info(f"[Ollama] Concluído após {iteration + 1} iterações.")
                break

        self.decisions = decisions  # permite _extract_quality_score funcionar

        return {
            "decisions": list(decisions),
            "total_tokens": total_tokens,
            "iterations": iteration + 1,
            "quality_score": self._extract_quality_score(),
        }

    def _build_user_message(self, sample_data: str, context: str) -> str:
        """Monta a mensagem inicial com os dados."""
        # Trunca dados se necessário
        data = sample_data[:AGENT_MAX_DATA_CHARS]
        msg = f"## Dados para processar\n\n```\n{data}\n```\n"
        if context:
            msg += f"\n## Contexto adicional\n\n{context}\n"
        msg += "\nPor favor, processe estes dados seguindo o workflow completo."
        return msg

    def _infer_step(self, iteration: int) -> str:
        """Infere o step com base na iteração."""
        steps = ["classify", "quality", "plan", "execute", "validate"]
        return steps[min(iteration, len(steps) - 1)]

    def _infer_step_from_tool(self, tool_name: str) -> str:
        """Mapeia tool name → step."""
        mapping = {
            "detect_schema": "classify",
            "assess_quality": "quality",
            "plan_transformation": "plan",
            "execute_transform": "execute",
            "validate_output": "validate",
        }
        return mapping.get(tool_name, "execute")

    def _extract_quality_score(self) -> float:
        """Extrai o quality score das decisões de validação."""
        for decision in reversed(self.decisions):
            action = decision.get("action", {})
            if isinstance(action, dict):
                output = action.get("output", {})
                if isinstance(output, dict) and "quality_score" in output:
                    return output["quality_score"]
        return 0.0
