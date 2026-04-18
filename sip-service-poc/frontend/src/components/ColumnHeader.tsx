import { motion } from 'framer-motion';

interface ColumnHeaderProps {
    readonly label: string;
    readonly accentClass: string;
    readonly description?: React.ReactNode;
}

export const ColumnHeader = ({ label, accentClass, description }: ColumnHeaderProps) => (
    <motion.div
      className="mb-4 flex flex-col gap-2"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
    >
      <div className={`flex items-center gap-3 p-2 rounded-lg text-[16px] font-bold text-white/90 ${accentClass}`}>
        {/* <span className={`h-2 w-2 min-w-2 rounded-full ${accentClass}`} /> */}
        {label}
      </div>
      {description && <p className="text-base text-white/80">{description}</p>}
      <div className="h-px w-full bg-white/5" />
    </motion.div>
  );
