# Запуск на VPS

## Требования

- Ubuntu 22.04+ (или другой Linux-дистрибутив)
- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- UFW firewall (опционально)

---

## 1. Подготовка сервера

```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Установка Python 3.12
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Установка Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs

# Перelogin в новую группу docker
newgrp docker
```

---

## 2. Клонирование репозитория

```bash
cd ~
git clone https://github.com/rtzZ/lk-ucp25.git lk
cd lk
```

---

## 3. Настройка переменных окружения

```bash
# Скопировать .env.example в .env
cp .env.example .env

# Отредактировать .env (важные параметры):
nano .env
```

**Обязательные переменные для продакшена:**

| Переменная | Пример значения | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://lk:password@db:5432/lk` | Подключение к PostgreSQL (через docker network `db:5432`) |
| `YANDEX_SCHEDULE_URL` | `https://yadi.sk/d/...` | Edit-ссылка таблицы расписания |
| `YANDEX_GRADES_URL` | `https://yadi.sk/d/...` | Edit-ссылка таблицы успеваемости |
| `SEED_DEMO` | `1` | Загрузить демо-данные при первом запуске |
| `FRONTEND_URL` | `https://your-domain.com` | CORS-origin (ваш домен) |

**Примечание:** В продакшне `DATABASE_URL` ссылается на сервис `db` (имя из `docker-compose.yml`), а не `localhost`.

---

## 4. Запуск через Docker Compose

В новых версиях Docker Compose встроен как плагин. Используйте `docker compose` (без дефиса):

```bash
# Запуск PostgreSQL и backend
docker compose up -d

# Проверка статуса контейнеров
docker compose ps
```

Backend автоматически запустится с `uvicorn` (конфигурация в `backend/pyproject.toml`).

---

## 5. Сборка и запуск фронтенда

### Вариант A: Продакшн-сборка (рекомендуется)

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8001 npm run build

# Установка nginx (если ещё не установлен)
sudo apt install -y nginx

# Настройка nginx
sudo rm /etc/nginx/sites-enabled/default
cat > /tmp/lk-nginx.conf << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /home/ubuntu/lk/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF
sudo cp /tmp/lk-nginx.conf /etc/nginx/sites-available/lk
sudo ln -sf /etc/nginx/sites-available/lk /etc/nginx/sites-enabled/lk
sudo nginx -t && sudo systemctl reload nginx
```

Фронтенд будет доступен по `http://your-domain.com`.

---

### Вариант B: Dev-режим (для отладки)

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8001 npm run dev
```

Фронтенд запустится на порту 5173. Для доступа извне настройте nginx как reverse proxy:

```bash
sudo cat > /etc/nginx/sites-available/lk-dev << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

---

## 6. Проверка работы

```bash
# Health-check backend
curl http://localhost:8001/health

# Документация API
curl http://localhost:8001/docs

# Логи backend
docker-compose logs -f app

# Логи frontend (dev-режим)
tail -f /home/ubuntu/lk/frontend/.vite/dev-server.log
```

---

## 7. Автозапуск и мониторинг

### Docker Compose автоматически перезапускает контейнеры (`restart: unless-stopped`).

Для продакшна рекомендую добавить `healthcheck` в `docker-compose.yml`:

```yaml
services:
  db:
    # ... существующие настройки ...
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lk"]
      interval: 10s
      timeout: 5s
      retries: 5
```

---

## 8. Обновление проекта

```bash
cd ~/lk
git pull origin master
docker compose down
docker compose up -d
cd frontend && npm install && npm run build
sudo systemctl reload nginx
```

---

## 9. Безопасность (опционально)

```bash
# Включение UFW
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS (если есть SSL)
sudo ufw enable

# Удаление ненужных портов (например, 8001, 5173 извне)
sudo ufw status
```

Для HTTPS рекомендую Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```
