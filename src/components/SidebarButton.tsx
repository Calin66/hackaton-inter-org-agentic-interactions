import { MessageSquare, Plus, Search } from 'lucide-react';

const ACCENT = '#c8643c';
export function SidebarButton({
  label,
  accent = false,
  onClick = () => {},
}: {
  label: string;
  accent?: boolean;
  onClick?: any;
}) {
  let Icon = MessageSquare;
  if (label.toLowerCase().startsWith('new')) Icon = Plus;
  else if (label.toLowerCase().startsWith('search')) Icon = Search;

  return (
    <button
      className={`mb-1 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-neutral-900 cursor-pointer ${
        accent ? 'border border-neutral-800 bg-[#151515] text-neutral-100' : 'text-neutral-300'
      }`}
      onClick={onClick}
    >
      <span
        className={`inline-flex h-6 w-6 items-center justify-center rounded-md ${
          accent ? '' : 'bg-neutral-700/60'
        }`}
        style={accent ? { background: ACCENT } : undefined}
      >
        <Icon className="h-3 w-3" />
      </span>
      {label}
    </button>
  );
}
