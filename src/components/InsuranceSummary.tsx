import React from 'react';

type Item = {
  claim_name: string;
  matched_name?: string;
  category?: string;
  billed?: number;
  ref_price?: number;
  allowed_amount?: number;
  payable_amount?: number;
  notes?: string;
};

type CorporateClause = { id: string; title?: string; verdict?: string };
type CorporateEvidence = {
  during_work_hours?: boolean;
  happened_at?: string;
  location?: string;
  sick_leave_days?: number;
  narrative?: string;
};
type CorporateMeta = {
  decision_id?: string;
  is_work_accident?: boolean;
  reason?: string;
  confidence?: number;
  policy_clauses?: CorporateClause[];
  evidence?: CorporateEvidence;
};

type Result = {
  policy_id?: string | null;
  eligible?: boolean;
  reason?: string | null;
  items?: Item[];
  total_payable?: number;
  // câmpuri extra, dacă vin din backend
  payer?: string;
  payer_reason?: string | null;
  corporate_meta?: CorporateMeta | null;
};

function Money({ v }: { v: number | undefined }) {
  if (v == null || Number.isNaN(v as any)) return <span>-</span>;
  return (
    <span>
      {v < 0 ? '-' : ''}$
      {Math.abs(Number(v)).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}
    </span>
  );
}

function Chip({ label }: { label: string }) {
  return (
    <span className="inline-block rounded-full border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-300">
      {label}
    </span>
  );
}

export function InsuranceSummary({ tool }: { tool: any }) {
  const result: Result | undefined = tool?.result_json;
  if (!result) return null;

  const rj = tool?.result_json ?? {};
  const corp: CorporateMeta | null = (rj?.corporate_meta as any) ?? null;

  const items = Array.isArray(result.items) ? result.items : [];
  const eligible = result.eligible === true && !!result.policy_id;

  // Compute totals client-side for readability
  const totals = items.reduce(
    (acc, it) => {
      const allowed = Number(it.allowed_amount ?? 0) || 0;
      const payable = Number(it.payable_amount ?? 0) || 0;
      const billed = Number(it.billed ?? 0) || 0;
      acc.patientResp += Math.max(0, allowed - payable);
      acc.balanceBill += Math.max(0, billed - allowed);
      return acc;
    },
    { patientResp: 0, balanceBill: 0 }
  );

  function pill(ok: boolean) {
    return (
      <span
        className={`ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ring-1 ring-inset ${
          ok
            ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
            : 'bg-red-500/15 text-red-300 ring-red-500/30'
        }`}
      >
        {ok ? 'OK' : 'LIMIT REACHED'}
        <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
      </span>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-neutral-800 bg-[#0e0e0e]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div className="text-sm font-medium text-neutral-200">Insurance Summary</div>
        <div className={`text-xs ${eligible ? 'text-emerald-300' : 'text-red-300'}`}>
          {eligible ? 'Policy valid' : 'No valid policy'}
        </div>
      </div>

      <div className="px-4 py-3">
        {/* Top KPIs */}
        <div className="mb-3 grid grid-cols-1 gap-2 text-sm text-neutral-300 sm:grid-cols-3">
          <div>
            <div className="text-neutral-400">Policy</div>
            <div className="font-medium text-neutral-100">{result.policy_id || '—'}</div>
          </div>
          <div>
            <div className="text-neutral-400">Total payable</div>
            <div className="font-medium text-neutral-100">
              <Money v={result.total_payable as any} />
            </div>
          </div>
          <div>
            <div className="text-neutral-400">Client responsibility</div>
            <div className="font-medium text-neutral-100">
              <Money v={totals.patientResp} />
            </div>
          </div>
          <div className="sm:col-span-3">
            <div className="text-neutral-400">Potential balance bill (if out-of-network)</div>
            <div className="font-medium text-neutral-100">
              <Money v={totals.balanceBill} />
            </div>
          </div>
        </div>

        {/* OPTIONAL: Payer & reason din backend dacă există */}
        {(rj.payer || rj.payer_reason) && (
          <div className="mb-3 rounded-xl border border-neutral-900 bg-[#0b0b0b] p-3 text-sm">
            <div className="text-neutral-200">
              Payer: <span className="font-medium text-neutral-100">{rj.payer}</span>
            </div>
            {rj.payer_reason && (
              <div className="mt-1 text-neutral-300 whitespace-pre-wrap">
                Reason: {rj.payer_reason}
              </div>
            )}
          </div>
        )}

        {/* Corporate panel */}
        {corp && (
          <div className="mb-3 rounded-xl border border-[#2b2b2b] bg-[#141414] p-3">
            <div className="mb-1 text-sm font-semibold">
              Corporate decision {corp.is_work_accident ? '- Work accident' : '- Not work accident'}
            </div>

            {corp.reason && (
              <div className="text-neutral-300 text-sm whitespace-pre-wrap">{corp.reason}</div>
            )}

            <div className="mt-2 text-neutral-400 text-xs">
              {typeof corp.confidence === 'number' && (
                <div>Confidence: {Math.round(corp.confidence * 100)}%</div>
              )}
            </div>
          </div>
        )}

        {/* Items */}
        {items.length ? (
          <div className="mb-3 space-y-2">
            {items.map((it, idx) => {
              const limitReached = typeof it.notes === 'string' && /limit reached/i.test(it.notes);
              return (
                <div key={idx} className="rounded-xl border border-neutral-900 bg-[#0b0b0b] p-3">
                  <div className="flex items-center justify-between">
                    <div className="truncate text-sm text-neutral-200">
                      {it.claim_name}
                      {pill(!limitReached)}
                    </div>
                    <div className="text-sm text-neutral-300">
                      Payable:{' '}
                      <span className="font-medium text-neutral-100">
                        <Money v={it.payable_amount} />
                      </span>
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-neutral-400">
                    Allowed: <Money v={it.allowed_amount} /> · Billed: <Money v={it.billed} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-sm text-neutral-400">No items.</div>
        )}

        {/* Footer totals */}
        <div className="mt-2 flex items-center justify-end gap-6 border-t border-neutral-900 pt-3 text-sm text-neutral-300">
          <div>
            Total payable:{' '}
            <span className="font-medium text-neutral-100">
              <Money v={result.total_payable} />
            </span>
          </div>
          <div>
            Client resp:{' '}
            <span className="font-medium text-neutral-100">
              <Money v={totals.patientResp} />
            </span>
          </div>
          <div>
            Balance bill:{' '}
            <span className="font-medium text-neutral-100">
              <Money v={totals.balanceBill} />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
