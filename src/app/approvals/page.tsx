'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { InsuranceApprovalCard } from '@/components/InsuranceApprovalCard';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '');

type PendingItem = {
  session_id: string;
  invoice: any;
  insurance_reply: { text: string; tool_result?: any };
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
    // auto-refresh every 10s while on page
    const id = setInterval(fetchItems, 10000);
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
      // Remove from list
      setItems((arr) => arr.filter((x) => x.session_id !== session_id));
    } catch (e) {
      // noop minimal error handling
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Insurance Approvals</h1>
        <Link className="text-sm text-neutral-300 hover:underline" href="/">Back to Claim Bridge</Link>
      </div>

      {loading ? (
        <div className="text-neutral-400">Loading…</div>
      ) : error ? (
        <div className="text-red-400">{error}</div>
      ) : items.length === 0 ? (
        <div className="text-neutral-400">No pending insurance replies.</div>
      ) : (
        <div className="space-y-4">
          {items.map((it) => (
            <InsuranceApprovalCard
              key={it.session_id}
              reply={it.insurance_reply?.text ?? ''}
              tool={it.insurance_reply?.tool_result}
              onApprove={() => act(it.session_id, 'approve')}
              onDeny={() => act(it.session_id, 'deny')}
            />
          ))}
        </div>
      )}
    </div>
  );
}

