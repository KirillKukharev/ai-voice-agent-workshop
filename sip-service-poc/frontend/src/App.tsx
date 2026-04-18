import { useEffect, useMemo, useReducer, useState } from "react";
import { ColumnHeader } from "./components/ColumnHeader";
import { UserTranscription } from "./components/UserTranscription";
import { AnimatePresence, motion } from "framer-motion";
import { dashboardReducer } from "./shared/reducer";
import { INITIAL_STATE, STATUS_CONFIG } from "./shared/constants";
import BotResponse from "./components/BotResponse";
// import IntentDisplay from "./components/IntentDisplay";
import RagChunksDisplay from "./components/RagChunksDisplay";
import { MOCK_TIMELINE } from "./shared/mock";
import ToolCallDisplay from "./components/ToolCallDisplay";
import DashboardHeader from "./components/DashboardHeader";
import type { DashboardConnectionStatus, DashboardEvent } from "./types/events";
import ActionPanel from "./components/ActionPanel";

function App() {
  const [state, dispatch] = useReducer(dashboardReducer, INITIAL_STATE);
  const [connectionStatus, setConnectionStatus] =
    useState<DashboardConnectionStatus>("disconnected");

  // WebSocket connection
  useEffect(() => {
    const useMockTimeline = import.meta.env.VITE_USE_MOCK === "true";
    if (useMockTimeline) {
      const timers: number[] = [];
      MOCK_TIMELINE.forEach((event, index) => {
        const timer = window.setTimeout(() => {
          dispatch(event);
        }, index * 1200);
        timers.push(timer);
      });
      return () => {
        timers.forEach((timer) => window.clearTimeout(timer));
      };
    }

    let wsUrl: string;
    if (import.meta.env.VITE_WS_URL) {
      wsUrl = import.meta.env.VITE_WS_URL;
    } else {
      // Для localhost используем прямой порт 8000
      if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        wsUrl = `ws://localhost:8000`;
      } else {
        // Для продакшена используем тот же хост (IP или домен) и путь /ws
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsUrl = `${protocol}//${window.location.host}/ws`;
      }
    }
    const sessionId = state.sessionId || "waiting";
    const ws = new WebSocket(`${wsUrl}?session_id=${sessionId}`);

    setConnectionStatus("connecting");

    ws.onopen = () => {
      console.log("✅ WebSocket connected");
      setConnectionStatus("connected");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        dispatch(data as DashboardEvent);

      } catch (error) {
        console.error("❌ Failed to parse WebSocket message:", error);
      }
    };

    ws.onerror = (error) => {
      console.error("❌ WebSocket error:", error);
      setConnectionStatus("error");
    };

    ws.onclose = () => {
      console.log("🔌 WebSocket disconnected");
      setConnectionStatus("disconnected");
    };

    return () => {
      ws.close();
    };
  }, [state.sessionId]);

  const toolCallPayload = useMemo(
    () => state.toolCall?.payload ?? null,
    [state.toolCall]
  );

  const statusConfig = STATUS_CONFIG[connectionStatus];

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#242430] text-text-primary">
      <div className="pointer-events-none absolute inset-0 opacity-40">
        <div className="wow-grid absolute inset-0 animate-grid-pulse" />
        <div className="wow-blur absolute inset-0 animate-dust-move" />
      </div>

      <div className="relative z-10 flex min-h-screen w-full flex-col px-6 py-10 lg:px-12">
        <DashboardHeader
          statusLabel={statusConfig.label}
          statusClassName={statusConfig.className}
          sessionId={state.sessionId}
        />

        <main className="grid flex-1 grid-cols-1 gap-6 xl:grid-cols-[1.2fr_1fr_1fr]">
          <section className="space-y-6">
            <ColumnHeader
              label="Диалог с гостем"
              accentClass="bg-accent-user/80 shadow-[0_0_12px_rgba(56,189,248,0.7)]"
              description={
                <>
                  <span className="font-bold">
                    Фронтальная часть разговора:{" "}
                  </span>
                  <span className="italic">
                    живая транскрипция и ответ консьержа.
                  </span>
                </>
              }
            />

            {state.userTranscription.text && (
              <motion.div layout>
                <UserTranscription
                  text={state.userTranscription.text}
                  sessionId={state.sessionId}
                />
              </motion.div>
            )}

            {state.botResponse.text && (
              <motion.div layout>
                <BotResponse
                  text={state.botResponse.text ?? undefined}
                  latencyMs={state.botResponse.latencyMs}
                  citations={state.botResponse.citations}
                />
              </motion.div>
            )}
          </section>

          <section className="space-y-6">
            <ColumnHeader
              label="Мыслительный процесс AI"
              accentClass="bg-accent-tool/80 shadow-[0_0_12px_rgba(167,139,250,0.7)]"
              description={
                <>
                  <span className="font-bold">Интенсивная аналитика: </span>
                  <span className="italic">
                    намерения, найденные знания и вызовы инструментов.
                  </span>
                </>
              }
            />
            {/* {state.intents.length > 0 && (
              <IntentDisplay intents={state.intents} />
            )} */}
            {state.ragChunks.length > 0 && (
              <RagChunksDisplay chunks={state.ragChunks} />
            )}
            <AnimatePresence>
              {toolCallPayload && (
                <ToolCallDisplay
                  payload={toolCallPayload ?? undefined}
                  toolName={state.toolCall?.toolName}
                  status={state.toolCall?.status}
                />
              )}
            </AnimatePresence>
          </section>

          <section className="space-y-6">
            <ColumnHeader
              label="Действия в системе отеля"
              accentClass="bg-accent-bot/80 shadow-[0_0_12px_rgba(52,211,153,0.7)]"
              description={
                <>
                  <span className="font-bold">Пользовательский опыт: </span>
                  <span className="italic">
                    автоматически создаваемые задачи, бронирования и события.
                  </span>
                </>
              }
            />
            {state.actions.length > 0 && <ActionPanel items={state.actions} />}
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
