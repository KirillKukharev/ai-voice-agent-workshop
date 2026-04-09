# Инструкция по развёртыванию — AVR (Agent Voice Response)

Официальный апстрим инфраструктуры: [agentvoiceresponse/avr-infra](https://github.com/agentvoiceresponse/avr-infra). Данный каталог **AVR** — форк экосистемы [Agent Voice Response](https://github.com/agentvoiceresponse); основная логика запуска совпадает с апстримом.

---

## 1. Назначение

**AVR** связывает **Asterisk** с цепочкой **ASR → LLM → TTS** (или единым **speech-to-speech**) через **Audiosocket**: аудио вызова уходит в **AVR Core**, далее — в подключаемые по HTTP/WebSocket сервисы.

---

## 2. Требования

| Компонент | Минимум |
|-----------|---------|
| Docker | 20.10+ |
| Docker Compose | v2 (`docker compose`) |
| ОЗУ | 4–8 ГБ в зависимости от выбранных моделей (локальный Vosk легче, облако — тоньше) |
| Диск | несколько ГБ под образы и модели |
| Опционально: Node.js 18+ | Только для локальной разработки **avr-app** (GUI) |

**Сеть:** освободите порты под выбранный профиль: часто **5060** (SIP TCP/UDP), **8088/8089** (если используется ARI в сценарии с приложением), порты **AVR Core** и провайдеров, RTP. Для `docker-compose-app.yml` — **80**, **8080** и записи в `/etc/hosts` (`avr.localhost`, `api.localhost` и т.д. — см. [avr-infra/README.md](avr-infra/README.md)).

---

## 3. Структура каталогов (кратко)

| Путь | Роль |
|------|------|
| `avr-infra/` | **Точка входа**: `docker-compose-*.yml`, Asterisk, `.env.example` |
| `avr-app/` | Админ-панель (NestJS + Next.js), опционально |
| `avr-vad/`, `avr-llm-openrouter/`, `avr-yandex-speechkit-adapter/` | Библиотеки и адаптеры |

Все команды ниже выполняются из **`avr-infra/`**, если не указано иное.

```bash
cd AVR/avr-infra
```

---

## 4. Подготовка переменных окружения

```bash
cp .env.example .env
```

Отредактируйте **`.env`**:

- Для классической схемы ASR+LLM+TTS задайте **`ASR_URL`**, **`LLM_URL`**, **`TTS_URL`** (точные шаблоны URL — в [avr-infra/README.md](avr-infra/README.md)).
- Для **speech-to-speech** укажите **`STS_URL`** (примеры: `docker-compose-openai-realtime.yml`, `docker-compose-ultravox.yml`).
- Добавьте **API-ключи** выбранного провайдера (OpenAI, Deepgram, Anthropic, Google и т.д.) — см. таблицу примеров в апстрим README.

Дополнительно в форке может быть **`avr-infra/.env.yandex.example`** — шаблон под Yandex SpeechKit.

**Важно:** файл `.env` не должен попадать в публичный git.

---

## 5. Выбор профиля Compose

Таблица файлов и провайдеров — в [avr-infra/README.md — Table of Compose Files](avr-infra/README.md#table-of-compose-files).

Примеры:

```bash
# OpenAI (LLM) + Deepgram (ASR/TTS)
docker compose -f docker-compose-openai.yml up -d

# Anthropic + Deepgram
docker compose -f docker-compose-anthropic.yml up -d

# OpenAI Realtime (STS)
docker compose -f docker-compose-openai-realtime.yml up -d

# Локальный Vosk + облачные LLM/TTS
docker compose -f docker-compose-vosk.yml up -d
```

Первая сборка может занять время (скачивание образов).

Проверка контейнеров:

```bash
docker compose -f docker-compose-<ваш-профиль>.yml ps
docker compose -f docker-compose-<ваш-профиль>.yml logs -f avr-core
```

(Имена сервисов смотрите в выбранном YAML.)

---

## 6. Полный стек с веб-интерфейсом (avr-app)

```bash
cd avr-infra
cp .env.example .env
# Заполните JWT_SECRET, ADMIN_*, при необходимости ARI_*, ключи провайдеров, MySQL из комментариев в апстрим README

docker compose -f docker-compose-app.yml up -d
```

Дальше: [avr-app/README.md](avr-app/README.md) — доступ к UI, учётные записи, настройка агентов.

---

## 7. Тестирование SIP

1. Зарегистрируйте софтфон на Asterisk из compose (часто пользователь **`1000`**, пароль **`1000`**, транспорт **TCP** — уточните в `avr-infra/asterisk/conf/pjsip.conf` для вашего профиля).
2. Проверьте **эхо-тест** (в апстрим документации указано расширение **`600`**).
3. Вызовите расширение, ведущее на **AVR** (в типичном примере **`5001`** и `AudioSocket` — см. [avr-infra README — Testing](avr-infra/README.md)).

Если используете **свой** Asterisk, отключите сервис `avr-asterisk` в compose и пропишите в своём `extensions.conf` вызов `AudioSocket` на хост:порт **AVR Core** (см. апстрим README, раздел *Using Your Existing Asterisk Installation*).

---

## 8. NAT и внешний SIP

Для корректного RTP за NAT настройте в `pjsip.conf` **`external_media_address`** / **`external_signaling_address`** (или аналоги) на публичный IP — см. комментарии в конфигах и [wiki AVR](https://wiki.agentvoiceresponse.com/en/home).

---

## 9. Остановка и очистка

```bash
docker compose -f docker-compose-<профиль>.yml down
# Полная очистка данных томов (осторожно):
docker compose -f docker-compose-<профиль>.yml down -v
```
