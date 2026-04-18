import { AnimatePresence, motion } from 'framer-motion';
import type { IntentItem } from '../types/events';

interface IntentDisplayProps {
  intents: IntentItem[];
}

const itemVariants = {
  hidden: { opacity: 0, x: 12 },
  visible: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
};

const normalizeIntent = (intent: IntentItem) => {
  if (typeof intent === 'string') {
    return { label: intent, confidence: undefined as number | undefined };
  }

  return {
    label: intent.name,
    confidence: intent.confidence,
  };
};

export const IntentDisplay = ({ intents }: IntentDisplayProps) => {
  const normalizedIntents = intents?.map(normalizeIntent) ?? [];
  const hasIntents = normalizedIntents.length > 0;

  return (
    <motion.div
      className="space-y-4 rounded-2xl border border-white/5 bg-[#242430]/80 p-6"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeInOut' }}
    >
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60">
        <span className="h-2 w-2 rounded-full bg-accent-user/60" />
        Намерения
      </div>

      <AnimatePresence initial={false}>
        {hasIntents ? (
          <div className="flex flex-wrap gap-2">
            {normalizedIntents.map((intent, index) => (
              <motion.span
                key={`${intent.label}-${index}`}
                variants={itemVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
                transition={{ duration: 0.25 }}
                className="flex items-center gap-1 rounded-full border border-accent-user/30 bg-accent-user/10 px-3 py-1 text-xs text-accent-user"
              >
                {intent.label}
                {intent.confidence !== undefined && (
                  <span className="text-[10px] text-white/60">
                    {(intent.confidence * 100).toFixed(0)}
                    <span className="ml-0.5">%</span>
                  </span>
                )}
              </motion.span>
            ))}
          </div>
        ) : (
          <motion.p
            className="text-sm text-white/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.7 }}
            transition={{ duration: 0.3 }}
          >
            Анализируем намерения гостя…
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default IntentDisplay;
