import { motion } from 'framer-motion';
import TypewriterText from './TypewriterText';

interface UserTranscriptionProps {
  text?: string | null;
  sessionId?: string | null;
}

const containerVariants = {
  hidden: { opacity: 0, x: -12 },
  visible: { opacity: 1, x: 0 },
};

export const UserTranscription = ({ text, sessionId }: UserTranscriptionProps) => {
  return (
    <motion.div
      key={`${sessionId ?? 'unknown'}-user-${text}`}
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      transition={{ type: 'spring', stiffness: 140, damping: 18 }}
      className="relative overflow-hidden rounded-2xl border border-accent-user/20 bg-[#242430]/80 p-6 shadow-glow-user"
    >
      <div className="pointer-events-none absolute inset-0 -z-10 bg-accent-user/10 opacity-60 blur-3xl" />
      <div className="flex items-center gap-2 text-base uppercase tracking-[0.2em] text-accent-user/90">
        <span className="h-2 w-2 rounded-full bg-accent-user/80 shadow-[0_0_8px_rgba(56,189,248,0.8)]" />
        Гость
      </div>
      <p className="mt-4 text-[15px] leading-relaxed text-text-primary">
        <TypewriterText text={text} />
      </p>
    </motion.div>
  );
};

export default UserTranscription;
