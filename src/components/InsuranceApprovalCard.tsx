import React from 'react';
import { InsuranceSummary } from '@/components/InsuranceSummary';

type Props = {
  reply: string;
  tool?: any; // expects Insurance agent tool_result (with .result_json)
  onApprove?: () => void;
  onDeny?: () => void;
  hideActions?: boolean;
  header?: string;
};

export function InsuranceApprovalCard({
  reply,
  tool,
  onApprove,
  onDeny,
  hideActions = false,
  header,
}: Props) {
  // tool is typically the insurance tool_result
  const resultJson = tool?.result_json ?? {};
  const policyId: string | null | undefined = resultJson?.policy_id;
  const eligible: boolean = Boolean(resultJson?.eligible);
  const policyValid = Boolean(eligible && policyId);

  const payer: 'patient' | 'corporation' | undefined = resultJson?.payer;
  const corp = resultJson?.corporate_meta ?? null;
  const isWorkAccident: boolean | undefined = corp?.suggested?.is_work_accident;
  const decisionId: string | undefined = corp?.decision_id;

  // Build header badges if not provided by parent
  const computedHeader = header ?? 'Insurance response received';

  return (
    <div className="rounded-2xl border border-[#2b2b2b] bg-[#121212]">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#222] px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
          <span className="truncate text-sm font-medium text-neutral-200">{computedHeader}</span>
        </div>

        {!hideActions && (
          <div className="text-xs text-neutral-400">
            {policyValid ? 'Awaiting approval' : 'Policy invalid – approval disabled'}
          </div>
        )}
      </div>

      {/* Meta badges row */}
      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        {typeof payer === 'string' && (
          <Badge>
            Payer (rest): <strong className="ml-1 capitalize">{payer}</strong>
          </Badge>
        )}
        {typeof isWorkAccident === 'boolean' && (
          <Badge>
            Work accident: <strong className="ml-1">{isWorkAccident ? 'YES' : 'NO'}</strong>
          </Badge>
        )}
        {decisionId && <Badge mono>Decision ID: {decisionId}</Badge>}
        {policyId && <Badge mono>Policy: {policyId}</Badge>}
      </div>

      {/* Body */}
      <div className="px-4 pb-3 pt-2 text-sm text-neutral-300">
        {reply ? (
          <div className="whitespace-pre-wrap leading-relaxed text-neutral-400">{reply}</div>
        ) : (
          <div className="text-neutral-500">Review the insurance summary below.</div>
        )}

        {tool ? (
          <div className="mt-3">
            <InsuranceSummary tool={tool} />
          </div>
        ) : null}
      </div>

      {/* Actions */}
      {!hideActions && (
        <div className="flex items-center justify-end gap-2 border-t border-[#222] px-4 py-3">
          <button
            onClick={policyValid ? onDeny : undefined}
            disabled={!policyValid}
            className="rounded-xl border border-neutral-800 bg-[#171717] px-3 py-1.5 text-sm text-neutral-200 hover:bg-[#1c1c1c] disabled:cursor-not-allowed disabled:opacity-60"
          >
            Deny
          </button>
          <button
            onClick={policyValid ? onApprove : undefined}
            disabled={!policyValid}
            className="rounded-xl bg-[#2a5d2a] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#2e6a2e] disabled:cursor-not-allowed disabled:opacity-60"
            style={{ boxShadow: '0 0 0 1px #2e6a2e inset' }}
          >
            Approve
          </button>
        </div>
      )}
    </div>
  );
}

/* -------------------- tiny internal badge component -------------------- */
function Badge({ children, mono = false }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border border-neutral-800 bg-[#171717] px-2 py-0.5 text-xs text-neutral-300 ${
        mono ? 'font-mono' : ''
      }`}
    >
      {children}
    </span>
  );
}
