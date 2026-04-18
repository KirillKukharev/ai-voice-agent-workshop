import type { DashboardConnectionStatus } from "../types/events";
import type { DashboardState } from "../types/types";

export const INITIAL_STATE: DashboardState = {
  sessionId: null,
  userTranscription: { text: null },
  botResponse: { text: null, citations: [] },
  intents: [],
  ragChunks: [],
  toolCall: null,
  actions: [],
  lastEvent: undefined,
  lastError: null,
};

export const DASHBOARD_EVENT_LIMIT = 5;

export const STATUS_CONFIG: Record<
  DashboardConnectionStatus,
  { label: string; className: string }
> = {
  connected: { label: "В реальном времени", className: "bg-accent-bot" },
  connecting: { label: "Подключаемся…", className: "bg-accent-user" },
  disconnected: { label: "Отключено", className: "bg-white/30" },
  error: { label: "Ошибка соединения", className: "bg-accent-error" },
};
