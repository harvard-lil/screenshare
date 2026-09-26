FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir poetry==1.8.4 poetry-plugin-export==1.8.0

COPY pyproject.toml poetry.lock ./

RUN python -m venv /opt/venv \
    && poetry export -f requirements.txt --only main -o requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

# The app reads static/img/sando_grids/ relative to the working directory, so
# every process runs from the repository root.
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv
COPY . .

# settings.py requires SECRET_KEY at import; this placeholder exists only for
# the build step and is not in the image's environment.
RUN SECRET_KEY=collectstatic python manage.py collectstatic --noinput \
    && useradd --system --no-create-home appuser

USER appuser

EXPOSE 8000

# The web process. The Slack process runs from the same image with
# `python manage.py slack_socket_mode`.
CMD ["sh", "-c", "exec daphne config.asgi:application --port ${PORT} --bind 0.0.0.0"]
