"""
Fixtures compartilhadas entre todos os testes.
"""
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


CSV_COM_NULOS = """nome,idade,salario,cidade
Alice,30,5000.0,São Paulo
Bob,,3200.0,Rio de Janeiro
Carol,25,,Belo Horizonte
David,45,8000.0,São Paulo
Eve,30,5000.0,São Paulo
Alice,30,5000.0,São Paulo
"""

CSV_LIMPO = """nome,idade,salario,cidade
Alice,30,5000.0,São Paulo
Bob,28,3200.0,Rio de Janeiro
Carol,25,4500.0,Belo Horizonte
David,45,8000.0,São Paulo
"""

JSON_SIMPLES = '[{"id": 1, "valor": 10.5}, {"id": 2, "valor": null}, {"id": 3, "valor": 30.0}]'


@pytest.fixture
def csv_com_nulos() -> str:
    """CSV com nulos e uma linha duplicada."""
    return CSV_COM_NULOS


@pytest.fixture
def csv_limpo() -> str:
    """CSV sem problemas de qualidade."""
    return CSV_LIMPO


@pytest.fixture
def json_simples() -> str:
    """JSON com um valor nulo."""
    return JSON_SIMPLES


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

@pytest.fixture
def user(db):
    """Usuário Django para autenticação nos testes de API."""
    from django.contrib.auth.models import User
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def auth_client(user):
    """APIClient autenticado via JWT."""
    token = RefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture
def anon_client():
    """APIClient sem autenticação."""
    return APIClient()
