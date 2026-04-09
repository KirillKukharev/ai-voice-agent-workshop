# AVR (Agent Voice Response)

Форк экосистемы **[Agent Voice Response](https://github.com/agentvoiceresponse)**; апстрим инфраструктуры: **[agentvoiceresponse/avr-infra](https://github.com/agentvoiceresponse/avr-infra)**.

**Полная инструкция по установке и запуску:** [SETUP.md](./SETUP.md).

## Краткий обзор

- **Docker** и Docker Compose v2 для сценариев в `avr-infra/`.
- **Опционально** для разработки GUI (`avr-app`): Node.js 18+, npm 9+.
- **Сеть:** порты под выбранный compose (часто `5060`, `8088`, `8089`, RTP; для стека с Traefik — `80`, `8080` и записи в `/etc/hosts` вида `avr.localhost`, `api.localhost`).
- **Секреты:** создайте `avr-infra/.env` из `.env.example`; ключи провайдеров (Deepgram, OpenAI, OpenRouter, Google и т.д.) получаете у соответствующих сервисов.

## Структура каталогов

| Путь | Роль |
|------|------|
| `avr-infra/` | Docker Compose профили, Asterisk (`asterisk/conf/`), точка сборки headless и full-stack. |
| `avr-app/` | Админ-панель: NestJS backend + Next.js frontend. |
| `avr-vad/` | VAD для пайплайнов. |
| `avr-llm-openrouter/` | Пример LLM через OpenRouter. |
| `avr-yandex-speechkit-adapter/` | Адаптер Yandex SpeechKit. |

Детали по каждому `docker-compose-*.yml` и переменным — в [avr-infra/README.md](./avr-infra/README.md).

## Быстрый старт (headless)

```bash
cd avr-infra
cp .env.example .env
# задайте ASR_URL, LLM_URL, TTS_URL или STS_URL и ключи провайдера
docker compose -f docker-compose-openai.yml up -d
```

## Быстрый старт (GUI + приложение)

```bash
cd avr-infra
cp .env.example .env
docker compose -f docker-compose-app.yml up -d
```

Далее — [avr-app/README.md](./avr-app/README.md).

## Архитектура (логический поток)

1. **Asterisk** принимает вызов и по **Audiosocket** отдаёт аудио в **AVR Core**.
2. **ASR** (или цепочка с VAD / `avr-asr-to-stt`) преобразует речь в текст.
3. **LLM** формирует ответ (или **STS** объединяет шаги).
4. **TTS** синтезирует речь; core возвращает аудио в Asterisk.

## Возможности

- Смена провайдеров через отдельные compose-файлы (Anthropic, OpenAI, Google, Deepgram, Vosk, n8n, Gemini и др.).
- Режимы **speech-to-speech** (`STS_URL`).
- **WebRTC** и SIP; настройка NAT в `pjsip.conf`.
- Фоновые шумы для тестов: `avr-infra/ambient_sounds/`.

## Дополнительно

- Пример переменных Yandex: `avr-infra/.env.yandex.example`.
- OpenRouter: `avr-llm-openrouter/.env.example`.
- Сообщество и wiki: [GitHub agentvoiceresponse](https://github.com/agentvoiceresponse), [wiki](https://wiki.agentvoiceresponse.com/en/home).
