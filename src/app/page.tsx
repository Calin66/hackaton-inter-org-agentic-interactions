'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ClaudeComposer } from '@/components/Composer';
import { SidebarButton } from '@/components/SidebarButton';
import Link from 'next/link';
import { RecentItem } from '@/components/RecentItem';
import { ChatMessage } from '@/components/ChatMessage';
import { SearchModal } from '@/components/SearchModal';
import type { Message, Thread } from '@/types';
import { parseInvoiceFromText, mergeToolResults } from '@/lib/invoice/parse';

/* ----------------------------- Constants -------------------------------- */
const ACCENT = '#c8643c';
const NEXT_PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';
const API_BASE = NEXT_PUBLIC_API_BASE.replace(/\/$/, '');
const INITIAL_THREAD_ID = 't-1'; // deterministic for SSR

type Procedure = { name: string; billed: number };
type Invoice = {
  'patient name': string;
  'patient SSN': string;
  'hospital name': string;
  'date of service': string;
  diagnose: string;
  procedures: Procedure[];
};

type PendingResponse = {
  session_id: string;
  status: 'pending';
  agent_reply: string;
  invoice: Invoice;
};

type ApprovedResponse = {
  session_id: string;
  status: 'approved';
  final_json: Invoice;
  file_path: string;
  // backend doesn't include agent_reply here, so we synthesize a message
};

// Accept both new and legacy shapes
type LegacyResponse = { message?: string; tool_result?: any };

function normalizeResponse(json: any): {
  text: string;
  tool: any;
  status?: 'pending' | 'approved';
  meta?: { file_path?: string; insurance_pending?: any };
} {
  // NEW: pending (include insurance_pending if present)
  if (json && json.status === 'pending') {
    const pr = json as PendingResponse;
    const base = {
      text: (pr as any).agent_reply ?? '',
      tool: (pr as any).invoice ?? null,
      status: 'pending' as const,
    };
    if ((json as any).insurance_pending) {
      return { ...base, meta: { insurance_pending: (json as any).insurance_pending } };
    }
    return base;
  }

  // NEW: approved
  if (json && json.status === 'approved') {
    const ar = json as ApprovedResponse;
    return {
      text:
        `✅ Claim approved and saved.\n\n` +
        (ar.file_path ? `Saved to: ${ar.file_path}\n\n` : '') +
        `Here is the final invoice JSON below.`,
      tool: ar.final_json ?? null,
      status: 'approved',
      meta: { file_path: ar.file_path },
    };
  }

  // Enrich with insurance pending (if present) for non-status responses
  if (json && json.insurance_pending) {
    return {
      text: json.agent_reply ?? '',
      tool: json.invoice ?? null,
      status: 'pending',
      meta: { insurance_pending: json.insurance_pending },
    } as any;
  }

  // LEGACY fallback
  const lr = json as LegacyResponse;
  return {
    text: lr.message ?? '',
    tool: lr.tool_result ?? null,
  };
}

export default function Page() {
  const [threads, setThreads] = useState<Thread[]>([
    { id: INITIAL_THREAD_ID, title: 'Claim 1', active: true },
  ]);
  const [messagesById, setMessagesById] = useState<Record<string, Message[]>>({
    [INITIAL_THREAD_ID]: seedMessages(),
  });

  // to be able to cancel the in-flight request
  const abortRef = useRef<AbortController | null>(null);

  // hydrate from localStorage
  useEffect(() => {
    try {
      const rawT = localStorage.getItem('threads');
      const rawM = localStorage.getItem('messagesById');
      if (rawT && rawM) {
        const parsedT: Thread[] = JSON.parse(rawT);
        const parsedM: Record<string, Message[]> = JSON.parse(rawM);
        if (Array.isArray(parsedT) && parsedT.length) setThreads(parsedT);
        if (parsedM && typeof parsedM === 'object') setMessagesById(parsedM);
      }
    } catch {
      /* ignore */
    }
  }, []);

  // persist to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('threads', JSON.stringify(threads));
      localStorage.setItem('messagesById', JSON.stringify(messagesById));
    } catch {
      /* ignore */
    }
  }, [threads, messagesById]);

  const activeId = useMemo(() => threads.find((t) => t.active)?.id ?? threads[0].id, [threads]);
  const activeMessages = messagesById[activeId] ?? [];
  const hasPendingInsurance = useMemo(
    () => !!activeMessages.find((m: any) => m?.meta?.insurance_pending),
    [activeMessages]
  );

  const [pending, setPending] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  // In-chat insurance approval is disabled; approvals happen on /request
  // NOTE: We now add lightweight in-chat step buttons to trigger
  // 'approve' and 'send to insurance' prompts for better UX.

  // auto-scroll when new messages
  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messagesById[activeId]?.length, pending]);

  // Poll backend for approved/denied insurance decisions when there is a pending one
  useEffect(() => {
    if (!hasPendingInsurance) return;
    let stopped = false;

    async function tick() {
      try {
        const res = await fetch(`${API_BASE}/insurance/requests?status=all`, { cache: 'no-store' });
        if (!res.ok) return;
        const json = await res.json();
        const items = Array.isArray(json?.items) ? json.items : [];
        // Determine which session_id to track from the message meta
        const pendingMsg: any = (activeMessages as any[]).find((m) => m?.meta?.insurance_pending);
        const pendingSid = pendingMsg?.meta?.insurance_pending?.session_id || activeId;
        const it = items.find((x: any) => x?.session_id === pendingSid);
        if (!it) return;
        const st = it.status;

        // Skip if we've already reflected a terminal status
        const alreadyTerminal = threads.find((t) => t.id === activeId && (t as any).insuranceStatus && (t as any).insuranceStatus !== 'pending');
        if (alreadyTerminal) {
          stopped = true;
          return;
        }

        if (st === 'approved') {
          const tool = it?.insurance_reply?.tool_result ?? null;
          const rj = (tool?.result_json ?? {}) as any;
          const payable = typeof rj.total_payable === 'number' ? rj.total_payable : null;
          const policyId = rj.policy_id ?? '';
          const totalStr = payable != null
            ? `$${payable.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '-';
          const header = `## Insurance Decision (Approved)`;
          const lines = [header, `Policy: ${policyId || '-'}`, `Total payable: ${totalStr}`];
          const content = lines.join('\n');

          // Clear pending card meta and append approved message
          setMessagesById((m) => {
            const msgs = (m[activeId] ?? []).map((mm: any) => (mm?.meta?.insurance_pending ? { ...mm, meta: undefined } : mm));
            return {
              ...m,
              [activeId]: [
                ...msgs,
                { id: Math.random().toString(36).slice(2, 10), role: 'assistant', content, tool_result: tool, status: 'approved' } as any,
              ],
            };
          });
          setThreads((ts) => ts.map((t) => (t.id === activeId ? { ...t, insuranceStatus: 'approved' } : t)));
          stopped = true;
        } else if (st === 'denied') {
          setMessagesById((m) => {
            const msgs = (m[activeId] ?? []).map((mm: any) => (mm?.meta?.insurance_pending ? { ...mm, meta: undefined } : mm));
            return {
              ...m,
              [activeId]: [
                ...msgs,
                { id: Math.random().toString(36).slice(2, 10), role: 'assistant', content: 'Insurance denied.', status: 'denied' } as any,
              ],
            };
          });
          setThreads((ts) => ts.map((t) => (t.id === activeId ? { ...t, insuranceStatus: 'denied' } : t)));
          stopped = true;
        }
      } catch {
        // ignore
      }
    }

    // initial and interval
    tick();
    const id = setInterval(() => { if (!stopped) tick(); }, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPendingInsurance, activeId, threads]);

  /* ---------------------------- Thread actions --------------------------- */
  const newId = () => Math.random().toString(36).slice(2, 10);

  function handleChangeConvo(id: string) {
    setThreads((ts) => ts.map((t) => ({ ...t, active: t.id === id })));
  }

  function newClaim() {
    const id = newId();
    setThreads((prev) => {
      const next = prev.map((t) => ({ ...t, active: false }));
      return [...next, { id, title: `Claim ${next.length + 1}`, active: true }];
    });
    setMessagesById((prev) => ({ ...prev, [id]: seedMessages() }));
  }

  function handleDeleteConvo(id: string) {
    setThreads((prev) => {
      const filtered = prev.filter((t) => t.id !== id);
      if (!filtered.length) {
        setMessagesById({ [INITIAL_THREAD_ID]: seedMessages() });
        return [{ id: INITIAL_THREAD_ID, title: 'Claim 1', active: true }];
      }
      if (prev.find((t) => t.id === id)?.active) filtered[0].active = true;
      return filtered;
    });
    setMessagesById(({ [id]: _drop, ...rest }) => rest);
  }

  /* ----------------------------- Networking ----------------------------- */
  // --- Replace your sendToBackend with this ---
  async function sendToBackend(text: string, sessionId: string) {
    // cancel any previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPending(true);
    try {
      const res = await fetch(`${API_BASE}/doctor_message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
        signal: controller.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail || `Request failed with ${res.status}`);
      }

      const json = await res.json();
      const { text: assistantText, tool, status, meta } = normalizeResponse(json);

      if (status === 'approved' && tool?.title) {
        setThreads((ts) =>
          ts.map((t) =>
            t.id === sessionId ? { ...t, title: tool.title } : t
          )
        );
      }

      // If you want to keep using your existing ChatMessage tool pane,
      // store the invoice under `tool_result` (no need to change ChatMessage).
      setMessagesById((m) => ({
        ...m,
        [sessionId]: [
          ...(m[sessionId] ?? []),
          {
            id: newId(),
            role: 'assistant',
            content: assistantText ?? '',
            tool_result: tool, // <- structured invoice lives here
            status, // <- optional: can show a badge in ChatMessage
            meta, // <- optional: contains file_path on approval
          } as any,
        ],
      }));

      // If insurance pending arrived, set sidebar status = pending for this thread
      if (meta && (meta as any).insurance_pending) {
        setThreads((ts) => ts.map((t) => (t.id === sessionId ? { ...t, insuranceStatus: 'pending' } : t)));
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        setMessagesById((m) => ({
          ...m,
          [sessionId]: [
            ...(m[sessionId] ?? []),
            {
              id: newId(),
              role: 'assistant',
              content: `⚠️ Sorry, I couldn't process that request.\n- ${e?.message ?? e}`,
            },
          ],
        }));
      }
    } finally {
      setPending(false);
      abortRef.current = null;
    }
  }

  const filteredThreads = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) => t.title.toLowerCase().includes(q));
  }, [searchQuery, threads]);

  // --------- Action helpers: determine when to show step buttons ---------
  function isInsuranceToolResult(obj: any): boolean {
    if (!obj || typeof obj !== 'object') return false;
    return 'result_json' in obj || 'message' in obj; // shape used by insurance agent
  }
  function isInvoiceShape(obj: any): boolean {
    if (!obj || typeof obj !== 'object') return false;
    if (isInsuranceToolResult(obj)) return false;
    // heuristic: hospital invoice from backend
    return (
      Array.isArray(obj?.procedures) &&
      ('patient name' in obj || 'patient SSN' in obj || 'diagnose' in obj)
    );
  }
  function invoiceReady(inv: any): boolean {
    if (!isInvoiceShape(inv)) return false;
    const hasPN = typeof inv?.['patient name'] === 'string' && inv['patient name'].trim().length > 0;
    const hasSSN = typeof inv?.['patient SSN'] === 'string' && inv['patient SSN'].trim().length > 0;
    const hasDx = typeof inv?.diagnose === 'string' && inv.diagnose.trim().length > 0;
    const hasProcedures = Array.isArray(inv?.procedures) && inv.procedures.length > 0;
    return hasPN && hasSSN && hasDx && hasProcedures;
  }
  const lastAssistantWithTool = useMemo(() => {
    const arr = [...(activeMessages ?? [])].reverse();
    return arr.find((m) => m.role === 'assistant' && (m as any)?.tool_result);
  }, [activeMessages]);
  // Whether we already have an approved message in this thread
  const hasApprovedMessage = useMemo(
    () => !![...(activeMessages ?? [])].reverse().find((m) => (m as any)?.status === 'approved'),
    [activeMessages]
  );
  const threadInsuranceStatus = useMemo(
    () => (threads.find((t) => t.id === activeId) as any)?.insuranceStatus ?? null,
    [threads, activeId]
  );
  // Show Approve when invoice is complete, nothing sent to insurance yet, and not already approved
  const canApproveInvoice = useMemo(() => {
    if (!lastAssistantWithTool) return false;
    const tool = (lastAssistantWithTool as any).tool_result;
    if (!invoiceReady(tool)) return false;
    if (hasApprovedMessage) return false;
    if (hasPendingInsurance) return false;
    if (threadInsuranceStatus === 'approved' || threadInsuranceStatus === 'pending' || threadInsuranceStatus === 'denied') return false;
    return true;
  }, [lastAssistantWithTool, hasApprovedMessage, hasPendingInsurance, threadInsuranceStatus]);
  const canSendToInsurance = useMemo(() => {
    // Show send-to-insurance only after hospital approval exists
    if (!hasApprovedMessage) return false;
    if (hasPendingInsurance) return false; // already sent and awaiting approval
    if (threadInsuranceStatus === 'approved' || threadInsuranceStatus === 'pending' || threadInsuranceStatus === 'denied') return false;
    return true;
  }, [hasApprovedMessage, hasPendingInsurance, threadInsuranceStatus]);

  /* -------------------------------- Render ------------------------------- */
  return (
    <div className="h-dvh w-dvw bg-[#0f0f0f] text-neutral-200 antialiased">
      {/* TOP LOADING BAR */}
      <TopLoader show={pending} />

      <div className="grid h-full w-full grid-cols-[280px_1fr]">
        {/* Sidebar */}
        <aside className="h-full border-r border-neutral-800/80 bg-[#111111]">
          <div className="flex h-full flex-col">
            <div className="px-4 py-4">
              <h1 className="text-xl font-semibold">Claim Bridge</h1>
            </div>

            <nav className="px-2">
              <SidebarButton label="New claim" accent onClick={newClaim} />
              <SidebarButton
                label="Search claim"
                onClick={() => {
                  setSearchQuery('');
                  setSearchOpen(true);
                }}
              />
              <Link href="/request" className="block">
                <SidebarButton label="Requests" />
              </Link>
            </nav>

            <div className="mt-6 px-4 text-xs uppercase tracking-wider text-neutral-400">
              Recents
            </div>
            <div className="mt-2 space-y-1 px-2">
              {threads.map((t) => (
                <RecentItem
                  key={t.id}
                  title={t.title}
                  active={t.active}
                  status={(t as any).insuranceStatus ?? null}
                  handleChangeConvo={() => handleChangeConvo(t.id)}
                  handleDeleteConvo={() => handleDeleteConvo(t.id)}
                />
              ))}
            </div>
          </div>
        </aside>

        {/* Main chat area */}
        <main className="relative flex h-full flex-col">
          {/* Cancel button while pending */}
          {pending && (
            <div className="absolute right-4 top-4 z-10">
              <button
                className="rounded-lg border border-neutral-800 bg-[#161616] px-3 py-1 text-sm hover:bg-[#1c1c1c]"
                onClick={() => {
                  abortRef.current?.abort();
                }}
              >
                Stop
              </button>
            </div>
          )}

          <div
            ref={scrollerRef}
            className="left-1/2 relative -translate-x-1/2 mt-2 h-[calc(100dvh-210px)] w-full max-w-5xl overflow-y-auto px-6 pb-6"
          >
            <div className="max-w-3xl space-y-6 left-1/2 relative -translate-x-1/2 mt-10">
              {activeMessages.map((m) => (
                <ChatMessage key={m.id} msg={m} />
              ))}

              {/* Assistant typing skeleton while waiting */}
              {pending && <AssistantTypingSkeleton />}

              {/* Step action bar: Approve -> Send to insurance */}
              {(canApproveInvoice || canSendToInsurance) && !pending && (
                <div className="sticky bottom-0 z-10 mt-2 rounded-2xl border border-neutral-800 bg-[#121212] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm text-neutral-300">
                      {canApproveInvoice
                        ? 'Invoice is complete. Approve to finalize.'
                        : 'Invoice approved. Send to insurance for verification.'}
                    </div>
                    <div className="flex items-center gap-2">
                      {canApproveInvoice && (
                        <button
                          disabled={pending}
                          onClick={() => {
                            const text = 'approve';
                            setMessagesById((m) => ({
                              ...m,
                              [activeId]: [
                                ...(m[activeId] ?? []),
                                { id: newId(), role: 'user', content: text },
                              ],
                            }));
                            sendToBackend(text, activeId);
                          }}
                          className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                        >
                          Approve
                        </button>
                      )}
                      {canSendToInsurance && (
                        <button
                          disabled={pending}
                          onClick={() => {
                            const text = 'send to insurance';
                            setMessagesById((m) => ({
                              ...m,
                              [activeId]: [
                                ...(m[activeId] ?? []),
                                { id: newId(), role: 'user', content: text },
                              ],
                            }));
                            sendToBackend(text, activeId);
                          }}
                          className="rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                        >
                          Send to insurance
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="py-8" />
            </div>
          </div>

          <ClaudeComposer
            disabledd={pending || threadInsuranceStatus === 'denied'} // disable after denial
            onSend={(text) => {
              const trimmed = (text ?? '').trim();
              if (!trimmed) return;
              setMessagesById((m) => ({
                ...m,
                [activeId]: [
                  ...(m[activeId] ?? []),
                  { id: newId(), role: 'user', content: trimmed },
                ],
              }));
              sendToBackend(trimmed, activeId);
            }}
          />
        </main>
      </div>

      {searchOpen && (
        <SearchModal
          query={searchQuery}
          onQueryChange={setSearchQuery}
          results={filteredThreads}
          onClose={() => setSearchOpen(false)}
          onSelect={(id) => {
            handleChangeConvo(id);
            setSearchOpen(false);
          }}
        />
      )}

      {/* global styles incl. scrollbar + shimmer keyframes */}
      <style>{`
        * { transition: background-color .2s ease, color .2s ease, border-color .2s ease; }
        ::selection { background: ${ACCENT}66; color: white; }
        *::-webkit-scrollbar { height: 12px; width: 12px; }
        *::-webkit-scrollbar-thumb { background: #262626; border-radius: 999px; border: 3px solid #121212; }
        *::-webkit-scrollbar-track { background: transparent; }
        @keyframes shimmer {
          0% { background-position: -200px 0; }
          100% { background-position: 200px 0; }
        }
        @keyframes indeterminate {
          0% { left: -40%; width: 40%; }
          50% { left: 20%; width: 60%; }
          100% { left: 100%; width: 40%; }
        }
      `}</style>
    </div>
  );
}

/* ------------------------------ UI bits --------------------------------- */

function TopLoader({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="fixed inset-x-0 top-0 z-50 h-0.5 bg-transparent">
      <div
        className="relative h-full"
        style={{ background: 'linear-gradient(90deg, transparent, transparent)' }}
      >
        <span
          className="absolute top-0 h-0.5 rounded-r-full"
          style={{
            background: ACCENT,
            animation: 'indeterminate 1.2s ease-in-out infinite',
          }}
        />
      </div>
    </div>
  );
}

function AssistantTypingSkeleton() {
  return (
    <div
      className="w-full rounded-2xl border border-neutral-800 bg-[#121212] px-4 py-3"
      aria-live="polite"
      aria-busy="true"
    >
      <div
        className="mb-2 h-4 w-24 rounded"
        style={{
          background: 'linear-gradient(90deg, #1a1a1a 25%, #222222 37%, #1a1a1a 63%)',
          backgroundSize: '400px 100%',
          animation: 'shimmer 1.2s linear infinite',
        }}
      />
      <div className="space-y-2">
        <ShimmerLine w="90%" />
        <ShimmerLine w="80%" />
        <ShimmerLine w="60%" />
      </div>
      <div className="mt-3 flex items-center gap-2 text-xs text-neutral-400">
        <TypingDots />
        <span>Assistant is typing…</span>
      </div>
    </div>
  );
}

function ShimmerLine({ w = '100%' }: { w?: string }) {
  return (
    <div
      className="h-3 rounded"
      style={{
        width: w,
        background: 'linear-gradient(90deg, #1a1a1a 25%, #222222 37%, #1a1a1a 63%)',
        backgroundSize: '400px 100%',
        animation: 'shimmer 1.2s linear infinite',
      }}
    />
  );
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1">
      <Dot delay="0s" />
      <Dot delay=".15s" />
      <Dot delay=".3s" />
    </span>
  );
}

function Dot({ delay = '0s' }: { delay?: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-500"
      style={{ animation: `pulse 1s ease-in-out infinite`, animationDelay: delay }}
    />
  );
}

/* ------------------------------- Seed ----------------------------------- */

function seedMessages(): Message[] {
  return [
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '## Welcome\nStart a claim in this thread. Paste a clinical note or type free text (name, SSN, diagnosis, procedures). I’ll extract, tariff and summarize cleanly.',
    },
  ];
}

/* (Removed) In-chat insurance approval handlers – now handled on /request */
