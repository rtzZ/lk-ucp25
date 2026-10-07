# Запуск на VPS

## Требования

- Ubuntu 22.04+
- Docker + Docker Compose plugin (`docker compose`)
- Node.js 24 (только для сборки фронтенда)
- Домен, направленный на сервер (для HTTPS)

---

## 1. Подготовка сервера

```bash
sudo apt update && sudo apt upgrade -y

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Node.js 24 (сборка фронтенда)
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo bash -
sudo apt install -y nodejs

# UFW: наружу только SSH/HTTP/HTTPS (8001 и 5432 слушают лишь 127.0.0.1)
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

newgrp docker  # перелогин в группу docker
```

---

## 2. Код и окружение

```bash
cd ~
git clone https://github.com/rtzZ/lk-ucp25.git lk
cd lk
cp .env.example .env
nano .env
```

**Обязательно задать в `.env` для продакшена:**

| Переменная | Значение |
|---|---|
| `POSTGRES_PASSWORD` | длинный случайный пароль |
| `DATABASE_URL` | можно не задавать — compose соберёт из `POSTGRES_*` (`...@db:5432/...`) |
| `YANDEX_SCHEDULE_URL` | edit-ссылка таблицы расписания |
| `YANDEX_GRADES_URL` | edit-ссылка таблицы успеваемости |
| `FRONTEND_URL` | `https://your-domain.com` (CORS-origin) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_GROUP_ID` | **обязательно**: вход только через бота (токен — только сюда, никогда в код). Бота добавить в группу курса |

**НЕ ставить в проде:** `SEED_DEMO=1` (зальёт демо-студентов Иванова/Петрову
в боевую базу). Chromium для синхронизации уже внутри образа backend
(`playwright install` на сервере не нужен). `AUTH_DEV_MODE=1` тоже не ставить:
при заданном `TELEGRAM_BOT_TOKEN` он игнорируется, но без бота отдаёт
пароли прямо в ответе API.

**Привязки Telegram.** Студент пишет боту `/start` и вводит фамилию и имя.
Если ФИО занял чужой аккаунт или студент сменил Telegram:

```bash
docker compose exec app python -m app.admin bindings           # список
docker compose exec app python -m app.admin unbind "Иванов Иван"
```

---

## 3. Запуск backend + PostgreSQL

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app  # логи backend (JSON в stderr)

curl http://localhost:8001/health  # {"status":"ok"}
```

Проверка чтения из БД (первые студенты появятся после первой синхронизации
или сида — см. раздел 6).

---

## 4. Сборка и запуск фронтенда

```bash
cd frontend
npm install
VITE_API_URL=/api npm run build  # относительный путь — API идёт через nginx
```

**Важно:** НЕ `VITE_API_URL=http://localhost:8001` — это адрес внутри сервера,
у посетителей в браузере он не откроется.

Nginx (API — прокси, фронт — статика):

```bash
sudo apt install -y nginx
sudo rm -f /etc/nginx/sites-enabled/default
sudo tee /etc/nginx/sites-available/lk > /dev/null << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /home/ubuntu/lk/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/lk /etc/nginx/sites-enabled/lk
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 5. Бэкапы PostgreSQL

```bash
# Разовый дамп
docker compose exec db pg_dump -U lk lk | gzip > ~/lk-backup-$(date +%F).sql.gz

# Ежедневный крон (в 3:00, хранить 7 штук)
(crontab -l 2>/dev/null; echo "0 3 * * * docker compose -f $HOME/lk/docker-compose.yml exec -T db pg_dump -U lk lk | gzip > $HOME/lk-backup-\$(date +\%F).sql.gz && ls -t $HOME/lk-backup-*.sql.gz | tail -n +8 | xargs -r rm") | crontab -
```

---

## 6. Обновление проекта

```bash
cd ~/lk
git pull
docker compose up -d --build  # пересобрать backend при изменениях
docker compose logs -f app
cd frontend && npm install && VITE_API_URL=/api npm run build
sudo systemctl reload nginx
```

---

## 7. Dev-режим на сервере (только для отладки)

```bash
# Backend без Docker: python3.12-venv + pip install -e "backend/.[dev]"
# + playwright install --with-deps chromium, запуск от НЕ-root
# (Chromium не стартует от root без CHROMIUM_NO_SANDBOX=1).
cd frontend
npm install
VITE_API_URL=http://localhost:8001 npm run dev  # порт 5173
```
