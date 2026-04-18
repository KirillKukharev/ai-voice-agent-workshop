# Инструкция по развёртыванию — Wazo + AI Bot (sip-service-poc)

Официальная основа стека Docker: [wazo-platform/wazo-docker](https://github.com/wazo-platform/wazo-docker). Репозиторий **sip-service-poc** — **форк** с расширениями (интеграция **wazo-ai-bot**, **speech_to_text**, frontend и др.). Поведение апстрима Wazo сохраняется; дополнительные сервисы описаны в корневом [README.md](README.md).

---

## 1. Назначение

Полноценная UC-платформа **Wazo** (Asterisk, auth, calld, confd, PostgreSQL, RabbitMQ, nginx и др.) плюс:

- **`wazo-ai-bot`** — голосовой бот (ARI/Stasis, Yandex Speech, LLM через Dify/NOCODE и т.д.);
- **`speech_to_text`** — HTTP-сервис распознавания (например GigaAM);
- опционально **frontend** дашборда.

---

## 2. Требования

| Компонент | Минимум |
|-----------|---------|
| ОС | Linux (хост для Docker) |
| Docker + Compose | v2 |
| ОЗУ | **16 ГБ** рекомендуется для полного стека; меньше — риск OOM при сборке |
| Диск | **20+ ГБ** свободно под образы, слои и тома PostgreSQL |
| Git | Для клонирования зависимостей **wazo-auth-keys** и **xivo-config** |
| Время | Первая **сборка** `speech_to_text` / `wazo-ai-bot` может занять **десятки минут** (зависимости, загрузки) |

---

## 3. Зависимости вне репозитория

Wazo в Docker ожидает рядом два репозитория (как в [wazo-docker](https://github.com/wazo-platform/wazo-docker)):

```bash
mkdir -p ~/wazo-deps
cd ~/wazo-deps

git clone https://github.com/wazo-platform/wazo-auth-keys.git
git clone https://github.com/wazo-platform/xivo-config.git
```

Запомните **абсолютный путь** к каталогу `~/wazo-deps` (или аналогу) — он понадобится в **`.env`** как **`LOCAL_GIT_REPOS`**.

---

## 4. Подготовка окружения в корне sip-service-poc

```bash
cd sip-service-poc
cp template.env .env
```

Отредактируйте **`.env`**:

| Переменная | Обязательность | Описание |
|------------|----------------|----------|
| `LOCAL_GIT_REPOS` | **Да** | Абсолютный путь к родительскому каталогу, где лежат **`wazo-auth-keys`** и **`xivo-config`** |
| `XIVO_UUID`, `TZ`, `INIT_TIMEOUT` | Рекомендуется | Обычно достаточно значений из `template.env` |
| `YANDEX_*` | Да, для Yandex STT/TTS | См. [README — переменные окружения](README.md#обязательно-для-работы-ai-бота-wazo-ai-bot-с-yandex-speech) |
| `STT_TOKEN` | Да | Должен совпадать с **`APP_TOKEN`** сервиса `speech_to_text` в `docker-compose.yml` (по умолчанию в репозитории часто `changeme`) |
| `NOCODE_BASE_URL`, `NOCODE_API_KEY` | Да, для диалога | Dify или совместимый API |
| `WAZO_AUTH_PASSWORD` | После bootstrap | Пароль пользователя Wazo Auth (часто совпадает с паролем UI, если вы его меняли) |

Полный перечень и источники значений: [README.md — Переменные окружения](README.md#переменные-окружения).

---

## 5. Сборка и запуск

Из корня **sip-service-poc** (где лежит `docker-compose.yml`):

```bash
# Обновить клоны зависимостей (опционально, перед каждым крупным обновлением)
for repo in wazo-auth-keys xivo-config; do
  git -C "$LOCAL_GIT_REPOS/$repo" pull
done

# Подтянуть базовые образы (часть может отсутствовать в registry — норма для Wazo)
docker compose pull --ignore-pull-failures

# Собрать кастомные сервисы
docker compose build

# Запустить весь стек
docker compose up -d

# Статус
docker compose ps
```

При ошибке сборки из-за **git clone** зависимостей Python (например `ten-vad`) в изолированной сети — повторите сборку или используйте зеркало/кэш; в форке Dockerfile может быть уже предусмотрена загрузка tarball (см. `backend/wazo-docker/Dockerfile-ai-bot` и `speech_to_text/Dockerfile`).

---

## 6. Первичная инициализация Wazo

После старта контейнеров дождитесь завершения **bootstrap** (сервис `bootstrap` / логи `auth`, `confd`).

Веб-интерфейс:

- URL: **https://localhost:8443** (самоподписанный сертификат — примите исключение в браузере)
- Логин по умолчанию в конфигах репозитория: **`root`** / пароль из `wazo-auth` bootstrap (в текущих шаблонах репозитория часто **`changeme`** — **смените в продакшене**)

Проверочный скрипт (как в апстриме):

```bash
./verify.sh
```

Требуются `curl` и `jq`.

---

## 7. Настройка пользователя и линии (кратко)

После входа в UI создайте пользователя и линию для тестового SIP. Пример полей см. в [README.md — Configuring users](README.md#configuring-users-in-the-wazo-ui). Пароль SIP-пользователя должен быть согласован с **`backend/wazo-docker/etc/pjsip.conf`** (внутренний endpoint, напр. `1000`).

---

## 8. Проверка голосового бота

1. Зарегистрируйте софтфон: хост = IP/имя хоста с **Asterisk**, пользователь/пароль = как в PJSIP, домен как в конфиге (часто **`asterisk`**).
2. Наберите расширение приложения бота (в документации репозитория — например **`1000`** для сценария AI Bot).
3. Логи:

```bash
docker compose logs -f asterisk
docker compose logs -f wazo-ai-bot
docker compose logs -f speech_to_text
```

HTTP-проверки:

```bash
# speech_to_text (при пробросе 127.0.0.1:8000 в compose)
curl -s http://localhost:8000/health
```

Сервис **wazo-ai-bot** в типичном `docker-compose.yml` не публикует REST наружу; смотрите health через **логи** или выполните проверку изнутри сети Docker (например `docker compose exec wazo-ai-bot …`), если в образе есть `curl` и известен внутренний порт из `wazo-ai-bot.yml`.

---

## 9. Типичные порты

| Порт | Назначение |
|------|------------|
| 8443 (127.0.0.1 в compose) | HTTPS UI через nginx |
| 5060 / UDP | SIP (Asterisk) — зависит от publish в compose |
| 5039 | ARI внутри сети Docker |
| 8000 | speech_to_text (в compose может быть привязан к 127.0.0.1) |
| 5432 | PostgreSQL (внутренний expose) |

Уточняйте актуальные пробросы в **`docker-compose.yml`**.

---

## 10. Остановка и полная переустановка

```bash
docker compose down --volumes --remove-orphans
```
