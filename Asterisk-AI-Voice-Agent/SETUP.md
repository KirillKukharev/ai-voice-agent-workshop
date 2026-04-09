# Инструкция по развёртыванию — Asterisk AI Voice Agent (AVA)

Официальный апстрим: [hkjarral/AVA-AI-Voice-Agent-for-Asterisk](https://github.com/hkjarral/AVA-AI-Voice-Agent-for-Asterisk). Этот каталог — **форк** с доработками; базовая архитектура и документация совпадают с апстримом. Ниже — пошаговый запуск для публичного стенда.

---

## 1. Назначение

Платформа голосового агента для **Asterisk / FreePBX**: контейнер **ai_engine** (оркестрация вызовов, ARI), опционально **local_ai_server** (локальные STT/LLM/TTS), **Admin UI** для настройки провайдеров и сценариев.

---

## 2. Требования

| Компонент | Минимум | Примечание |
|-----------|---------|------------|
| ОС | Linux x86_64 с systemd | См. [docs/SUPPORTED_PLATFORMS.md](docs/SUPPORTED_PLATFORMS.md) |
| Docker | 24+ рекомендуется | Плагин Compose v2 (`docker compose`) |
| ОЗУ | от 4 ГБ (облачные провайдеры) | Локальный гибрид / полностью локальный режим — 8–16+ ГБ |
| Asterisk | 18+ с включённым **ARI** | Можно на том же хосте или отдельно; см. [INSTALLATION.md](docs/INSTALLATION.md) |
| Сеть | Свободные порты см. §6 | Проброс портов при удалённом доступе к UI |

**GPU (опционально):** для локального инференса см. [docs/LOCAL_ONLY_SETUP.md](docs/LOCAL_ONLY_SETUP.md) и overlay `docker-compose.gpu.yml`.

---

## 3. Подготовка репозитория

Рабочая директория — корень проекта (этот каталог):

```bash
cd Asterisk-AI-Voice-Agent
```

---

## 4. Обязательный preflight

Скрипт создаёт `.env` из `.env.example`, задаёт `JWT_SECRET`, проверяет окружение и при необходимости выравнивает права (UID/GID Asterisk).

```bash
chmod +x preflight.sh
sudo ./preflight.sh --apply-fixes
```

Проверьте, что в каталоге появился файл **`.env`** и в нём заполнены ключи провайдеров, которые вы планируете использовать (после мастера в UI или вручную по [Configuration](README.md#-configuration)).

---

## 5. Запуск Admin UI

Имя проекта Compose фиксирует сеть и тома; рекомендуется тот же префикс, что в документации апстрима:

```bash
docker compose -p asterisk-ai-voice-agent up -d --build --force-recreate admin_ui
```

Откройте в браузере:

- локально: `http://localhost:3003`
- на сервере: `http://<IP>:3003`

**Учётные данные по умолчанию:** `admin` / `admin` — **смените пароль** и ограничьте доступ (firewall, VPN, reverse proxy).

Дальше следуйте **Setup Wizard** в интерфейсе: провайдеры, транспорт аудио, при необходимости — генерация фрагментов диалплана.

---

## 6. Запуск ai_engine

Без **ai_engine** health-check и реальные вызовы работать не будут.

```bash
docker compose -p asterisk-ai-voice-agent up -d --build ai_engine
```

Проверка:

```bash
curl -s http://localhost:15000/health
# Ожидается JSON с "healthy" / status ok (см. актуальный ответ в документации)
```

Логи:

```bash
docker compose -p asterisk-ai-voice-agent logs -f ai_engine
```

При необходимости поднимите остальные сервисы из корневого `docker-compose.yml` (например `local_ai_server`) согласно выбранному профилю в [LOCAL_ONLY_SETUP.md](docs/LOCAL_ONLY_SETUP.md).

---

## 7. Подключение Asterisk / FreePBX

1. Включите **ARI** в `http.conf` / `ari.conf`, создайте пользователя ARI и совместите пароли с `.env` / конфигом движка.
2. Используйте диалплан, предлагаемый мастером или [примеры в README](README.md#-advanced-setup-cli) (приложение **Stasis**, имя приложения должно совпадать с конфигурацией `ai-agent.yaml`).
3. Учтите **режим транспорта** (AudioSocket vs ExternalMedia RTP): [docs/Transport-Mode-Compatibility.md](docs/Transport-Mode-Compatibility.md).

Подробный чеклист первого успешного звонка: [docs/INSTALLATION.md](docs/INSTALLATION.md).

---

## 8. CLI (альтернатива UI)

```bash
./install.sh
agent setup
```

Диагностика:

```bash
agent check
agent check --local   # локальный AI-сервер на этой машине
```

См. раздел [Agent CLI Tools](README.md#-agent-cli-tools) в основном README.

---

## 9. Типичные порты

| Порт | Сервис |
|------|--------|
| 3003 | Admin UI |
| 15000 | ai_engine (HTTP API / health) |
| Задаётся в Asterisk | ARI (часто 8088 / 8089) |
| 5060 / UDP-TCP | SIP (на стороне Asterisk) |
| RTP | Диапазон из `rtp.conf` |

Конфликты с другими стеками (AVR, Wazo) на одном хосте устраняйте сменой портов или изоляцией сети.

---

## 10. Конфигурация (кратко)

- **`config/ai-agent.yaml`** — базовые golden-профили.
- **`config/ai-agent.local.yaml`** — ваши переопределения.
- **`.env`** — секреты и ключи API.

---

## 11. Безопасность

- Сменить пароль Admin UI и закрыть порт 3003 от интернета.
- Не публиковать `.env` и `ai-agent.local.yaml`.
- Ознакомиться с [SECURITY.md](SECURITY.md) апстрима.
