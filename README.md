Screenshare Redux
=================

Another LIL screenshare project. This one is based on Django Channels.

This project serves two functions: first, to allow a team to post
pictures to a Slack channel and have them appear on a monitor in a
common workspace; second, as a context for experimentation with web
technologies.

Deployment
----------

The system runs as two processes from one image, sharing a Redis
server:

- the web process, `daphne config.asgi:application`, serves the
  display page at `/` and its websocket at `/ws/`;
- the Slack process, `python manage.py slack_socket_mode`, opens an
  outbound [Socket Mode](https://api.slack.com/apis/socket-mode)
  connection to Slack and receives events over it, so Slack never
  needs to reach this system.

To set up the Slack app, enable Socket Mode (Settings/Socket Mode),
create an app-level token with the `connections:write` scope, and
subscribe to the bot events `message.channels`, `reaction_added`, and
`reaction_removed` in Event Subscriptions. The Slack process needs
`SLACK_APP_TOKEN` (the app-level token, `xapp-...`) and
`SLACK_BOT_ACCESS_TOKEN` ("Bot User OAuth Token" in the OAuth &
Permissions section of the app's config); see `config/.env.example`.
The web process needs neither.

In production, this system runs on AWS ECS, defined in
[lil-terraform](https://github.com/harvard-lil/lil-terraform) under
`screenshare/`. Pushes to `develop` build the `Dockerfile` and deploy
it through `.github/workflows/deploy.yml`. The display is served at
`https://screenshare.lil.tools/` through a Cloudflare Tunnel, where a
Cloudflare rule admits only LILspace addresses, and to people on LIL's
NetBird network at `http://web.screenshare.lil.internal:8000/`.

Images at URLs posted in Slack are fetched through the HTTP proxy at
`EGRESS_PROXY_URL` when it is set. In production that is an egress
proxy in the same task that refuses private and link-local
destinations, so a posted URL cannot reach services inside LIL's
network.

The `primrose` feature posts images to a
[primitive-api](https://github.com/bensteinberg/primitive-api) server
at `PRIMITIVE_URL`, and is skipped when that is unset, as it is in
production.

To try this out locally:

- copy `config/.env.example` to `config/.env`
- install redis, probably with `brew install redis`
- in one terminal, run `redis-server`
- set up a Slack app as described above, and put `SLACK_APP_TOKEN`
  and `SLACK_BOT_ACCESS_TOKEN` in `config/.env`
- add the app to whatever channel you like, and set the channel name
  in `config/.env` like this: `POST_CHANNEL='#bottest'`
- optionally set `ASCII_FIRE_URL` in `config/.env`
- install [Poetry](https://python-poetry.org/), probably with `curl
  -sSL https://install.python-poetry.org | python3 -`
- in another terminal, in this directory, run `poetry install`
- in the same terminal, generate a secret key with `poetry run python
  -c "from django.core.management.utils import get_random_secret_key;
  print(get_random_secret_key())"` and set the `SECRET_KEY` in
  `config/.env`
- in the same terminal, in this directory, run `poetry run ./manage.py collectstatic`
- in the same terminal, in this directory, run `poetry run
  daphne config.asgi:application --port 8000 --bind 0.0.0.0 -v2`
- in yet another terminal, in this directory, run `poetry run
  ./manage.py slack_socket_mode`

You should now be able to open http://127.0.0.1:8000/, post an image
to the channel you added the app to, and see it appear in your
browser.

Slack spreads an app's events across all of its open Socket Mode
connections, so a development copy connected with the production app's
token would take some of production's events. Use a separate Slack app
for development.

Development
-----------

For development, use [Poetry](https://python-poetry.org/). The
`Dockerfile` exports its requirements from `poetry.lock` at build
time.

Note that `daphne`, when run as shown above, does not auto-reload on
code changes. [This issue](https://github.com/django/daphne/issues/9)
suggests switching to [uvicorn](https://www.uvicorn.org/) for an ASGI
server. The Slack process does not auto-reload either.
