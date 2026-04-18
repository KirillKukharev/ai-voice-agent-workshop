import { motion } from "framer-motion";
import type { BotCitation } from "../types/events";
import TypewriterText from "./TypewriterText";

interface BotResponseProps {
  readonly text?: string | null;
  readonly latencyMs?: number;
  readonly icon?: React.ReactNode;
  readonly citations?: BotCitation[] | null;
}

const containerVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0 },
};

export const BotResponse = ({
  text,
  latencyMs,
  icon,
  citations,
}: BotResponseProps) => {
  if (!text) {
    return (
      <div className="rounded-2xl border border-white/5 bg-surface/60 p-6 text-sm text-white/40">
        Готовим ответ…
      </div>
    );
  }

  return (
    <motion.div
      key={`bot-${text}`}
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="relative overflow-hidden rounded-2xl border border-accent-bot/20 bg-[#242430]/80 p-6 shadow-glow-bot"
    >
      <div className="pointer-events-none absolute inset-0 -z-10 bg-accent-bot/10 opacity-60 blur-3xl" />
      <div className="flex items-center gap-2 text-base uppercase tracking-[0.2em] text-accent-bot/90">
        {icon ? (
          icon
        ) : (
          <span className="h-2 w-2 rounded-full bg-accent-bot/80 shadow-[0_0_12px_rgba(52,211,153,0.7)]" />
        )}
        <span className="flex justify-between items-center">
          Консьерж
          {latencyMs !== undefined && (
            <span className="text-white rounded-full bg-accent-bot/10 px-2 py-0.5 text-[10px]">
              {latencyMs} мс
            </span>
          )}
        </span>
      </div>
      <motion.p
        className="mt-4 text-[15px] leading-relaxed text-text-primary"
        layout
      >
        <TypewriterText text={text} />
      </motion.p>
      {citations && citations.length > 0 && (
        <motion.div
          className="mt-5 rounded-xl border border-white/5 bg-black/30 p-4"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <p className="text-[11px] uppercase tracking-[0.3em] text-white/50">
            Источники
          </p>
          <ul className="mt-3 space-y-2 text-xs text-white/70">
            {citations.map((citation, index) => (
              <li
                key={citation.url ?? citation.title ?? `citation-${index}`}
                className="space-y-1"
              >
                <p className="font-medium text-white/80">
                  {citation.title ?? `Источник ${index + 1}`}
                </p>
                {citation.snippet && (
                  <p className="text-white/60">{citation.snippet}</p>
                )}
                {citation.url && (
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-accent-user hover:text-accent-user/80"
                  >
                    {citation.url.replace(/^https?:\/\//, "")}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </motion.div>
      )}
    </motion.div>
  );
};

export default BotResponse;
