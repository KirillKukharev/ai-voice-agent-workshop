# WAZO AI Bot

**Пошаговый запуск и зависимости:** см. [SETUP.md](./SETUP.md).

## Overview

This repository contains a WAZO Platform setup with AI Bot integration for voice call processing. The system includes:

- **WAZO Platform** - full-featured IP telephony
- **AI Bot Service** - a voice bot with support for the Yandex Speech API
- **Speech-to-Text** - speech recognition service
- **Asterisk** - SIP server with ARI (Asterisk REST Interface)

## Переменные окружения

Все секреты и пути к репозиториям задаются через файл **`.env` в корне проекта** (`sip-service-poc/.env`). Его **нет в git** — скопируйте шаблон и заполните значения:

```bash
cp template.env .env
```

Ниже — что обязательно, что опционально и **где взять значения**.

### Обязательно для `docker compose up`

| Переменная | Назначение | Где взять |
|------------|------------|-----------|
| `LOCAL_GIT_REPOS` | Абсолютный путь к каталогу, в котором **лежат рядом** клоны `wazo-auth-keys` и `xivo-config` (родительский каталог, не сам `sip-service-poc`). Используется в `docker-compose.yml` для bind-mount’ов Asterisk и agid. | Создайте каталог (например `~/wazo-deps`), выполните там `git clone` репозиториев из раздела [Cloning repositories](#2-cloning-repositories) и укажите **полный путь** к этому каталогу. |
| `XIVO_UUID` | Идентификатор инсталляции Wazo в формате UUID. | Для локальной разработки можно оставить значение из `template.env`. Для нового стенда сгенерируйте UUID (например `uuidgen` в Linux) и при необходимости согласуйте с документацией Wazo. |
| `INIT_TIMEOUT`, `TZ` | Таймауты инициализации и часовой пояс контейнеров. | `TZ` — IANA-имя зоны (`Europe/Moscow` и т.д.). `INIT_TIMEOUT` обычно оставляют как в шаблоне. |

Пароли **PostgreSQL / Wazo / ARI** для поднятия стека зашиты в файлах `backend/wazo-docker/etc/*.yml` и в `docker-compose.yml` (дефолт `changeme`). Их меняют там же и синхронно, а не только в `.env`, если вы ужесточаете безопасность.

### Обязательно для работы AI-бота (`wazo-ai-bot`) с Yandex Speech

Сервис бота при старте поднимает **Yandex STT/TTS** через IAM. В `Settings` ожидаются переменные с префиксом `YANDEX_*` (см. `backend/wazo-docker/bin/init_ai_bot_config/config/settings.py`).

| Переменная | Назначение | Где взять |
|------------|------------|-----------|
| `YANDEX_SERVICE_ACCOUNT_ID` | ID сервисного аккаунта в Yandex Cloud. | [Yandex Cloud Console](https://console.cloud.yandex.ru/) → **Сервисные аккаунты** → выбранный аккаунт → поле **Идентификатор**. |
| `YANDEX_SA_KEY_ID` | ID статического ключа доступа. | Тот же аккаунт → вкладка **Ключи** → создать **статический ключ** (Access Key) → сохраните **идентификатор ключа**. |
| `YANDEX_PRIVATE_KEY` | Секретная часть ключа (PEM или строка, как ожидает ваш код/SDK). | Выдаётся **один раз** при создании статического ключа; храните только в `.env` или секрет-хранилище. |
| `YANDEX_FOLDER_ID` | Каталог (folder), в котором включены **SpeechKit** и квоты. | Console → **Каталог** → **Идентификатор каталога**. |

Дополнительно в консоли Yandex: включите API **SpeechKit**, выдайте роли сервисному аккаунту на каталог (например `ai.speechkit-stt.user`, `ai.speechkit-tts.user` или роль вроде `editor` на каталог — по вашей политике).

### Связка бота и сервиса распознавания речи

| Переменная | Назначение | Где взять |
|------------|------------|-----------|
| `STT_TOKEN` | Bearer-токен для HTTP-запросов бота к `speech_to_text` (`/v1/speech_recognition/...`). | Должен **совпадать** с `APP_TOKEN`, который задан для сервиса `speech_to_text` в **`docker-compose.yml`** (в репозитории по умолчанию `changeme`). Если меняете токен в compose — задайте то же значение в `.env` как `STT_TOKEN`. |

Опционально для загрузки моделей GigaAM с Hugging Face при отсутствии локальных файлов: переменная **`HF_TOKEN`** (токен с [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)) — задаётся в окружении контейнера/сборки `speech_to_text`, если используете соответствующий сценарий (см. код в `speech_to_text/GigaAM`).

### LLM (диалог, Dify / «nocode»)

| Переменная | Назначение | Где взять |
|------------|------------|-----------|
| `NOCODE_BASE_URL` | Базовый URL API вашего Dify (или совместимого бэкенда). | URL развёрнутого Dify, например `https://api.dify.ai` или ваш инстанс. В коде по умолчанию-заглушка `https://example.com` — её **нужно заменить**. |
| `NOCODE_API_KEY` | Ключ API для авторизации запросов к LLM-слою. | В панели Dify: **Settings → API Access** / ключ приложения (App API Key). Без него при старте поднимется ошибка `NOCODE_API_KEY is required`. |

`OPENAI_API_KEY` в шаблоне зарезервирован под сценарии, где OpenAI вызывается напрямую; в текущем `Settings` бота может не использоваться — уточняйте по своей ветке кода.

### Airtable (опционально)

Используются для бронирований/тикетов и событий tool-call, если эта интеграция у вас включена.

| Переменная | Где взять |
|------------|-----------|
| `AIRTABLE_API_KEY` | [Airtable → Developer hub → Personal access tokens](https://airtable.com/create/tokens) |
| `AIRTABLE_BASE_ID` | В веб-интерфейсе базы: **Help → API documentation** — префикс в URL вида `appXXXXXXXX`. |
| `AIRTABLE_TICKETS_TABLE`, `AIRTABLE_BOOKINGS_TABLE` | Имена таблиц внутри базы (как в UI). |

### Wazo Auth (REST)

| Переменная | Назначение | Где взять |
|------------|------------|-----------|
| `WAZO_AUTH_USERNAME` | Учётная запись для REST-вызовов к Wazo Auth (часто `root`). | Совпадает с пользователем, которым вы входите в API/CLI после bootstrap. |
| `WAZO_AUTH_PASSWORD` | Пароль этой учётной записи. | Задаётся при первичной настройке (wizard / `bootstrap_user_password` в `wazo-auth.yml` и связанных конфигах). Должен совпадать с реальным паролем стенда, не с шаблоном из git, если вы его меняли. |

### ARI и поля `ASTERISK_*` в шаблоне

Подключение бота к Asterisk в **текущем** корневом `docker-compose.yml` задаётся блоком `environment` сервиса **`wazo-ai-bot`** (`ARI_HOST`, `ARI_PORT`, `ARI_USER`, `ARI_PASSWORD`, `ARI_APP_NAME`). Переменные `ASTERISK_*` и пустой `ARI_APP_NAME` в `template.env` оставлены для **документации и внешних сценариев**; при необходимости вы можете продублировать значения здесь или перенести их в compose.

Имя приложения ARI (`ARI_APP_NAME` / `voice-bot`) должно совпадать с `stasis` в диалплане Asterisk. Учётные данные ARI — в `backend/wazo-docker/etc/asterisk-ari.conf` (пользователь по умолчанию `ariuser`).

### Модели

| Переменная | Назначение |
|------------|------------|
| `STT_MODEL` | Модель распознавания (например `gigaam`). |
| `TTS_MODEL` | Движок/модель синтеза (например `yandex`). |

Имеют дефолты в коде; в `.env` переопределяют их при необходимости.

### Дашборд (frontend)

Отдельно от корневого `.env`, при сборке фронтенда можно использовать **`frontend/.env`** (см. `frontend/.env.template`):

| Переменная | Назначение |
|------------|------------|
| `VITE_USE_MOCK` | `true` — демо-таймлайн без бэкенда; `false` — реальный WebSocket. |
| `VITE_WS_URL` | URL WebSocket (если не задан, в коде есть fallback на `ws://localhost:8000` и др.). |

Токены API во **frontend** не кладутся: только публичные `VITE_*` попадают в браузер.

### Дополнительный шаблон для образа AI-бота

В `backend/wazo-docker/bin/init_ai_bot_config/.env.template` перечислены переменные, которые удобно держать под рукой при локальной отладке пакета `init_ai_bot_config`; при запуске через корневой `docker compose` основной источник правды — **корневой `.env`** плюс `environment` в `docker-compose.yml`.

---

## Environment preparation


### 1. Setting Environment Variables

Создайте `.env` из шаблона и задайте как минимум `LOCAL_GIT_REPOS` (см. [Переменные окружения](#переменные-окружения)). При необходимости экспортируйте переменную в shell для других сценариев:

```bash
export LOCAL_GIT_REPOS=~/path/to/your/repository

# Added to ~/.bashrc for permanent use
echo 'export LOCAL_GIT_REPOS=~/path/to/your/repository' >> ~/.bashrc
source ~/.bashrc
```


### 2. Cloning repositories

```bash
cd ~/path/to/your/repository

# Clone the necessary dependencies
git clone https://github.com/wazo-platform/wazo-auth-keys.git
git clone https://github.com/wazo-platform/xivo-config.git
```

## System deployment

### 1. Build and launch

```bash
# Updating dependencies
for repo in wazo-auth-keys xivo-config; do
    git -C "$LOCAL_GIT_REPOS/$repo" pull
done

# Downloading the basic images
docker compose pull --ignore-pull-failures

# Collecting all
docker compose build

# Launching all
docker compose up -d

# Checking the status
docker compose ps
```


## Access to the WAZO UI

### Web interface
- **URL**: https://localhost:8443
- **Login**: `root`
- **Password**: `changeme` (default in repo configs; override for production)

## Configuring users in the WAZO UI

### 1. Creating a user

1. **Log in to the WAZO UI** at https://localhost:8443
2. **Go to the "Users" section** (Users)
3. **Click "Add User"** (Add User)
4. **Fill out the form:**
-**First name**: User
   - **Last name**: 1000
- **Username**: "User1000"
- **Password**: `changeme` (or your policy; align with SIP user in `pjsip.conf`)
- **Email**: test@example.com

### 2. Creating a Line

1. **Go to the "Lines" section** (Lines)
2. **Click "Add Line"** (Add Line)
3. **Fill out the form:**
- **Label**: test_line
- **Name**: label_name
- **Transport**: transport-udp
   - **Context**: context_name

## Testing calls

### 1. Configuring the SIP client

Use any SIP client (for example, Zoiper, X-Lite, or a mobile application):

- **SIP server**: host where Asterisk listens (e.g. `localhost` or your server IP)
- **User name**: 1000
- **Domain**: asterisk
- **Login**: 1000
- **Password**: `changeme` (same as internal endpoint in `backend/wazo-docker/etc/pjsip.conf`)
- **Display Name**: User1000

Select an audio codec from the list:
> G.711 A-law, G.711 u-law, G.722 16 kHz


### 2. Testing calls

1. **Call to AI Bot**: dial 1000
2. **Queue call**: dial 1002, 1008
3. **A simple message that the queue is busy**: dial 1004

### 3. Checking logs

```bash
# Asterisk
docker compose logs -f asterisk

# AI Bot logs
docker compose logs -f wazo-ai-bot

# Speech-to-Text Logs
docker compose logs -f speech_to_text
```

## Diagnostics and monitoring

### Checking the AI Bot status

```bash
# AI Bot
curl -s http://localhost:9495/status

# Speech-to-Text
curl -s http://localhost:8000/health
```


### Cleaning and reinstalling

```bash
# Complete cleaning
docker compose down --volumes --remove-orphans
docker system prune -a

# Reinstalling
docker compose up -d
```

## Security

Set autoscanning logs and ban external ips to avoid ddos.
```bash
pkill -f auto-sip-blocker.sh  # stop previous task

nohup ./auto-sip-blocker.sh &  # start new task
```

Show list of banned ip
```
iptables -L DOCKER-USER -n | grep DROP
```

Checked that script is running
```
ps aux | grep -E "(auto-sip-blocker|sip_blocker)" | grep -v grep
```

## Generate audio speech replies from text prompts

1. Move to `bin/init-ai-bot-config/utils` directory
2. Run command:
```bash
python generate_audio_files.py
```
3. Add generated audio file in general pipeline.
