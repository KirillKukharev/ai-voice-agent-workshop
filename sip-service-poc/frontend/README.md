# HBF Hotels Demo — AI Dashboard

Одностраничное приложение, демонстрирующее, как гостиничный AI‑консьерж ведёт диалог с гостем, анализирует намерения, обращается к базам знаний и фиксирует действия в операционных системах отеля. Проект построен на React 19, Vite 7 и TypeScript 5.9 и включает визуальные эффекты Tailwind + Framer Motion.

## Основные возможности

- **Диалог в реальном времени** — живая транскрипция гостя и стриминговый ответ бота с эффектом пишущей машинки (`TypewriterText` и `BotResponse`).
- **Прозрачный ход мыслей AI** — отображение найденных RAG‑фрагментов и вызовов инструментов (`RagChunksDisplay`, `ToolCallDisplay`).
- **Единая временная шкала** — все события прокручиваются через `dashboardReducer`, что упрощает замену моков на WebSocket или SSE.
- **Mock‑режим по таймеру** — `MOCK_TIMELINE` генерирует события с небольшой задержкой, что позволяет показать сценарий end‑to‑end без бэкенда.
- **Tailwind‑тема под брендинг** — кастомные неоновые акценты, анимации сетки и пыли для hero‑фона.

## Требования

- Node.js 20+
- npm 10+ (или другой пакетный менеджер)

## Быстрый старт

```bash
git clone https://github.com/hbf-hotels-demo/frontend.git
cd frontend
npm install
npm run dev
```

Приложение будет доступно по адресу `http://localhost:3003`.

### Сценарии npm

| Скрипт          | Назначение                               |
| --------------- | ---------------------------------------- |
| `npm run dev`   | Dev‑сервер Vite с HMR                    |
| `npm run build` | TypeScript build + Vite production build |
| `npm run preview` | Просмотр собранного `/dist`            |
| `npm run lint`  | ESLint + type‑checked правила            |

## Переменные окружения

| Переменная            | Значение по умолчанию | Описание |
| --------------------- | --------------------- | -------- |
| `VITE_USE_MOCK`       | `true`                | Если `true`, `App` проигрывает `MOCK_TIMELINE`; при `false` ожидается внешний источник событий. |
| `VITE_WS_URL`         | —                    | Необязательный WebSocket‑endpoint для реального источника `DashboardEvent`. При отсутствии переменной используется `ws://localhost:8000` в dev или `wss://<host>/ws` в проде. |

Создайте `.env`, чтобы переопределять значения:
```
VITE_USE_MOCK=false
VITE_WS_URL=ws://localhost:8000/ws
```

## Структура проекта

```
src/
  components/        # UI-блоки: чат, RAG, тулкиты
  shared/
    mock.ts          # временная шкала событий
    reducer.ts       # централизованный state machine
    constants.ts     # INITIAL_STATE, цвета, лимиты
  types/             # типы событий и DashboardState
  App.tsx            # композиция колонок и потоков данных
  main.tsx           # точка входа React
```

## Поток данных

1. `App.tsx` инициализирует `useReducer(dashboardReducer, INITIAL_STATE)`.
2. При `VITE_USE_MOCK=true` `MOCK_TIMELINE` диспатчит события раз в ~1.2 секунды.
3. Редьюсер обновляет срезы состояния (`userTranscription`, `botResponse`, `ragChunks`, `toolCall`, `actions`).
4. UI‑компоненты автоматически анимируют появление новых данных.

Чтобы перейти на реальные данные, замените мок‑таймер на WebSocket/SSE и диспатчите события того же типа `DashboardEvent`.

## Тестирование и качество

- ESLint 9 с type‑aware правилами (`eslint.config.js`).
- TypeScript строгий (`tsconfig.app.json` + `tsconfig.node.json`).
- Перед коммитом рекомендуется запускать `npm run lint && npm run build`.

## Дальнейшие шаги

- Подключить реальный бекенд для tool calls и бронирований.
- Раскомментировать `IntentDisplay` и снабдить его данными модели.
- Добавить e2e‑тесты (Playwright/Cypress) для сценариев бронирования.

## Лицензия

Проект распространяется на условиях лицензии, указанной в корне репозитория (если файл отсутствует — уточните условия у владельца HBF Hotels Demo).
