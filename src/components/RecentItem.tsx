import { TrashIcon } from 'lucide-react';
export function RecentItem({
  title,
  active = false,
  status = null,
  handleChangeConvo = () => {},
  handleDeleteConvo = () => {},
}: {
  title: string;
  active?: boolean;
  status?: 'pending' | 'approved' | 'denied' | null;
  handleChangeConvo?: any;
  handleDeleteConvo?: any;
}) {
  return (
    <button
      className={`group flex w-full cursor-pointer items-center justify-between rounded-xl px-3 py-2 text-sm ${
        active ? 'bg-neutral-900/70' : 'hover:bg-neutral-900/50'
      }`}
      onClick={handleChangeConvo}
    >
      <span className="truncate text-neutral-300">{title}</span>
      <span
        className="opacity-0 transition-opacity group-hover:opacity-100 hover:opacity-50"
        onClick={(e) => {
          e.stopPropagation();
          handleDeleteConvo();
        }}
      >
        <TrashIcon className="h-4 w-4 text-neutral-500" />
      </span>
      {status === 'pending' && (
        <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300 ring-1 ring-inset ring-amber-500/30">
          Pending
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
        </span>
      )}
      {status === 'approved' && (
        <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300 ring-1 ring-inset ring-emerald-500/30">
          Approved
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        </span>
      )}
      {status === 'denied' && (
        <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-300 ring-1 ring-inset ring-red-500/30">
          Denied
          <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
        </span>
      )}
    </button>
  );
}
