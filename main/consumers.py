from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
import json

from django.conf import settings

from .helpers import get_message_history, send_state


class Consumer(WebsocketConsumer):

    def connect(self):
        # add new connections to group
        async_to_sync(self.channel_layer.group_add)(
            settings.ROOM_NAME,
            self.channel_name
        )
        self.accept()

        # send data for last image
        with get_message_history() as message_history:
            if message_history:
                send_state(message_history[-1])

    def disconnect(self, close_code):
        # leave room group
        async_to_sync(self.channel_layer.group_discard)(
            settings.ROOM_NAME,
            self.channel_name)

    def share_state(self, event):
        """ Event handler to send current state to client. Triggered by send_state(). """
        self.send(json.dumps(event['state']))