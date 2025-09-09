'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { InsuranceApprovalCard } from '@/components/InsuranceApprovalCard';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '');

type Item = {
  session_id: string;
  status: 'pending' | 'approved' | 'denied' | string;
  invoice: any;
  insurance_reply: { text: string; tool_result?: any };
};

export default function RequestsPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [status, setStatus] = useState<'pending' | 'approved' | 'denied'>('pending');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchItems(st = status) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/insurance/requests?status=${st}`, { cache: 'no-store' });
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
    fetchItems('pending');
    const id = setInterval(() => fetchItems(), 10000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchItems(status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function act(session_id: string, decision: 'approve' | 'deny') {
    try {
      const res = await fetch(`${API_BASE}/approve_insurance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, decision }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      await res.json();
      fetchItems(status);
    } catch (e) {
      // ignore for brevity
    }
  }

  return (
    <div className="h-dvh w-dvw bg-[#0f0f0f] text-neutral-200 antialiased">
      <div className="mx-auto max-w-5xl px-6 py-6">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-xl font-semibold">Insurance Requests</h1>
          <div className="flex items-center gap-3">
            <label className="text-sm text-neutral-300">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as any)}
              className="rounded-lg border border-neutral-800 bg-[#121212] px-3 py-1.5 text-sm text-neutral-200"
            >
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="denied">Denied</option>
            </select>
            <Link className="text-sm text-neutral-300 hover:underline" href="/">Back to Claim Bridge</Link>
          </div>
        </div>

        <div className="rounded-2xl border border-neutral-900 bg-[#111111] p-4">
          {loading ? (
            <div className="text-neutral-400">Loading…</div>
          ) : error ? (
            <div className="text-red-400">{error}</div>
          ) : items.length === 0 ? (
            <div className="text-neutral-400">No {status} items.</div>
          ) : (
            <div className="space-y-4">
              {items.map((it) => {
                const policyValid = it.insurance_reply?.policy_valid === true;
                const canAct = status === 'pending' && policyValid;
                return (
                  <InsuranceApprovalCard
                    key={it.session_id}
                    reply={it.insurance_reply?.text ?? ''}
                    tool={it.insurance_reply?.tool_result}
                    onApprove={canAct ? () => act(it.session_id, 'approve') : noop}
                    onDeny={canAct ? () => act(it.session_id, 'deny') : noop}
                    hideActions={!canAct}
                    header={policyValid ? undefined : 'No valid policy found'}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function noop() {}
