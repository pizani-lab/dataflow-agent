"""
Factories de teste para os modelos do DataFlow Agent.
"""
import factory
from django.contrib.auth.models import User

from dataflow.models import AgentDecision, Pipeline, ProcessingRun, QualityReport


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email    = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class PipelineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pipeline

    name        = factory.Sequence(lambda n: f"Pipeline {n}")
    description = "Pipeline de teste"
    status      = Pipeline.Status.DRAFT


class ProcessingRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProcessingRun

    pipeline = factory.SubFactory(PipelineFactory)
    status   = ProcessingRun.Status.SUCCESS
    rows_in  = 100
    rows_out = 95
    trigger  = "manual"


class AgentDecisionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentDecision

    run        = factory.SubFactory(ProcessingRunFactory)
    step       = AgentDecision.Step.CLASSIFY
    reasoning  = "Analisando schema dos dados."
    action     = {"tool": "detect_schema", "output": {}}
    tokens_used = 150
    latency_ms  = 320


class QualityReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QualityReport

    run                  = factory.SubFactory(ProcessingRunFactory)
    quality_score        = 85.0
    null_percentage      = 2.5
    duplicate_percentage = 1.0
    schema_drift_detected = False
    details              = {}
