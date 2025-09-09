import React from 'react';
import { InsuranceSummary } from '@/components/InsuranceSummary';

type Props = {
  reply: string;
  tool?: any;
  onApprove: () => void;
  onDeny: () => void;
  hideActions?: boolean;
  header?: string;
};

export function InsuranceApprovalCard({ reply, tool, onApprove, onDeny, hideActions = false, header }: Props) {
  return (
    <div className="rounded-2xl border border-[#2b2b2b] bg-[#121212]">
      <div className="flex items-center justify-between gap-3 border-b border-[#222] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
          <span className="text-sm font-medium text-neutral-200">{header ?? 'Insurance response received'}</span>
        </div>
        {!hideActions && <div className="text-xs text-neutral-400">Awaiting approval</div>}
      </div>

      <div className="px-4 py-3 text-sm text-neutral-300">
        <div className="whitespace-pre-wrap leading-relaxed text-neutral-400">
          Review the insurance summary below.
        </div>

        {tool ? (
          <div className="mt-3">
            <InsuranceSummary tool={tool} />
          </div>
        ) : null}
      </div>

      {!hideActions && (
        <div className="flex items-center justify-end gap-2 border-t border-[#222] px-4 py-3">
          <button
            onClick={onDeny}
            className="rounded-xl border border-neutral-800 bg-[#171717] px-3 py-1.5 text-sm text-neutral-200 hover:bg-[#1c1c1c]"
          >
            Deny
          </button>
          <button
            onClick={onApprove}
            className="rounded-xl bg-[#2a5d2a] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#2e6a2e]"
            style={{ boxShadow: '0 0 0 1px #2e6a2e inset' }}
          >
            Approve
          </button>
        </div>
      )}
    </div>
  );
}
