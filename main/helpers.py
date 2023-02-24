import json
from contextlib import contextmanager
from slack import WebClient
from slack.errors import SlackApiError

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache

import logging
logger = logging.getLogger(__name__)


@contextmanager
def get_message_history():
    """
        Context manager to load and save state of previously received Slack messages. E.g.:

            with get_message_history() as message_history:
                # message_history is a list like
                # [{'id':'...', 'image':'data', 'color':'#fff', 'reactions':['smile', 'red_circle']}]
                # with the most recent message appearing last.
                # Changes made to message_history inside this block will be persisted.
    """
    # load message history
    orig_message_history = cache.get("message_history", "[]")
    message_history = json.loads(orig_message_history)

    yield message_history

    # trim and save message_history if changed
    message_history = message_history[-5:]
    new_message_history = json.dumps(message_history)
    if new_message_history != orig_message_history:
        cache.set("message_history", new_message_history)

def message_for_ts(message_history, ts):
    """
        Given list of messages and timestamp of desired message, return (message, is_last),
        or (None, None) if not found.
    """
    return next((
        (m, i==len(message_history)-1)
        for i, m in enumerate(message_history)
        if m['id'] == ts
    ), (None, None))


_state_keys = ('html', 'color')

def send_state(state):
    """ Send state to listeners. """
    # filter state to just expected keys
    state = {k:v for k, v in state.items() if k in _state_keys}

    # send to settings.ROOM_NAME
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(settings.ROOM_NAME, {
        'type': 'share_state',
        'state': state,
    })

def send_to_slack(channel, thread_ts, text):
    client = WebClient(token=settings.SLACK['bot_access_token'])
    try:
        response = client.chat_postMessage(
            channel=f"{channel}",
            thread_ts=thread_ts,
            text=text
        )
        assert response["ok"]
    except (SlackApiError, AssertionError):
        logger.exception(f"Unsuccessful attempt to post a message to {channel}.")
