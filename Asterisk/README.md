# Docker: Asterisk «light» (общий образ)

Каталог содержит **сборку Asterisk** из исходников (Ubuntu 22.04, PJSIP, ARI, Stasis, chan_audiosocket и т.д.). Образ можно собирать **один раз** и применять как **отдельный SIP/ARI-сервер** для любой из трёх линий в монорепозитории `asterisk/`:

| Проект | Как использовать этот Asterisk |
|--------|--------------------------------|
| **[Asterisk-AI-Voice-Agent](../Asterisk-AI-Voice-Agent/)** | Штатный сценарий: диалплан уже содержит `Stasis(asterisk-ai-voice-agent)`, ARI/AMI по умолчанию `asterisk`/`asterisk`. |
| **[AVR](../AVR/)** | Подключите в `extensions.conf` вызов **AudioSocket** на хост:порт **AVR Core** (см. [avr-infra](https://github.com/agentvoiceresponse/avr-infra)); при необходимости отключите встроенный Asterisk в compose AVR. |
| **[sip-service-poc](../sip-service-poc/)** | Стек Wazo поднимает **свой** Asterisk из `backend/wazo-docker/Dockerfile-asterisk` (образ **wazoplatform/asterisk**). Этот «light»-образ **не заменяет** его в compose; используйте только если намеренно разносите Wazo и Asterisk или для тестов. |

---

## Откуда берётся контейнер `docker ps` с именем `asterisk`

Если вы видите контейнер с именем **`asterisk`** и портами вроде:

`5060/tcp`, `5060/udp`, `10000-10020/udp`, `8088`, `8089`, `5038`, `9100`

— это **не** обязательно `docker compose` из `sip-service-poc`. Такой набор портов соответствует **ручному** запуску образа **`asterisk-light:latest`**, собранного из **`Dockerfile-asterisk`**:

1. Сборка (контекст — **этот каталог** `Asterisk/`, в нём есть `scripts/asterisk-docker-entrypoint.sh`):

   ```bash
   cd Asterisk
   docker build --network=host -f Dockerfile-asterisk -t asterisk-light:latest .
   ```

2. Запуск контейнера **вручную** (`docker run`), например:

   ```bash
   docker run -d --name asterisk \
     -e AST_EXTERNAL_IP=172.30.100.139 \
     -p 5060:5060/udp -p 5060:5060/tcp \
     -p 10000-10020:10000-10020/udp \
     -p 5038:5038/tcp -p 8088:8088/tcp -p 8089:8089/tcp -p 9100:9100/tcp \
     asterisk-light:latest
   ```

Чтобы убедиться в происхождении:

```bash
docker inspect asterisk --format '{{.Config.Image}} {{.Image}}'
docker image inspect asterisk-light:latest --format '{{.Id}}'
```

---

## Порты (типичные)

| Порт | Назначение |
|------|------------|
| 5060 UDP/TCP | SIP (PJSIP) |
| 10000–10020 UDP | RTP (задано в образе) |
| 8088 | HTTP ARI / веб |
| 8089 | HTTPS |
| 5038 | Доп. сервис в конфиге образа (см. Dockerfile) |
| 9100 | Prometheus (если включено в `prometheus.conf`) |

Переменная **`AST_EXTERNAL_IP`** — адрес, который телефон может достичь (NAT); entrypoint подставляет `external_media_address` / `external_signaling_address` в PJSIP.

---

## Безопасность

Пароли ARI/AMI и SIP в образе по умолчанию **учебные** (`asterisk`/`asterisk`, `1001`/`1001` и т.д.). Для любой публичной сети замените их в своих `my_*.conf` или пересоберите слой.

---

## Файлы

| Файл | Назначение |
|------|------------|
| `Dockerfile-asterisk` | Многостадийная сборка Asterisk из исходников |
| `scripts/asterisk-docker-entrypoint.sh` | Точка входа: NAT через `AST_EXTERNAL_IP`, запуск `asterisk -f` |
| `scripts/run-asterisk-example.sh` | Пример `docker run` (из каталога `Asterisk/`: `./scripts/run-asterisk-example.sh`) |
