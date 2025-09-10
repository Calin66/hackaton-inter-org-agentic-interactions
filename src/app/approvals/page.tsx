'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { InsuranceApprovalCard } from '@/components/InsuranceApprovalCard';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8002').replace(/\/$/, '');

type PendingItem = {
  session_id: string;
  invoice: any;
  insurance_reply: {
    text: string;
    tool_result?: {
      result_json?: {
        policy_id?: string | null;
        eligible?: boolean;
        payer?: 'patient' | 'corporation';
        corporate_meta?: {
          decision_id?: string;
          suggested?: { is_work_accident?: boolean; payer?: 'patient' | 'corporation' };
        } | null;
      };
    };
  };
};

export default function ApprovalsPage() {
  const [items, setItems] = useState<PendingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchItems() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/insurance/pending`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const json = await res.json();
      setItems(json?.items ?? []);
    } catch (e: any) {
      setError(e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchItems();
    const id = setInterval(fetchItems, 8000);
    return () => clearInterval(id);
  }, []);

  async function act(session_id: string, decision: 'approve' | 'deny') {
    try {
      const res = await fetch(`${API_BASE}/approve_insurance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, decision }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      await res.json();
      // Remove from list after decision
      setItems((arr) => arr.filter((x) => x.session_id !== session_id));
    } catch {
      /* ignore */
    }
  }

  function headerFor(it: PendingItem): string | undefined {
    const rj = it.insurance_reply?.tool_result?.result_json ?? {};
    const payer = rj?.payer;
    const corp = rj?.corporate_meta ?? null;
    const isWA = corp?.suggested?.is_work_accident;
    const decisionId = corp?.decision_id;

    const bits: string[] = [];
    if (payer) bits.push(`Payer (rest): ${payer}`);
    if (typeof isWA === 'boolean') bits.push(`Work accident: ${isWA ? 'yes' : 'no'}`);
    if (decisionId) bits.push(`Decision ID: ${decisionId}`);

    const policyValid = Boolean(rj?.eligible && rj?.policy_id);
    if (!policyValid) return 'No valid policy found';
    return bits.length ? bits.join(' · ') : undefined;
  }

  function canAct(it: PendingItem): boolean {
    const rj = it.insurance_reply?.tool_result?.result_json ?? {};
    return Boolean(rj?.eligible && rj?.policy_id);
  }

  return (
    <div className="h-dvh w-dvw bg-[#0f0f0f] text-neutral-200 antialiased">
      <div className="mx-auto max-w-4xl px-6 py-6">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold">Insurance Approvals</h1>
          <Link className="text-sm text-neutral-300 hover:underline" href="/">
            Back to Claim Bridge
          </Link>
        </div>

        {loading ? (
          <div className="text-neutral-400">Loading…</div>
        ) : error ? (
          <div className="text-red-400">{error}</div>
        ) : items.length === 0 ? (
          <div className="text-neutral-400">No pending insurance replies.</div>
        ) : (
          <div className="space-y-4">
            {items.map((it) => {
              const enabled = canAct(it);
              return (
                <InsuranceApprovalCard
                  key={it.session_id}
                  reply={it.insurance_reply?.text ?? ''}
                  tool={it.insurance_reply?.tool_result}
                  onApprove={enabled ? () => act(it.session_id, 'approve') : undefined}
                  onDeny={enabled ? () => act(it.session_id, 'deny') : undefined}
                  hideActions={!enabled}
                  header={headerFor(it)}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
