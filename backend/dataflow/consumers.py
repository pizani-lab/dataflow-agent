"""
DataFlow Agent — WebSocket Consumers

Consumers Channels para atualizações em tempo real de runs de pipeline.
"""
import json

from channels.generic.websocket import AsyncWebsocketConsumer


class PipelineConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket para um pipeline específico.

    URL: ws://<host>/ws/pipelines/<pipeline_id>/

    Entra no grupo do pipeline ao conectar e recebe eventos
    de atualização de run enviados pelo Celery task.
    """

    async def connect(self):
        self.pipeline_id = self.scope["url_route"]["kwargs"]["pipeline_id"]
        self.group_name = f"pipeline_{self.pipeline_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Frontend não envia mensagens; conexão é somente leitura."""
        pass

    async def run_update(self, event):
        """
        Recebe evento do channel layer e repassa ao cliente WebSocket.

        Disparado pelo Celery task quando o status de um run muda.
        """
        await self.send(text_data=json.dumps(event["data"]))
