import type { ActionItem, DashboardEvent, RagChunk } from "../types/events";
import type { DashboardState } from "../types/types";
import { DASHBOARD_EVENT_LIMIT, INITIAL_STATE } from "./constants";
import { generateId } from "./utils";


function isValidPhoneSession(sessionId: string | null): boolean {
  if (!sessionId) return false;
  if (sessionId === "waiting" || sessionId.startsWith("test-")) {
    return false;
  }
  const phoneRegex = /\d{7,}/;
  return phoneRegex.test(sessionId);
}

const applyDashboardEvent = (
  state: DashboardState,
  event: DashboardEvent
): DashboardState => {
  switch (event.event) {
    case "session_start":
      const newSessionId = event.session_id ?? state.sessionId;
      const shouldClearActions =
        (state.sessionId && state.sessionId !== newSessionId) ||
        !isValidPhoneSession(newSessionId);

      return {
        ...state,
        sessionId: newSessionId,
        // Clear actions from previous session if session changed or if new session is test
        actions: shouldClearActions ? [] : state.actions,
        lastEvent: event.event,
      };

    case "session_end":
      return {
        ...INITIAL_STATE,
        lastEvent: event.event,
      };

    case "user_transcription":
      return {
        ...state,
        sessionId: event.session_id ?? state.sessionId,
        userTranscription: {
          text: event.payload.text,
          timestamp: event.payload.timestamp,
        },
        lastEvent: event.event,
      };

    case "bot_response":
      const hotelbotSource = "hotelbot.xlsx";
      const hasHotelbotSource = state.ragChunks.some(
        chunk => chunk.source === hotelbotSource
      );

      let updatedRagChunks = [...state.ragChunks];
      if (event.payload.text && !hasHotelbotSource) {
        const hotelbotChunk: RagChunk = {
          id: `hotelbot-${Date.now()}`,
          title: "База знаний отеля",
          snippet: "Источник данных о сервисах и услугах отеля",
          source: hotelbotSource,
          score: 1.0,
        };
        updatedRagChunks = [...state.ragChunks, hotelbotChunk];
      }

      return {
        ...state,
        sessionId: event.session_id ?? state.sessionId,
        botResponse: {
          text: event.payload.text,
          latencyMs: event.payload.latency_ms,
          citations: event.payload.citations,
        },
        ragChunks: updatedRagChunks,
        lastEvent: event.event,
      };

    case "intent_analysis":
      return {
        ...state,
        sessionId: event.session_id ?? state.sessionId,
        intents: event.payload.intents ?? [],
        lastEvent: event.event,
      };

    case "rag_retrieval":
      return {
        ...state,
        sessionId: event.session_id ?? state.sessionId,
        ragChunks: event.payload.chunks ?? [],
        lastEvent: event.event,
      };

    case "tool_call": {
      const toolPayload = event.payload;
      const formattedPayload = {
        tool: toolPayload.tool_name,
        status: toolPayload.status ?? "pending",
        parameters: toolPayload.parameters,
        result: toolPayload.result,
        started_at: toolPayload.started_at,
        finished_at: toolPayload.finished_at,
      };

      return {
        ...state,
        sessionId: event.session_id ?? state.sessionId,
        toolCall: {
          toolName: toolPayload.tool_name,
          status: toolPayload.status ?? "pending",
          payload: formattedPayload,
        },
        lastEvent: event.event,
      };
    }

    case "ticket_created": {
      const currentSessionId = state.sessionId || event.session_id;
      if (event.session_id && state.sessionId && event.session_id !== state.sessionId) {
        return state;
      }

      if (!isValidPhoneSession(currentSessionId)) {
        return state;
      }

      const ticketId = String(event.payload.ticket_id ?? generateId());

      const existingIndex = state.actions.findIndex(action => action.id === ticketId);
      if (existingIndex !== -1) {
        return state;
      }

      const newAction: ActionItem = {
        id: ticketId,
        type: event.event,
        title: `Заявка №${ticketId}`,
        description: `${event.payload.department}: ${event.payload.summary}`,
        payload: event.payload,
      };

      return {
        ...state,
        sessionId: currentSessionId,
        actions: [newAction, ...state.actions].slice(0, DASHBOARD_EVENT_LIMIT),
        lastEvent: event.event,
      };
    }

    case "booking_created": {
      const currentSessionId = state.sessionId || event.session_id;
      if (event.session_id && state.sessionId && event.session_id !== state.sessionId) {
        return state;
      }

      if (!isValidPhoneSession(currentSessionId)) {
        return state;
      }

      const bookingId = String(event.payload.booking_id ?? generateId());

      const existingIndex = state.actions.findIndex(action => action.id === bookingId);
      if (existingIndex !== -1) {
        return state;
      }

      const newAction: ActionItem = {
        id: bookingId,
        type: event.event,
        title: `Бронь №${bookingId} — ${event.payload.service}`,
        description: event.payload.details,
        payload: event.payload,
      };

      return {
        ...state,
        sessionId: currentSessionId,
        actions: [newAction, ...state.actions].slice(0, DASHBOARD_EVENT_LIMIT),
        lastEvent: event.event,
      };
    }

    case "ticket_loaded": {
      const currentSessionId = state.sessionId || event.session_id;
      if (event.session_id && state.sessionId && event.session_id !== state.sessionId) {
        return state;
      }

      if (!isValidPhoneSession(currentSessionId)) {
        return state;
      }

      const ticketId = String(event.payload.ticket_id ?? generateId());

      const existingIndex = state.actions.findIndex(action => action.id === ticketId);
      if (existingIndex !== -1) {
        return state;
      }

      const description = event.payload.description || event.payload.category || "Без описания";
      const roomNumber = event.payload.room_number || "N/A";
      const category = event.payload.category || "N/A";

      const title = `Заявка из Airtable — ${roomNumber}`;
      let fullDescription = "";
      if (category && category !== "N/A") {
        fullDescription = `${category}`;
      }
      if (description && description !== "Без описания") {
        fullDescription = fullDescription ? `${fullDescription}: ${description}` : description;
      }
      if (!fullDescription) {
        fullDescription = "Заявка без описания";
      }

      const newAction: ActionItem = {
        id: ticketId,
        type: "ticket_created",
        title: title,
        description: fullDescription,
        timestamp: event.payload.loaded_at,
        payload: event.payload,
      };

      const newState = {
        ...state,
        sessionId: currentSessionId,
        actions: [newAction, ...state.actions].slice(0, DASHBOARD_EVENT_LIMIT),
        lastEvent: event.event,
      };

      return newState;
    }

    case "booking_loaded": {
      const currentSessionId = state.sessionId || event.session_id;
      if (event.session_id && state.sessionId && event.session_id !== state.sessionId) {
        return state;
      }

      if (!isValidPhoneSession(currentSessionId)) {
        return state;
      }

      const bookingId = String(event.payload.booking_id ?? generateId());

      const existingIndex = state.actions.findIndex(action => action.id === bookingId);
      if (existingIndex !== -1) {
        return state;
      }

      const details = `${event.payload.guest_name} — ${event.payload.service} на ${event.payload.date} в ${event.payload.time} (${event.payload.guests_count} гостей)`;


      const newAction: ActionItem = {
        id: bookingId,
        type: "booking_created",
        title: `Бронь из Airtable — ${event.payload.guest_name}`,
        description: details,
        timestamp: event.payload.loaded_at,
        payload: event.payload,
      };

      const newState = {
        ...state,
        sessionId: currentSessionId,
        actions: [newAction, ...state.actions].slice(0, DASHBOARD_EVENT_LIMIT),
        lastEvent: event.event,
      };

      return newState;
    }

    case "error":
      return {
        ...state,
        lastEvent: event.event,
        lastError: event.payload.message,
      };

    default:
      return {
        ...state,
        lastEvent: event.event,
      };
  }
};

export const dashboardReducer = (state: DashboardState, event: DashboardEvent) =>
  applyDashboardEvent(state, event);
