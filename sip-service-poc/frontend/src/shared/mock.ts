import type { DashboardEvent } from "../types/events";

export const MOCK_TIMELINE: DashboardEvent[] = [
  {
    event: "session_start",
    session_id: "demo-session",
    payload: { },
  },
  {
    event: "user_transcription",
    session_id: "demo-session",
    payload: {
      text: "Привет! У меня завтра годовщина свадьбы, есть ли свободный люкс?",
      timestamp: new Date().toISOString(),
    },
  },
  {
    event: "intent_analysis",
    session_id: "demo-session",
    payload: {
      intents: [
        { name: "Запрос о бронировании", confidence: 0.93 },
        { name: "Особый случай", confidence: 0.71 },
      ],
    },
  },
  {
    event: "rag_retrieval",
    session_id: "demo-session",
    payload: {
      chunks: [
        {
          id: "chunk-1",
          title: "Категория номеров — Люкс",
          snippet:
            "Люкс с панорамным видом, доступен с пакетом романтический уикенд. Включает украшение номера и поздний выезд.",
          source: "knowledge_base/rooms/luxe.md",
          score: 0.86,
        },
        {
          id: "chunk-2",
          title: "Специальные предложения",
          snippet:
            "Предложение «Anniversary Bliss»: бутылка шампанского, ужин на двоих, поздний чек-аут.",
          source: "offers/anniversary.json",
          score: 0.78,
        },
      ],
    },
  },
  {
    event: "tool_call",
    session_id: "demo-session",
    payload: {
      tool_name: "checkAvailability",
      status: "success",
      parameters: { roomType: "Luxe", date: "2025-11-12" },
      result: { available: true, pricePerNight: 290, currency: "EUR" },
    },
  },
  {
    event: "bot_response",
    session_id: "demo-session",
    payload: {
      text: "Поздравляю! У нас свободен люкс с романтическим пакетом. Забронировать на двоих?",
      latency_ms: 640,
    },
  },
  {
    event: "booking_created",
    session_id: "demo-session",
    payload: {
      booking_id: "BK-4915",
      guest_name: "Анна Иванова",
      room_type: "Люкс",
      check_in: "2025-11-12",
      check_out: "2025-11-13",
      status: "confirmed",
      service: "room_booking",
      details:
        "Гость: Анна Иванова; номер: Люкс; даты: 2025-11-12 — 2025-11-13; статус: confirmed",
    },
  },
];
