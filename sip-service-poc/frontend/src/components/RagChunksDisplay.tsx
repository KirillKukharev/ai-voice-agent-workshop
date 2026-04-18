import { AnimatePresence, motion } from 'framer-motion';
import type { RagChunk } from '../types/events';

interface RagChunksDisplayProps {
  chunks: RagChunk[];
}

const chunkVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.95 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { delay: index * 0.12, duration: 0.35, ease: 'easeOut' },
  }),
  exit: { opacity: 0, y: -10 },
};

export const RagChunksDisplay = ({ chunks }: RagChunksDisplayProps) => {
  const hasChunks = chunks?.length > 0;

  return (
    <motion.div
      className="space-y-4 rounded-2xl border border-accent-rag/20 bg-[#242430]/80 p-6 shadow-glow-rag"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeInOut' }}
    >
      <div className="flex items-center gap-2 text-base uppercase tracking-[0.2em] text-accent-rag/90">
        <span className="h-2 w-2 rounded-full bg-accent-rag/80 shadow-[0_0_12px_rgba(251,191,36,0.7)]" />
        RAG - ПОИСК
      </div>

      <AnimatePresence>
        {hasChunks ? (
          <div className="space-y-4">
            {chunks.map((chunk, index) => (
              <motion.article
                key={`${chunk.source}-${index}`}
                className="rounded-xl border border-accent-rag/30 bg-black/20 p-4 backdrop-blur-sm"
                custom={index}
                variants={chunkVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <div className="mb-2">
                  <span className="text-xs font-mono uppercase tracking-[0.2em] text-white/60">Источник</span>
                </div>
                <h4 className="text-sm font-medium text-white">{chunk.source}</h4>
                {chunk.snippet && (
                  <p className="mt-2 text-xs leading-6 text-white/70">
                    {chunk.snippet}
                  </p>
                )}
                {chunk.highlight && (
                  <p className="mt-2 text-xs leading-6 text-white/70">
                    <span className="text-accent-rag/70">{chunk.highlight}</span>
                  </p>
                )}
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
            Ищем релевантные знания…
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default RagChunksDisplay;
