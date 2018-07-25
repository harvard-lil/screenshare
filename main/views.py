import base64
import hashlib
import hmac
import json
import logging

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.utils.encoding import force_bytes, force_str
from django.views.decorators.csrf import csrf_exempt
from main.consumers import Consumer


logger = logging.getLogger(__name__)

def verify_slack_request(request):
    """ Raise SuspiciousOperation if request was not signed by Slack. """
    basestring = b":".join([
        b"v0",
        force_bytes(request.META.get("HTTP_X_SLACK_REQUEST_TIMESTAMP", b"")),
        request.body
    ])
    expected_signature = 'v0=' + hmac.new(settings.SLACK['signing_secret'], basestring, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, force_str(request.META.get("HTTP_X_SLACK_SIGNATURE", ""))):
        raise SuspiciousOperation("Slack signature verification failed")

def send_message(message_type, data):
    """ Send screenshare event, and cache in django_cache. """
    cache.set("previous:"+message_type, data, None)
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(Consumer.room_group_name, {"type": message_type, "data": data})

@csrf_exempt
def slack_event(request):
    """ Handle message from Slack. """
    verify_slack_request(request)
    event = json.loads(request.body.decode("utf-8"))
    print(event)

    # url verification
    if event["type"] == "url_verification":
        return HttpResponse(event["challenge"], content_type='text/plain')

    event = event["event"]

    # message in channel
    if event["type"] == "message":

        # message contains a file
        if event.get("subtype") == "file_share":
            file_info = event["files"][0]
            if file_info["filetype"] in ("jpg", "gif", "png"):
                # if image, fetch file and send to listeners
                file_response = requests.get(file_info["url_private"], headers={"Authorization": "Bearer %s" % settings.SLACK["bot_access_token"]})
                if file_response.headers['Content-Type'].startswith('text/html'):
                    logger.error("Failed to fetch image; check bot_access_token")
                else:
                    encoded_image = "data:%s;base64,%s" % (
                        file_response.headers['Content-Type'],
                        base64.b64encode(file_response.content).decode())
                    send_message("image", encoded_image)

    # handle reactions
    elif event["type"] == "reaction_added":
        if 'night' in event["reaction"]:
            send_message("color", "#000")
        else:
            colors = ['black', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white', 'grey']
            for color in colors:
                if color in event["reaction"]:
                    send_message("color", color)
                    break

    # tell Slack not to resend
    return HttpResponse()
