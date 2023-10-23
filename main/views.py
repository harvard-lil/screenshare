import base64
from datetime import datetime, time
import hashlib
import hmac
import json
import logging
import pytz
import random
import re
import requests
import threading
from urllib.parse import urlencode
import os

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.utils.encoding import force_bytes, force_str
from django.views.decorators.csrf import csrf_exempt
from main.helpers import get_message_history, message_for_ts, send_state, send_to_slack
from main.moongazing import MOONGAZING_URLS

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

def extract_emoji_from_message_text(text):
    no_code_blocks = re.sub(r"```.*?```", "", text, flags=re.MULTILINE|re.DOTALL)
    no_inline_code = re.sub(r"`.*?`", "", no_code_blocks)
    return re.findall(r":(\w+)?:", no_inline_code)

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

def store_astronomy_image(id, random_day=False, attempts=0):
    """ Add NASA's astronomy image of the day to message history """
    apod_url = "https://apod.nasa.gov/apod"

    # Retrieve list of available images:
    # e.g. [('2015 January 01', 'ap150101.html', 'Vela Supernova Remnant')]
    archive_url = f"{apod_url}/archivepix.html"
    r = requests.get(archive_url, timeout=5)
    assert r.status_code == 200, f"{archive_url} returned {r.status_code}: {r.text}"
    pic_tuples = re.findall(r"(\d\d\d\d .*\d\d): +<a href=\"(.*)\">(.*?)</a>", r.text)
    assert pic_tuples, "No NASA astronomy images of the day found: has the page's markup changed?"

    # Select an image
    if random_day:
        target = random.choice(pic_tuples)
    else:
        target = pic_tuples[0]

    # Get the image's URL and description
    target_day_url = f"{apod_url}/{target[1]}"
    r = requests.get(target_day_url, timeout=5)
    assert r.status_code == 200, f"{archive_url} returned {r.status_code}: {r.text}"
    text = r.text.replace("\n", " ")  # Remove newlines for easier parsing
    try:
        [pic_relative_url] = re.findall(r"<a\s+?href=\s*?\"(image/.*?)\"\s*?>", text)
        [description] = re.findall(r"Explanation: </b>\s+(.*?)\s+<p>\s*<center>", text)
    except ValueError:
        # if parsing failed, try again for some random day
        if attempts < 3:
            store_astronomy_image(id, True, attempts + 1)
        else:
            raise

    # Store the image
    store_message(id, f"<image src={apod_url}/{pic_relative_url}>", 'black')

    # Format the image description for display.
    # First, make relative URLs absolute.
    for url in re.findall(r"<a\s*?href=\s*?\"(.+?)\"\s*?>", description):
        if not url.startswith('http'):
            description = re.sub(url, f"{apod_url}/{url}", description)
    # Next, convert the links to the format expected by Slack
    description = re.sub(r"<a\s*?href=\s*?\"(.+?)\"\s*?>(.+?)</a>", r"<\1|\2>", description)

    # Reply to Slack with information about what is being displayed
    txt = f"""
*{target[2]}*
<{apod_url}/{target[1]}|NASA's Astronomy Picture of the Day>
{target[0]}
--------------------

{description}"""

    send_to_slack(settings.DEFAULT_POST_CHANNEL, id, txt)

def store_sandwich(id):
    sando_dir = "static/img/sando_grids/"
    img = random.choice(os.listdir(sando_dir))
    filename = os.path.basename(img)
    sandwich_name = filename[:-9].replace("-", " ")

    with open(sando_dir + img, "rb") as f:
        encoded_image = "<img src='data:image/png;base64,%s'>" % (
            base64.b64encode(f.read()).decode())
    store_message(id, encoded_image)

    txt = f':yum: "{sandwich_name}" :yum:'
    send_to_slack(settings.DEFAULT_POST_CHANNEL, id, txt)

def store_ambient_youtube_video(id, emoji):
    config = settings.AMBIENT_YOUTUBE_VIDEOS[emoji]
    youtube_id = config["youtube_id"]

    # check the time constraints
    if "online_between" in config:
        start_online, end_online, tz, msg = config["online_between"]
        tzinfo = pytz.timezone(tz)
        if not (time(start_online, tzinfo=tzinfo) <= datetime.now(tzinfo).time() < time(end_online, tzinfo=tzinfo)):
            send_to_slack(settings.DEFAULT_POST_CHANNEL, id, msg)
            return

    # get a random start time, if any
    start = None
    if "start_times" in config:
        start = random.choice(config["start_times"])

    # get the end time if any
    end = None
    if "end_time" in config:
        end = config["end_time"]

    store_autoplaying_youtube_video(id, youtube_id, start, end, loop=True)

def store_autoplaying_youtube_video(id, youtube_id, start=None, end=None, loop=True):
    """Add an autoplaying, muted YouTube video to message history"""

    # https://developers.google.com/youtube/player_parameters
    options = {
        "autoplay": 1,
        "modestbranding": 1,
        "mute": 1
    }
    if start:
        options['start'] = start
    if end:
        options['end'] = end
    if loop:
        # This parameter has limited support in IFrame embeds. To loop a single video, set the loop parameter
        # value to 1 and set the playlist parameter value to the same video ID already specified in the Player
        # API URL: https://www.youtube.com/embed/VIDEO_ID?playlist=VIDEO_ID&loop=1
        options['loop'] = 1
        options['playlist'] = youtube_id

    html = f'<iframe class="youtube" src="https://youtube.com/embed/{youtube_id}?{urlencode(options)}">'
    store_message(id, html, "black")

def fetch_and_store_image_from_url(ts, url, as_curl=False, color=None):
    try:
        if as_curl:
            file_response = requests.get(url, headers={'User-Agent': 'curl/7.88.1'})
        else:
            file_response = requests.get(url)
        assert file_response.ok
        assert any(file_response.headers['Content-Type'].startswith(prefix) for prefix in ('image/jpeg', 'image/gif', 'image/png', 'image/webp'))
    except (requests.RequestException, AssertionError) as e:
        logger.error("Failed to fetch URL: %s" % e)
    else:
        store_image(ts, file_response, color)

def store_image(id, file_response, color=None):
    """ Add requested file to message_history """
    encoded_image = "<img src='data:%s;base64,%s'>" % (
        file_response.headers['Content-Type'],
        base64.b64encode(file_response.content).decode())
    store_message(id, encoded_image, color)

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
    if not settings.DEBUG:
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
            if file_info["filetype"] in ("jpg", "gif", "png", "webp"):
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
                    fetch_and_store_image_from_url(message['ts'], attachment['image_url'])

            elif event['previous_message'].get('attachments'):
                # if edited message doesn't have attachment but previous_message did, attachment was hidden -- delete
                delete_message(event['previous_message']['ts'])

        # handle message deleted
        elif message_type == "message_deleted" and event.get('previous_message'):
            delete_message(event['previous_message']['ts'])

        # handle regular messages (including within threads)
        elif message_type is None:
            # {
            #     "type": "message",
            #     "text": "Hello world",
            #     "ts": "1355517523.000005"
            # }
            emoji_list = extract_emoji_from_message_text(event.get("text", ""))
            if emoji_list:
                if "hotfire" in emoji_list and settings.ASCII_FIRE_URL:
                    store_fire(event["ts"])

                elif "sandwich" in emoji_list:
                    store_sandwich(event["ts"])

                elif "milky_way" in emoji_list:
                    store_astronomy_image(event["ts"], random_day="random" in event.get("text", ""))

                elif any((matching_emoji := emoji) in settings.AMBIENT_YOUTUBE_VIDEOS.keys() for emoji in emoji_list):
                    store_ambient_youtube_video(event['ts'], matching_emoji)

                elif any((matching_emoji := emoji).endswith("moon") for emoji in emoji_list):
                    fetch_and_store_image_from_url(event["ts"], random.choice(MOONGAZING_URLS), as_curl=True, color="black")


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

