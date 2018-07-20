from channels.generic.websocket import AsyncWebsocketConsumer
import json

from django.core.cache import cache


class Consumer(AsyncWebsocketConsumer):
    room_group_name = 'index'

    async def connect(self):
        # add new connections to group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # send data for last image
        for message_type in ("image", "color"):
            data = cache.get("previous:"+message_type)
            if data:
                await self.channel_layer.group_send(self.room_group_name, {"type": message_type, "data": data})

    async def disconnect(self, close_code):
        # leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name)

    async def image(self, event):
        await self.send(json.dumps({"type": "image", "data": event["data"]}))

    async def color(self, event):
        await self.send(json.dumps({"type": "color", "data": event["data"]}))