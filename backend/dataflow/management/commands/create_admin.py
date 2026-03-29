"""Management command para criar superuser padrão."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    """Cria superuser admin/admin123 se não existir."""

    help = "Cria superuser padrão (admin/admin123) de forma idempotente"

    def handle(self, *args, **options) -> None:
        """Executa criação do admin."""
        if User.objects.filter(username="admin").exists():
            self.stdout.write("Admin já existe, pulando.")
            return

        User.objects.create_superuser(
            username="admin",
            email="admin@portfolio.local",
            password="admin123*",
        )
        self.stdout.write(self.style.SUCCESS("Superuser admin criado (senha: admin123)"))
