import { AnimatePresence, motion } from 'framer-motion';
import type { ActionItem } from '../types/events';

interface ActionPanelProps {
  items: ActionItem[];
}

const cardVariants = {
  hidden: { opacity: 0, y: -20 },
  visible: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 20 },
};

const accentClassMap: Record<string, string> = {
  ticket_created: 'border-accent-tool/25 bg-accent-tool/5 shadow-glow-tool',
  booking_created: 'border-accent-bot/25 bg-accent-bot/5 shadow-glow-bot',
  ticket_loaded: 'border-accent-tool/25 bg-accent-tool/5 shadow-glow-tool',
  booking_loaded: 'border-accent-bot/25 bg-accent-bot/5 shadow-glow-bot',
};

export const ActionPanel = ({ items }: ActionPanelProps) => {
  return (
    <motion.div
      className="space-y-4 rounded-2xl border border-white/5 bg-surface/80 p-6"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeInOut' }}
    >
      <div className="flex items-center gap-2 text-base uppercase tracking-[0.2em] text-accent-bot/90">
        <span className="h-2 w-2 rounded-full bg-accent-bot/80 shadow-[0_0_12px_rgba(52,211,153,0.7)]" />
        Действия ({items.length})
      </div>

      <AnimatePresence initial={false}>
        {items.length > 0 ? (
        <div className="space-y-3">
          {items.map((action) => (
            <motion.article
              key={action.id}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              transition={{ duration: 0.3 }}
              className={`rounded-xl border bg-black/20 p-4 backdrop-blur-sm ${
                accentClassMap[action.type] ?? 'border-accent-bot/20'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs uppercase tracking-[0.2em] text-white/90">{action.type.replace('_', ' ')}</span>
                {action.timestamp && <span className="text-[10px] text-white/40">{action.timestamp}</span>}
              </div>
              <h4 className="mt-2 text-sm font-medium text-text-primary">{action.title}</h4>
              {action.description && <p className="mt-1 text-xs text-white/60">{action.description}</p>}
            </motion.article>
          ))}
        </div>
      ) : (
        <motion.p
          className="text-sm text-white/40"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.7 }}
          transition={{ duration: 0.3 }}
        >
          Действия в системе появятся здесь.
        </motion.p>
      )}
    </AnimatePresence>
  </motion.div>
  );
};

export default ActionPanel;
