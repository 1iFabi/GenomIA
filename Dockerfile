# Dockerfile en la RAÍZ del repo
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Para sqlite3 de Python
RUN apt-get update \
  && apt-get install -y --no-install-recommends libsqlite3-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1

# Dependencias de producción desde el lock de uv
COPY backend/sequoh/pyproject.toml backend/sequoh/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --python /usr/local/bin/python

# Copiamos SOLO el backend/sequoh (ahí está manage.py y sequoh/)
COPY backend/sequoh/ .

# Arranque: migrate + collectstatic + gunicorn
CMD sh -c "python manage.py migrate --noinput \
  && python manage.py collectstatic --noinput || true \
  && gunicorn sequoh.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 600"
