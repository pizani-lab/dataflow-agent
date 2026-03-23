"""
DataFlow Agent — WebSocket URL Routing
"""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/pipelines/(?P<pipeline_id>[^/]+)/$", consumers.PipelineConsumer.as_asgi()),
]
