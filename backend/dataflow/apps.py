from django.apps import AppConfig
from django.contrib.auth import get_user_model
import os

User = get_user_model()


class DataflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dataflow"
    verbose_name = "DataFlow Agent"

    def ready(self):
        """Cria usuário admin padrão no primeiro run (dev only)."""
        # Apenas cria se não existir e se for desenvolvimento
        if os.getenv("DEBUG", "True").lower() == "true":
            if not User.objects.filter(username="admin").exists():
                password = os.getenv("ADMIN_PASSWORD", "admin123")
                User.objects.create_superuser(
                    username="admin",
                    email="admin@localhost",
                    password=password,
                )
                print("✓ Usuário admin criado (admin / admin123)")
