import type { Message } from '@/types';
import { InvoiceSummaryCard } from '@/components/InvoiceSummaryCard';

export function ChatMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user';
  const isAssistant = msg.role === 'assistant';
  const bubbleClass = isUser
    ? 'bg-[rgba(200,100,60,0.12)] border-[rgba(200,100,60,0.45)]'
    : isAssistant
    ? 'bg-[#121212] border-neutral-800'
    : 'bg-transparent border-transparent';

  return (
    <div className="flex gap-3">
      <div className={`w-full rounded-2xl border px-4 py-3 leading-relaxed ${bubbleClass}`}>
        <RichText content={msg.content} />
        {isAssistant && msg.tool_result ? (
          <div className="mt-3">
            <InvoiceSummaryCard data={msg.tool_result} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RichText({ content }: { content: string }) {
  const lines = (content ?? '').split('\n');
  return (
    <div className="prose prose-invert max-w-none prose-p:my-3 prose-li:my-1 prose-strong:text-neutral-100 prose-headings:tracking-tight prose-h2:mb-2 prose-h2:mt-0 prose-h2:text-xl prose-h3:text-lg">
      {lines.map((l, i) => {
        if (l.startsWith('## ')) return <h2 key={i}>{l.slice(3)}</h2>;
        if (l.startsWith('### ')) return <h3 key={i}>{l.slice(4)}</h3>;
        if (l.startsWith('- '))
          return (
            <ul key={i} className="my-2 list-disc pl-6">
              <li>{l.slice(2)}</li>
            </ul>
          );
        return <p key={i}>{l}</p>;
      })}
    </div>
  );
}
