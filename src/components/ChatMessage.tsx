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
  const lines = (content ?? '').split(/\r?\n/);

  const elements: React.ReactNode[] = [];
  let listBuffer: string[] = [];

  const flushList = () => {
    if (!listBuffer.length) return;
    elements.push(
      <ul key={`ul-${elements.length}`} className="my-2 ml-6 list-disc text-neutral-200">
        {listBuffer.map((item, i) => (
          <li key={i} className="my-0.5">
            {item}
          </li>
        ))}
      </ul>
    );
    listBuffer = [];
  };

  lines.forEach((raw, i) => {
    const line = raw ?? '';

    // Headings
    if (line.startsWith('## ')) {
      flushList();
      elements.push(
        <h2
          key={`h2-${i}`}
          className="mb-2 mt-0 text-xl font-semibold tracking-tight text-neutral-100"
        >
          {line.slice(3)}
        </h2>
      );
      return;
    }
    if (line.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={`h3-${i}`} className="mb-1 mt-1 text-lg font-semibold tracking-tight">
          {line.slice(4)}
        </h3>
      );
      return;
    }

    // Bullets: allow indentation + different dash chars
    const ltrim = line.replace(/^\s+/, '');
    if (/^[-•–]\s+/.test(ltrim)) {
      listBuffer.push(ltrim.replace(/^[-•–]\s+/, ''));
      return;
    }

    // Blank line = paragraph break
    if (!line.trim()) {
      flushList();
      // insert a soft gap between paragraphs
      elements.push(<div key={`br-${i}`} className="h-2" />);
      return;
    }

    // Normal paragraph; preserve inline linebreaks if any (rare)
    flushList();
    elements.push(
      <p key={`p-${i}`} className="my-1 whitespace-pre-wrap leading-relaxed">
        {line}
      </p>
    );
  });

  flushList();

  return <div className="prose prose-invert max-w-none">{elements}</div>;
}
