export type DashboardEventName =
  | "session_start"
  | "session_end"
  | "user_transcription"
  | "bot_response"
  | "intent_analysis"
  | "rag_retrieval"
  | "tool_call"
  | "ticket_created"
  | "booking_created"
  | "ticket_loaded"
  | "booking_loaded"
  | "heartbeat"
  | "error";

export interface BaseDashboardEvent<
  TName extends DashboardEventName,
  TPayload = Record<string, unknown>,
> {
  event: TName;
  session_id: string;
  payload: TPayload;
}

export type SessionStartEvent = BaseDashboardEvent<
  "session_start",
  Record<string, never>
>;

export type SessionEndEvent = BaseDashboardEvent<
  "session_end",
  Record<string, never>
>;

export type UserTranscriptionEvent = BaseDashboardEvent<
  "user_transcription",
  { text: string; language?: string; timestamp?: string }
>;

export type BotResponseEvent = BaseDashboardEvent<
  "bot_response",
  {
    text: string;
    modality?: "text" | "audio";
    latency_ms?: number;
    timestamp?: string;
    citations?: BotCitation[];
  }
>;

export type IntentAnalysisEvent = BaseDashboardEvent<
  "intent_analysis",
  {
    intents: IntentItem[];
    reasoning?: string;
  }
>;

export type RagRetrievalEvent = BaseDashboardEvent<
  "rag_retrieval",
  {
    chunks: RagChunk[];
    latency_ms?: number;
  }
>;

export type ToolCallEvent = BaseDashboardEvent<
  "tool_call",
  {
    tool_name: string;
    parameters: Record<string, unknown>;
    status?: "pending" | "success" | "error";
    result?: Record<string, unknown>;
    started_at?: string;
    finished_at?: string;
  }
>;

export type TicketCreatedEvent = BaseDashboardEvent<
  "ticket_created",
  {
    ticket_id: number | string;
    department: string;
    summary: string;
  }
>;

export type BookingCreatedEvent = BaseDashboardEvent<
  "booking_created",
  {
    booking_id: number | string;
    guest_name: string;
    room_type: string;
    check_in: string;
    check_out: string;
    status: string;
    service: string;
    details: string;
  }
>;

export type TicketLoadedEvent = BaseDashboardEvent<
  "ticket_loaded",
  {
    ticket_id: string;
    room_number: string;
    category: string;
    description: string;
    loaded_at: string;
  }
>;

export type BookingLoadedEvent = BaseDashboardEvent<
  "booking_loaded",
  {
    booking_id: string;
    service: string;
    guest_name: string;
    date: string;
    time: string;
    guests_count: number;
    loaded_at: string;
  }
>;

export type HeartbeatEvent = BaseDashboardEvent<
  "heartbeat",
  { timestamp?: string }
>;

export type ErrorEvent = BaseDashboardEvent<
  "error",
  { message: string; details?: Record<string, unknown> }
>;

export type DashboardEvent =
  | SessionStartEvent
  | SessionEndEvent
  | UserTranscriptionEvent
  | BotResponseEvent
  | IntentAnalysisEvent
  | RagRetrievalEvent
  | ToolCallEvent
  | TicketCreatedEvent
  | BookingCreatedEvent
  | TicketLoadedEvent
  | BookingLoadedEvent
  | HeartbeatEvent
  | ErrorEvent;

export type DashboardConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error";

export interface RagChunk {
  id: string;
  title: string;
  snippet: string;
  source: string;
  score: number;
  highlight?: string;
}

export interface ActionItem {
  id: string;
  type: "ticket_created" | "booking_created" | string;
  title: string;
  description?: string;
  timestamp?: string;
  accent?: "bot" | "rag" | "tool" | "user";
  payload?: Record<string, unknown>;
}

export type BotCitation = {
  title?: string;
  url?: string;
  snippet?: string;
};

export type IntentItem =
  | string
  | { name: string; confidence?: number; description?: string };
