from django.apps import AppConfig


class DataflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dataflow"
    verbose_name = "DataFlow Agent"
