import { X as CloseIcon, Search } from 'lucide-react';
import type { Thread } from '@/types';

export function SearchModal({
  query,
  onQueryChange,
  results,
  onSelect,
  onClose,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  results: Thread[];
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4">
      <div className="mt-20 w-full max-w-xl rounded-2xl border border-neutral-800 bg-[#121212] shadow-xl">
        <div className="flex items-center gap-2 border-b border-neutral-800 px-4 py-3">
          <Search className="h-4 w-4 text-neutral-400" />
          <input
            autoFocus
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search claims by title…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-neutral-500"
          />
          <button
            onClick={onClose}
            className="rounded-md p-1 text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-2 py-2">
          {results.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-neutral-500">No matches</div>
          ) : (
            results.map((t) => (
              <button
                key={t.id}
                onClick={() => onSelect(t.id)}
                className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-neutral-900"
              >
                <div className="truncate">
                  <div className="text-sm text-neutral-200">{t.title}</div>
                  <div className="text-xs text-neutral-500">{t.id}</div>
                </div>
                {t.active ? (
                  <span className="rounded-md border border-neutral-700 px-2 py-0.5 text-xs text-neutral-400">
                    Active
                  </span>
                ) : null}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
