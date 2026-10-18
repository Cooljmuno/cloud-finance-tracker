FROM python:3.14.7-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.33

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS development

RUN uv sync --frozen
COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS production

ENV DJANGO_SETTINGS_MODULE=config.settings.production

COPY . .

RUN groupadd --system app && \
    useradd --system --gid app --home-dir /app --no-create-home app && \
    chmod 1777 /tmp

VOLUME ["/tmp"]

USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--graceful-timeout", "30", "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "--access-logformat", "%(t)s %(m)s %(U)s %(s)s %(L)s", "--error-logfile", "-", "--capture-output", "--forwarded-allow-ips", ""]
