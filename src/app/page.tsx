'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ClaudeComposer } from '@/components/Composer';
import { SidebarButton } from '@/components/SidebarButton';
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

export default function Page() {
  const [threads, setThreads] = useState<Thread[]>([
    { id: INITIAL_THREAD_ID, title: 'Claim 1', active: true },
  ]);
  const [messagesById, setMessagesById] = useState<Record<string, Message[]>>({
    [INITIAL_THREAD_ID]: seedMessages(),
  });

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

  const [pending, setPending] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  // auto-scroll when new messages
  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messagesById[activeId]?.length]);

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
  async function sendToBackend(text: string, sessionId: string) {
    setPending(true);
    try {
      const res = await fetch(`${API_BASE}/doctor_message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail || `Request failed with ${res.status}`);
      }
      const data: { message: string; tool_result?: any } = await res.json();

      const parsed = parseInvoiceFromText(data.message ?? '');
      const mergedTool = mergeToolResults(data.tool_result, parsed);

      setMessagesById((m) => ({
        ...m,
        [sessionId]: [
          ...(m[sessionId] ?? []),
          { id: newId(), role: 'assistant', content: data.message ?? '', tool_result: mergedTool },
        ],
      }));
    } catch (e: any) {
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
    } finally {
      setPending(false);
    }
  }

  const filteredThreads = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) => t.title.toLowerCase().includes(q));
  }, [searchQuery, threads]);

  /* -------------------------------- Render ------------------------------- */
  return (
    <div className="h-dvh w-dvw bg-[#0f0f0f] text-neutral-200 antialiased">
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
                  handleChangeConvo={() => handleChangeConvo(t.id)}
                  handleDeleteConvo={() => handleDeleteConvo(t.id)}
                />
              ))}
            </div>
          </div>
        </aside>

        {/* Main chat area */}
        <main className="relative flex h-full flex-col">
          <div
            ref={scrollerRef}
            className="left-1/2 relative -translate-x-1/2 mt-2 h-[calc(100dvh-210px)] w-full max-w-5xl overflow-y-auto px-6 pb-6"
          >
            <div className="max-w-3xl space-y-6 left-1/2 relative -translate-x-1/2 mt-10">
              {activeMessages.map((m) => (
                <ChatMessage key={m.id} msg={m} />
              ))}
              <div className="py-8" />
            </div>
          </div>

          <ClaudeComposer
            disabledd={pending}
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

      <style>{`
        * { transition: background-color .2s ease, color .2s ease, border-color .2s ease; }
        ::selection { background: ${ACCENT}66; color: white; }
        *::-webkit-scrollbar { height: 12px; width: 12px; }
        *::-webkit-scrollbar-thumb { background: #262626; border-radius: 999px; border: 3px solid #121212; }
        *::-webkit-scrollbar-track { background: transparent; }
      `}</style>
    </div>
  );
}

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
