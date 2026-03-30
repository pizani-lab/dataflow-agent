"""Management command para criar superuser padrão."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
import os

User = get_user_model()


class Command(BaseCommand):
    """Cria superuser admin via variáveis de ambiente."""

    help = "Cria superuser padrão via ADMIN_USERNAME/ADMIN_PASSWORD/ADMIN_EMAIL"

    def handle(self, *args, **options) -> None:
        """Executa criação do admin."""
        username = os.getenv("ADMIN_USERNAME", "admin")
        email = os.getenv("ADMIN_EMAIL", "admin@localhost")
        password = os.getenv("ADMIN_PASSWORD")

        if not password:
            raise CommandError(
                "ADMIN_PASSWORD não configurada. Configure a variável de ambiente ADMIN_PASSWORD."
            )

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Usuário '{username}' já existe, pulando.")
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' criado."))
