"""
DataFlow Agent — API URL Configuration
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgentDecisionViewSet,
    DataSourceViewSet,
    PipelineViewSet,
    ProcessingRunViewSet,
)

router = DefaultRouter()
router.register(r"pipelines", PipelineViewSet, basename="pipeline")
router.register(r"runs", ProcessingRunViewSet, basename="run")
router.register(r"sources", DataSourceViewSet, basename="source")
router.register(r"decisions", AgentDecisionViewSet, basename="decision")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
]
