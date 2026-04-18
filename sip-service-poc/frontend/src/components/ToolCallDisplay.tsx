import { motion } from 'framer-motion';
import { useMemo } from 'react';

interface ToolCallDisplayProps {
  payload?: Record<string, unknown> | null;
  toolName?: string;
  status?: 'pending' | 'success' | 'error';
}

const highlightJson = (data: Record<string, unknown> | null | undefined) => {
  if (!data) {
    return null;
  }

  const jsonString = JSON.stringify(data, null, 2);
  const lines = jsonString.split('\n');

  return lines.map((line, index) => {
    const keyMatch = line.match(/^(\s*)"([^"]+)":\s?(.*)$/);

    if (!keyMatch) {
      return (
        <div key={index} className="font-mono text-xs whitespace-pre text-white/80">
          {line}
        </div>
      );
    }

    const [, indent, key, rest] = keyMatch;
    const isString = rest.trim().startsWith('"');

    return (
      <div key={index} className="font-mono text-xs text-white/80">
        <span className="whitespace-pre">{indent}</span>
        <span className="text-accent-user">"{key}"</span>
        <span>: </span>
        <span className={isString ? 'text-accent-bot whitespace-pre' : 'text-white/80 whitespace-pre'}>{rest}</span>
      </div>
    );
  });
};

export const ToolCallDisplay = ({ payload }: ToolCallDisplayProps) => {
  const highlightedJson = useMemo(() => highlightJson(payload), [payload]);

  return (
    <motion.div
      className="rounded-2xl border border-accent-tool/20 bg-[#242430]/80 p-6 shadow-glow-tool"
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <div className="flex items-center gap-2 text-base uppercase tracking-[0.2em] text-accent-tool/90">
        <span className="h-2 w-2 rounded-full bg-accent-tool/80 shadow-[0_0_12px_rgba(167,139,250,0.7)]" />
        Тип действия
        {/* {status && (
          <span className="rounded-full border border-accent-tool/40 px-2 py-0.5 text-[10px] text-accent-tool/80">
            {status === 'pending' ? 'в процессе' : status === 'success' ? 'готово' : 'ошибка'}
          </span>
        )} */}
      </div>

      <div className="mt-4 overflow-auto rounded-xl bg-black/40 p-4">
        {highlightedJson ?? (
          <p className="text-sm text-white/40">Ожидаем данные от инструмента…</p>
        )}
      </div>
    </motion.div>
  );
};

export default ToolCallDisplay;
