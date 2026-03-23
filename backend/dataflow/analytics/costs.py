"""
DataFlow Agent — Cálculo de Custo por Token

Estima o custo em USD de uma execução com base nos tokens consumidos
pelo modelo Claude. Usa taxa blended (80% input + 20% output).
"""
from django.conf import settings


def compute_cost(tokens: int) -> float:
    """
    Calcula o custo estimado em USD para um número de tokens.

    Args:
        tokens: Total de tokens consumidos (input + output combinados).

    Returns:
        Custo em USD arredondado em 6 casas decimais.
    """
    rate = getattr(settings, "ANTHROPIC_BLENDED_COST_PER_M", 5.40)
    return round(tokens * rate / 1_000_000, 6)


def format_cost(usd: float) -> str:
    """
    Formata um valor em USD para exibição.

    Valores abaixo de $0.01 são exibidos em frações de centavo.
    """
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.4f}"
