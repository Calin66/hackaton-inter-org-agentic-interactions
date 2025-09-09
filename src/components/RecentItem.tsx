import { TrashIcon } from 'lucide-react';
export function RecentItem({
  title,
  active = false,
  handleChangeConvo = () => {},
  handleDeleteConvo = () => {},
}: {
  title: string;
  active?: boolean;
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
    </button>
  );
}
