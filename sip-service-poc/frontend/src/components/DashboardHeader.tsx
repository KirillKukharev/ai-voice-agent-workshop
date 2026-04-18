interface DashboardHeaderProps {
  readonly statusLabel: string;
  readonly statusClassName: string;
  readonly sessionId?: string | null;
}

export const DashboardHeader = ({
  statusLabel,
  statusClassName,
  sessionId,
}: DashboardHeaderProps) => (
  <>
    <header className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <p className="text-base font-bold uppercase tracking-[0.4em] text-white/80">Raft/Cloud.ru</p>
        <h1 className="mt-3 text-3xl font-[Unbounded] font-bold text-[#26D07C] sm:text-4xl">ИИ-консьерж для отелей</h1>
        <p className="mt-2 text-base text-white/80">
          Визуализация мыслительного процесса, вызовов инструментов и действий в системе отеля.
        </p>
      </div>
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:gap-3">
        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-black/40 px-4 py-2 text-xs">
          <span className={`h-2.5 w-2.5 rounded-full ${statusClassName}`} />
          {statusLabel}
        </div>
        {sessionId && (
          <div className="rounded-full border border-white/10 bg-black/40 px-4 py-2 text-xs text-white/60">
            Сессия: <span className="font-mono text-white/80">{sessionId}</span>
          </div>
        )}
      </div>
    </header>
  </>
);

export default DashboardHeader;
