# Backend: FastAPI + синхронизация из Яндекс.Таблиц через headless Chromium.
# Браузеры Playwright ставятся на этапе сборки (в рантайме сети может не быть).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/lk/backend

# Системные зависимости + браузер для Playwright (нужен root на сборке).
COPY pyproject.toml ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && pip install . \
    && python -m playwright install --with-deps chromium \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/* /root/.cache

COPY app ./app

# Непривилегированный пользователь для рантайма.
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /srv/lk
USER appuser

# За nginx: реальный IP клиента — из X-Forwarded-For (нужен rate limit'у).
# nginx стучится в контейнер с адреса docker-шлюза, а uvicorn по умолчанию
# доверяет заголовку только от 127.0.0.1 — иначе у всех один IP и общий
# лимит на весь сайт. Доверяем только приватным сетям Docker.
ENV FORWARDED_ALLOW_IPS="127.0.0.1,172.16.0.0/12,192.168.0.0/16"

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://localhost:8001/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers"]
