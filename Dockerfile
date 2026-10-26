# Pinned tool images. uv is used only to install the locked dependencies and
# is not left in the runtime image.
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:3.14-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    PORT=8000 \
    PATH="/opt/venv/bin:$PATH"

# The app reads static/img/sando_grids/ relative to the working directory, so
# every process runs from the repository root.
WORKDIR /app

# The locked runtime dependencies, from the manifest and lockfile alone so this
# layer is independent of app-code changes. pip is removed afterwards: nothing
# at runtime installs packages, and scanners report its advisories otherwise.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-cache \
    && rm -rf /usr/local/lib/python3.14/site-packages/pip* /usr/local/bin/pip*

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
