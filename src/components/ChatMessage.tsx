import type { Message } from '@/types';
import { InvoiceSummaryCard } from '@/components/InvoiceSummaryCard';
import { InsuranceApprovalCard } from '@/components/InsuranceApprovalCard';
import { InsuranceSummary } from '@/components/InsuranceSummary';

export function ChatMessage({
  msg,
  onApproveInsurance,
  onDenyInsurance,
}: {
  msg: Message;
  onApproveInsurance?: () => void;
  onDenyInsurance?: () => void;
}) {
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
        {/* Status badge */}
        {isAssistant && (msg as any)?.status && (
          <div className="mb-1 flex justify-end">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${
                (msg as any).status === 'approved'
                  ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
                  : (msg as any).status === 'denied'
                  ? 'bg-red-500/15 text-red-300 ring-red-500/30'
                  : 'bg-amber-500/15 text-amber-300 ring-amber-500/30'
              }`}
            >
              {(msg as any).status}
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  (msg as any).status === 'approved'
                    ? 'bg-emerald-400'
                    : (msg as any).status === 'denied'
                    ? 'bg-red-400'
                    : 'bg-amber-400'
                }`}
              />
            </span>
          </div>
        )}
        <RichText content={msg.content} />
        {isAssistant && (msg as any)?.tool_result ? (
          <div className="mt-3">
            {isInsuranceToolResult((msg as any).tool_result) ? (
              <InsuranceSummary tool={(msg as any).tool_result} />
            ) : (
              <InvoiceSummaryCard data={(msg as any).tool_result} />
            )}
          </div>
        ) : null}

        {/* Insurance approval flow */}
        {isAssistant && (msg as any)?.meta?.insurance_pending ? (
          <div className="mt-3">
            <InsuranceApprovalCard
              reply={(msg as any)?.meta?.insurance_pending?.text ?? ''}
              tool={(msg as any)?.meta?.insurance_pending?.tool_result}
              onApprove={() => onApproveInsurance?.()}
              onDeny={() => onDenyInsurance?.()}
              hideActions={!((msg as any)?.meta?.insurance_pending?.policy_valid === true)}
              header={
                (msg as any)?.meta?.insurance_pending?.policy_valid === true
                  ? undefined
                  : 'No valid policy found'
              }
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
function isInsuranceToolResult(obj: any): boolean {
  if (!obj || typeof obj !== 'object') return false;
  return 'result_json' in obj || 'message' in obj;
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
