import base64
import hashlib
import hmac
import json
import logging
import re
import requests
import threading

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.utils.encoding import force_bytes, force_str
from django.views.decorators.csrf import csrf_exempt
from main.helpers import get_message_history, message_for_ts, send_state

logger = logging.getLogger(__name__)


### helpers ###

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

colors = ['black', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'brown']
def handle_reactions(message, is_most_recent):
    old_color = message['color']
    new_color = None
    for reaction in message['reactions']:
        if 'night' in reaction:
            new_color = "#000"
        else:
            new_color = next((
                color
                for color in colors
                if color in reaction
            ), None)
        if new_color == 'brown':
            # saddle brown
            new_color = '#8b4513'
        if new_color:
            break
    if old_color != new_color:
        message["color"] = new_color or '#fff'
        if is_most_recent:
            send_state({"color": message["color"]})

def store_fire(id):
    """ Add an ascii fire video to message history """
    video_html = f"""
        <video class="ascii-fire" controls loop autoplay muted>
          <source src="{ settings.ASCII_FIRE_URL }" type="video/mp4">
          Sorry, your browser doesn't support embedded videos, but don't worry, you can
            <a href="{ settings.ASCII_FIRE_URL }">download it</a>
          and watch it with your favorite video player!
        </video>
    """
    store_message(id, video_html, 'black')

def store_image(id, file_response):
    """ Add requested file to message_history """
    encoded_image = "<img src='data:%s;base64,%s'>" % (
        file_response.headers['Content-Type'],
        base64.b64encode(file_response.content).decode())
    store_message(id, encoded_image)

def store_message(id, html, color=None):
    with get_message_history() as message_history:
        message_history.append({
            "id": id,
            "html": html,
            "reactions": [],
            "color": color or "#fff",
        })
        send_state(message_history[-1])

def delete_message(id):
    with get_message_history() as message_history:
        message, is_most_recent = message_for_ts(message_history, id)
        if message:
            message_history.remove(message)
            if is_most_recent and message_history:
                send_state(message_history[-1])

### views ###

@csrf_exempt
def slack_event(request):
    """ Handle message from Slack. """
    verify_slack_request(request)

    event = json.loads(request.body.decode("utf-8"))
    logger.info(event)

    # url verification
    if event["type"] == "url_verification":
        return HttpResponse(event["challenge"], content_type='text/plain')
    else:
        # handle event in a background thread so Slack doesn't resend if it takes too long
        threading.Thread(target=handle_slack_event, args=(event,)).start()

        # 200 to tell Slack not to resend
        return HttpResponse()


def handle_slack_event(event):

    event = event["event"]

    # message in channel
    if event["type"] == "message":

        message_type = event.get("subtype")

        # handle uploaded image
        if message_type == "file_share":
            # {
            #   'type': 'message',
            #   'files': [{
            #       'filetype': 'png',
            #       'url_private': 'https://files.slack.com/files-pri/T02RW19TT-FBY895N1Z/image.png'
            #   }],
            #   'ts': '1532713362.000505',
            #   'subtype': 'file_share',
            # }
            file_info = event["files"][0]
            if file_info["filetype"] in ("jpg", "gif", "png"):
                # if image, fetch file and send to listeners
                file_response = requests.get(file_info["url_private"], headers={"Authorization": "Bearer %s" % settings.SLACK["bot_access_token"]})
                if file_response.headers['Content-Type'].startswith('text/html'):
                    logger.error("Failed to fetch image; check bot_access_token")
                else:
                    store_image(event['ts'], file_response)

        # handle pasted URL
        elif message_type == "message_changed":
            # this is what we get when slack unfurls an image URL -- a nested message with attachments
            message = event['message']

            if message.get('attachments'):
                attachment = message['attachments'][0]

                # video URL
                if 'video_html' in attachment:
                    # {
                    #   'type': 'message',
                    #   'subtype': 'message_changed',
                    #   'message': {
                    #       'attachments': [{
                    #           'video_html': '<iframe width="400" height="225" ...></iframe>'
                    #       }],
                    #      'ts': '1532713362.000505',
                    #   },
                    # }
                    html = attachment['video_html']
                    html = re.sub(r'width="\d+" height="\d+" ', '', html)
                    store_message(message['ts'], html)

                # image URL
                elif 'image_url' in attachment:
                    # {
                    #   'type': 'message',
                    #   'subtype': 'message_changed',
                    #   'message': {
                    #       'attachments': [{
                    #           'image_url': 'some external url'
                    #       }],
                    #      'ts': '1532713362.000505',
                    #   },
                    # }
                    try:
                        file_response = requests.get(attachment['image_url'])
                        assert file_response.ok
                        assert any(file_response.headers['Content-Type'].startswith(prefix) for prefix in ('image/jpeg', 'image/gif', 'image/png'))
                    except (requests.RequestException, AssertionError) as e:
                        logger.error("Failed to fetch URL: %s" % e)
                    else:
                        store_image(message['ts'], file_response)

            elif event['previous_message'].get('attachments'):
                # if edited message doesn't have attachment but previous_message did, attachment was hidden -- delete
                delete_message(event['previous_message']['ts'])

        # handle message deleted
        elif message_type == "message_deleted" and event.get('previous_message'):
            delete_message(event['previous_message']['ts'])

        # handle regular messages (not including threads)
        elif message_type is None:
            # {
            #     "type": "message",
            #     "text": "Hello world",
            #     "ts": "1355517523.000005"
            # }
            if ":hotfire:" in event.get("text", ""):
                store_fire(event["ts"])


    # handle reactions
    elif event["type"] == "reaction_added":
        # {
        #   'type': 'reaction_added',
        #   'user': 'U02RXC5JN',
        #   'item': {'type': 'message', 'channel': 'CBU9W589K', 'ts': '1532713362.000505'},
        #   'reaction': 'rage',
        #   'item_user': 'U02RXC5JN',
        #   'event_ts': '1532713400.000429'
        # }
        with get_message_history() as message_history:
            message, is_most_recent = message_for_ts(message_history, event['item']['ts'])
            if message:
                message['reactions'].insert(0, event["reaction"])
                handle_reactions(message, is_most_recent)

    elif event["type"] == "reaction_removed":
        with get_message_history() as message_history:
            message, is_most_recent = message_for_ts(message_history, event['item']['ts'])
            if message:
                try:
                    message['reactions'].remove(event["reaction"])
                except ValueError:
                    pass
                else:
                    handle_reactions(message, is_most_recent)

