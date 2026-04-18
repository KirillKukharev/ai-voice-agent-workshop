import type { ActionItem, BotCitation, IntentItem, RagRetrievalEvent } from "./events";

export interface DashboardState {
  sessionId: string | null;
  userTranscription: { text: string | null; timestamp?: string };
  botResponse: {
    text: string | null;
    latencyMs?: number;
    citations?: BotCitation[];
  };
  intents: IntentItem[];
  ragChunks: RagRetrievalEvent["payload"]["chunks"];
  toolCall: {
    toolName?: string;
    status?: "pending" | "success" | "error";
    payload?: Record<string, unknown>;
  } | null;
  actions: ActionItem[];
  lastEvent?: string;
  lastError?: string | null;
}
