import logging
from threading import Event

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse

from main.views import handle_slack_event

logger = logging.getLogger(__name__)


def process(client, req):
    """ Acknowledge each envelope so Slack doesn't redeliver it, then handle Events API payloads. """
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    if req.type == "events_api":
        handle_slack_event(req.payload)


class Command(BaseCommand):
    help = "Receive Slack events over a Socket Mode connection opened from this process."

    def handle(self, *args, **options):
        if not (settings.SLACK['app_token'] and settings.SLACK['bot_access_token']):
            raise CommandError("SLACK_APP_TOKEN and SLACK_BOT_ACCESS_TOKEN are required")

        # The client reconnects on its own when Slack closes the connection, and
        # runs listeners on a thread pool, so one slow handler does not hold up later events.
        client = SocketModeClient(app_token=settings.SLACK['app_token'])
        client.socket_mode_request_listeners.append(process)
        client.connect()
        logger.info("Connected to Slack in Socket Mode")
        Event().wait()
