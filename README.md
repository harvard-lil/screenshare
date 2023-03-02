Screenshare Redux
=================

Another LIL screenshare project. This one is based on Django Channels.

This project serves two functions: first, to allow a team to post
pictures to a Slack channel and have them appear on a monitor in a
common workspace; second, as a context for experimentation with web
technologies.

Deployment
----------

This system should be deployed on a server accessible from the public
web, so that Slack can reach it. It subscribes to certain Slack events
by exposing the endpoint `/slack_event`; create an app, enter the URL
in Event Subscriptions (something like
`https://api.slack.com/apps/<app ID>/event-subscriptions?`), and
subscribe to the bot events `message.channels`, `reaction_added`, and
`reaction_removed`. In `config/.env`, you'll need to configure
`SLACK_SIGNING_SECRET` (Signing Secret in the App Credentials section
of Settings/Basic Information) and `SLACK_BOT_ACCESS_TOKEN` ("Bot User
OAuth Token" in the OAuth & Permissions section of the app's config);
see `config/.env.example`.

In production, this system is running on a Dokku instance. The
complete (?) sequence for setting it up is

```
dokku apps:create screenshare
dokku redis:create screenshare-store
dokku redis:link screenshare-store screenshare
dokku domains:set screenshare <your domain>
dokku letsencrypt:enable screenshare
dokku config:set --no-restart screenshare "SECRET_KEY=..."
dokku config:set --no-restart screenshare "SLACK_SIGNING_SECRET=..."
dokku config:set --no-restart screenshare "SLACK_BOT_ACCESS_TOKEN=..."
dokku config:set --no-restart screenshare "ALLOWED_HOSTS=<your domain>"
dokku config:set --no-restart screenshare "POST_CHANNEL=..."
dokku config:set --no-restart screenshare "ASCII_FIRE_URL=..."
```

Finally, having set up your git remote with something like `git remote
add dokku dokku@<your dokku instance>:screenshare`, deploy with `git
push dokku develop`.

(Screenshare used to be set up on a VM running Debian, with the
application served by daphne via systemd, and exposed with
nginx. Important dependencies include `redis-server`.)

Depending on your setup, you may want to use a firewall and/or nginx
to restrict access to the `/` endpoint.

Prior to a production deployment, you may want to try this out
locally, using [ngrok](https://ngrok.com/) to expose the service to
Slack. The complete sequence for doing this is as follows:

- copy `config/.env.example` to `config/.env`
- install redis, probably with `brew install redis`
- in one terminal, run `redis-server`
- install [ngrok](https://ngrok.com/), probably with `brew install
  ngrok/ngrok/ngrok`
- in another terminal, run `ngrok http 8000`
- put the `ngrok` endpoint in `ALLOWED_HOSTS` in `config/.env`
- set up a Slack app as described above, and put
  `SLACK_SIGNING_SECRET` and `SLACK_BOT_ACCESS_TOKEN` in `config/.env`
- add the app to whatever channel you like, and set the channel name
  in `config/.env` like this: `POST_CHANNEL='#bottest'`
- additionally set `ASCII_FIRE_URL` in `config/.env`
- install [Poetry](https://python-poetry.org/), probably with `curl
  -sSL https://install.python-poetry.org | python3 -`
- in yet another terminal, in this directory, run `poetry install`
- in the same terminal, generate a secret key with `poetry run python
  -c "from django.core.management.utils import get_random_secret_key;
  print(get_random_secret_key())"` and set the `SECRET_KEY` in
  `config/.env`
- in the same terminal, in this directory, run `poetry run ./manage.py collectstatic`
- in the same terminal, in this directory, run `poetry run
  daphne config.asgi:application --port 8000 --bind 0.0.0.0 -v2`
- in the Slack app config page, go to Event Subscriptions and set and
  verify the Request URL, which will be the `ngrok` endpoint with
  `/slack_event` appended

You should now be able to open http://127.0.0.1:8000/ (or the `ngrok`
endpoint), post an image to the channel you added the app to, and see
it appear in your browser.

(Next steps might be to script this, and/or embody it in a `docker
compose` setup.)

Development
-----------

For development, use [Poetry](https://python-poetry.org/), but make
sure to export the conventional requirements file if you make changes
to `poetry.lock`:

    poetry export -o requirements.txt

Note that `daphne`, when run as shown in the `ngrok` example above,
does not auto-reload on code changes. [This
issue](https://github.com/django/daphne/issues/9) suggests switching
to [uvicorn](https://www.uvicorn.org/) for an ASGI server.
