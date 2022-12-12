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
in Event Subscriptions (something like `https://api.slack.com/apps/<app
ID>/event-subscriptions?`), and subscribe to the bot events
`message.channels`, `reaction_added`, and `reaction_removed`. In
`config/.env`, you'll need to configure `SLACK_SIGNING_SECRET` and
`SLACK_BOT_ACCESS_TOKEN` ( ("User OAuth Token" and "Bot User OAuth
Token" in the OAuth & Permissions section of the app's config at
Slack); see `config/.env.example`.

In production, this system is set up on a VM running Debian buster,
with the application served by daphne via systemd, and exposed with
nginx. Important dependencies include `redis-server`.

Depending on your setup, you may want to use a firewall and/or nginx
to restrict access to the `/` endpoint.

Prior to a production deployment, you may want to try this out
locally, using [ngrok](https://ngrok.com/) to expose the service to
Slack.

Development
-----------

For development, use [Poetry](https://python-poetry.org/), but make
sure to export the conventional requirements file f you make changes
to `poetry.lock`:

    poetry export -o requirements.txt
