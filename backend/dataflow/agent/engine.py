"""
DataFlow Agent — Engine

Orquestra o agente LLM com tool use para processar dados autonomamente.
O loop principal: envia contexto → recebe tool_use → executa → retorna resultado → repete.
"""
import json
import logging
import time

import anthropic
from django.conf import settings

from .tools import TOOL_HANDLERS, TOOLS

logger = logging.getLogger(__name__)


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
    Agente que processa dados usando Claude API com tool use.

    Uso:
        agent = DataFlowAgent()
        result = agent.process(sample_data="col1,col2\\n1,2\\n3,4")
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL
        self.decisions: list[dict] = []
        self.total_tokens = 0

    def process(self, sample_data: str, context: str = "") -> dict:
        """
        Executa o pipeline completo do agente.

        Se AGENT_MOCK=true, usa _process_mock (sem chamada à API).

        Args:
            sample_data: Dados brutos (CSV ou JSON string).
            context: Contexto adicional sobre os dados.

        Returns:
            Dict com decisions, quality_score e métricas.
        """
        if getattr(settings, "AGENT_MOCK", False):
            return self._process_ollama(sample_data, context)

        user_message = self._build_user_message(sample_data, context)
        messages = [{"role": "user", "content": user_message}]

        logger.info("Iniciando processamento do agente...")

        # Agentic loop: continua enquanto o modelo pedir tool_use
        max_iterations = 15
        for iteration in range(max_iterations):
            start_time = time.time()

            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            self.total_tokens += response.usage.input_tokens + response.usage.output_tokens

            # Processa cada bloco da resposta
            tool_results = []
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self._record_decision(
                        step=self._infer_step(iteration),
                        reasoning=block.text,
                        action={"type": "reasoning"},
                        tokens=response.usage.output_tokens,
                        latency_ms=latency_ms,
                    )

                elif block.type == "tool_use":
                    tool_result = self._execute_tool(block)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })

                    self._record_decision(
                        step=self._infer_step_from_tool(block.name),
                        reasoning=f"Executou tool '{block.name}'",
                        action={"tool": block.name, "input": block.input, "output": tool_result},
                        tokens=response.usage.output_tokens,
                        latency_ms=latency_ms,
                    )

            # Se não há mais tool_use, o agente terminou
            if response.stop_reason == "end_turn":
                logger.info(f"Agente concluiu após {iteration + 1} iterações.")
                break

            # Adiciona resposta do assistente e resultados das tools
            messages.append({"role": "assistant", "content": response.content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        return {
            "decisions": self.decisions,
            "total_tokens": self.total_tokens,
            "iterations": iteration + 1,
            "quality_score": self._extract_quality_score(),
        }

    def _process_ollama(self, sample_data: str, context: str = "") -> dict:
        """
        Executa o pipeline usando Ollama local (OpenAI-compatible API).

        Converte o schema das tools de Anthropic → OpenAI, roda o mesmo
        agentic loop com o modelo configurado em OLLAMA_MODEL, e executa
        os tool handlers locais (pandas) sem nenhuma chamada externa paga.

        Args:
            sample_data: Dados brutos (CSV ou JSON string).
            context: Contexto adicional sobre os dados.

        Returns:
            Dict com decisions, quality_score e métricas.
        """
        import httpx

        ollama_url   = getattr(settings, "OLLAMA_URL",   "http://localhost:11434")
        ollama_model = getattr(settings, "OLLAMA_MODEL", "qwen3.5:latest")

        # Converte schemas Anthropic → OpenAI
        openai_tools = [
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

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": self._build_user_message(sample_data, context)},
        ]

        decisions:    list[dict] = []
        total_tokens: int        = 0

        for iteration in range(15):
            start_time = time.time()

            resp = httpx.post(
                f"{ollama_url}/v1/chat/completions",
                json={
                    "model":    ollama_model,
                    "messages": messages,
                    "tools":    openai_tools,
                    "stream":   False,
                },
                timeout=180.0,
            )
            resp.raise_for_status()
            data = resp.json()

            latency_ms    = int((time.time() - start_time) * 1000)
            usage         = data.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)
            step_tokens   = usage.get("completion_tokens", 100)

            choice  = data["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""

            # Raciocínio em texto (pode estar vazio quando há tool_calls)
            if content.strip():
                decisions.append({
                    "step":        self._infer_step(iteration),
                    "reasoning":   content,
                    "action":      {"type": "reasoning"},
                    "tokens_used": step_tokens,
                    "latency_ms":  latency_ms,
                })

            tool_calls = message.get("tool_calls") or []

            # Adiciona mensagem do assistente ao histórico
            asst_msg: dict = {"role": "assistant", "content": content}
            if tool_calls:
                asst_msg["tool_calls"] = tool_calls
            messages.append(asst_msg)

            # Executa cada tool call e devolve os resultados
            for tc in tool_calls:
                fn        = tc["function"]
                tool_name = fn["name"]
                raw_args  = fn.get("arguments", "{}")
                tool_input = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                handler     = TOOL_HANDLERS.get(tool_name)
                tool_result = handler(**tool_input) if handler else {"error": f"Tool '{tool_name}' não encontrada."}

                logger.info(f"[Ollama] Tool '{tool_name}' executada.")

                decisions.append({
                    "step":        self._infer_step_from_tool(tool_name),
                    "reasoning":   f"Executou tool '{tool_name}'",
                    "action":      {"tool": tool_name, "input": tool_input, "output": tool_result},
                    "tokens_used": step_tokens,
                    "latency_ms":  latency_ms,
                })

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content":      json.dumps(tool_result, ensure_ascii=False),
                })

            # Sem tool calls = agente terminou
            if not tool_calls or choice.get("finish_reason") == "stop":
                logger.info(f"[Ollama] Concluído após {iteration + 1} iterações.")
                break

        self.decisions = decisions  # permite _extract_quality_score funcionar

        return {
            "decisions":     decisions,
            "total_tokens":  total_tokens,
            "iterations":    iteration + 1,
            "quality_score": self._extract_quality_score(),
        }

    def _build_user_message(self, sample_data: str, context: str) -> str:
        """Monta a mensagem inicial com os dados."""
        msg = f"## Dados para processar\n\n```\n{sample_data[:5000]}\n```\n"
        if context:
            msg += f"\n## Contexto adicional\n\n{context}\n"
        msg += "\nPor favor, processe estes dados seguindo o workflow completo."
        return msg

    def _execute_tool(self, tool_block) -> dict:
        """Executa a tool chamada pelo agente."""
        handler = TOOL_HANDLERS.get(tool_block.name)
        if not handler:
            return {"error": f"Tool '{tool_block.name}' não encontrada."}

        try:
            result = handler(**tool_block.input)
            logger.info(f"Tool '{tool_block.name}' executada com sucesso.")
            return result
        except Exception as e:
            logger.error(f"Erro na tool '{tool_block.name}': {e}")
            return {"error": str(e)}

    def _record_decision(self, step: str, reasoning: str, action: dict, tokens: int, latency_ms: int):
        """Registra uma decisão do agente."""
        self.decisions.append({
            "step": step,
            "reasoning": reasoning,
            "action": action,
            "tokens_used": tokens,
            "latency_ms": latency_ms,
        })

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
