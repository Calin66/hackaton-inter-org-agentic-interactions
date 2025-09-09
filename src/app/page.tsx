// app/page.tsx
"use client";

import { ClaudeComposer } from "@/Composer";
import {
  Plus,
  Search,
  MessageSquare,
  TrashIcon,
  ChevronDown,
  ChevronUp,
  X as CloseIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

/* ------------------------------- Types ---------------------------------- */

type Message = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  ts?: string;
  tool_result?: any;
};

type Thread = { id: string; title: string; active: boolean };

/* ----------------------------- Constants -------------------------------- */

const ACCENT = "#c8643c";
const NEXT_PUBLIC_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_BASE = NEXT_PUBLIC_API_BASE.replace(/\/$/, "");

// IMPORTANT: deterministic ID used on the first server render
const INITIAL_THREAD_ID = "t-1";

/* -------------------------------- Page ---------------------------------- */

export default function Page() {
  // Deterministic, SSR-safe initial state (no random, no localStorage)
  const [threads, setThreads] = useState<Thread[]>([
    { id: INITIAL_THREAD_ID, title: "Claim 1", active: true },
  ]);

  const [messagesById, setMessagesById] = useState<Record<string, Message[]>>({
    [INITIAL_THREAD_ID]: seedMessages(),
  });

  // After mount, hydrate from localStorage (client only)
  useEffect(() => {
    try {
      const rawT = localStorage.getItem("threads");
      const rawM = localStorage.getItem("messagesById");
      if (rawT && rawM) {
        const parsedT: Thread[] = JSON.parse(rawT);
        const parsedM: Record<string, Message[]> = JSON.parse(rawM);
        // sanity guard: ensure there's at least one thread/messages list
        if (Array.isArray(parsedT) && parsedT.length > 0) setThreads(parsedT);
        if (parsedM && typeof parsedM === "object") setMessagesById(parsedM);
      }
    } catch {
      /* ignore localStorage parse errors */
    }
  }, []);

  const activeId = useMemo(
    () => threads.find((t) => t.active)?.id ?? threads[0].id,
    [threads]
  );

  const [pending, setPending] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll on new messages in active thread
  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messagesById[activeId]?.length]);

  // Persist to localStorage (client)
  useEffect(() => {
    try {
      localStorage.setItem("threads", JSON.stringify(threads));
      localStorage.setItem("messagesById", JSON.stringify(messagesById));
    } catch {
      /* ignore */
    }
  }, [threads, messagesById]);

  /* ---------------------------- Thread actions --------------------------- */

  function handleChangeConvo(id: string) {
    setThreads((ts) => ts.map((t) => ({ ...t, active: t.id === id })));
  }

  function newId() {
    // Generates on client after hydration, so randomness is OK here.
    return Math.random().toString(36).slice(2, 10);
  }

  function newClaim() {
    const id = newId();
    // 1) Activate the new thread
    setThreads((prev) => {
      const next = prev.map((t) => ({ ...t, active: false }));
      return [...next, { id, title: `Claim ${next.length + 1}`, active: true }];
    });
    // 2) Seed welcome message (always)
    setMessagesById((prev) => ({ ...prev, [id]: seedMessages() }));
  }

  function handleDeleteConvo(id: string) {
    setThreads((prev) => {
      const filtered = prev.filter((t) => t.id !== id);
      if (!filtered.length) {
        // recreate deterministic default thread
        setMessagesById({ [INITIAL_THREAD_ID]: seedMessages() });
        return [{ id: INITIAL_THREAD_ID, title: "Claim 1", active: true }];
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
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail || `Request failed with ${res.status}`);
      }
      const data: { message: string; tool_result?: any } = await res.json();
      setMessagesById((m) => ({
        ...m,
        [sessionId]: [
          ...(m[sessionId] ?? []),
          {
            id: newId(),
            role: "assistant",
            content: data.message ?? "",
            tool_result: data.tool_result,
          },
        ],
      }));
    } catch (e: any) {
      setMessagesById((m) => ({
        ...m,
        [sessionId]: [
          ...(m[sessionId] ?? []),
          {
            id: newId(),
            role: "assistant",
            content: `⚠️ Sorry, I couldn't process that request.\n- ${
              e?.message ?? e
            }`,
          },
        ],
      }));
    } finally {
      setPending(false);
    }
  }

  const activeMessages = messagesById[activeId] ?? [];

  // Simple local, title-only search of threads
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
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold">Claim Bridge</h1>
              </div>
            </div>

            <nav className="px-2">
              <SidebarButton label="New claim" accent onClick={newClaim} />
              <SidebarButton
                label="Search claim"
                onClick={() => {
                  setSearchQuery("");
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
                  title={t.title}
                  key={t.id}
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
          {/* Messages */}
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

          {/* Composer */}
          <ClaudeComposer
            disabledd={pending}
            onSend={(text) => {
              const trimmed = (text ?? "").trim();
              if (!trimmed) return;
              // optimistic user bubble
              setMessagesById((m) => ({
                ...m,
                [activeId]: [
                  ...(m[activeId] ?? []),
                  { id: newId(), role: "user", content: trimmed },
                ],
              }));
              // server call
              sendToBackend(trimmed, activeId);
            }}
          />
        </main>
      </div>

      {/* Search modal */}
      {searchOpen ? (
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
      ) : null}

      {/* Smooth transitions */}
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

/* ----------------------------- Components ------------------------------- */

function ChatMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isAssistant = msg.role === "assistant";

  const bubbleClass = isUser
    ? "bg-[rgba(200,100,60,0.12)] border-[rgba(200,100,60,0.45)]"
    : isAssistant
    ? "bg-[#121212] border-neutral-800"
    : "bg-transparent border-transparent";

  return (
    <div className="flex gap-3">
      <div className={`w-full rounded-2xl border px-4 py-3 leading-relaxed ${bubbleClass}`}>
        <RichText content={msg.content} />
        {isAssistant && msg.tool_result !== undefined ? (
          <div className="mt-3">
            <ToolResultCard data={msg.tool_result} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ToolResultCard({ data }: { data: any }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rounded-xl border border-neutral-800 bg-[#0f0f0f]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-sm hover:bg-neutral-900/60"
      >
        <span className="font-medium text-neutral-200">Tool result</span>
        {open ? (
          <ChevronUp className="h-4 w-4 text-neutral-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-neutral-400" />
        )}
      </button>
      {open && (
        <pre className="overflow-x-auto whitespace-pre-wrap px-3 pb-3 text-xs text-neutral-300">
{JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function RichText({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="prose prose-invert max-w-none prose-p:my-3 prose-li:my-1 prose-strong:text-neutral-100 prose-headings:tracking-tight prose-h2:mb-2 prose-h2:mt-0 prose-h2:text-xl prose-h3:text-lg">
      {lines.map((l, i) => {
        if (l.startsWith("## ")) return <h2 key={i}>{l.slice(3)}</h2>;
        if (l.startsWith("- "))
          return (
            <ul key={i} className="my-2 list-disc pl-6">
              <li>{l.slice(2)}</li>
            </ul>
          );
        return <p key={i}>{l}</p>;
      })}
    </div>
  );
}

function SidebarButton({
  label,
  accent = false,
  onClick = () => {},
}: {
  label: string;
  accent?: boolean;
  onClick?: any;
}) {
  let Icon = MessageSquare;
  if (label.toLowerCase().startsWith("new")) Icon = Plus;
  else if (label.toLowerCase().startsWith("search")) Icon = Search;

  return (
    <button
      className={`mb-1 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-neutral-900 cursor-pointer ${
        accent ? "border border-neutral-800 bg-[#151515] text-neutral-100" : "text-neutral-300"
      }`}
      onClick={onClick}
    >
      <span
        className={`inline-flex h-6 w-6 items-center justify-center rounded-md ${accent ? "" : "bg-neutral-700/60"}`}
        style={accent ? { background: ACCENT } : undefined}
      >
        <MessageSquare className="h-3 w-3" />
      </span>
      {label}
    </button>
  );
}

function RecentItem({
  title,
  active = false,
  handleChangeConvo = () => {},
  handleDeleteConvo = () => {},
}: {
  title: string;
  active?: boolean;
  handleChangeConvo?: any;
  handleDeleteConvo?: any;
}) {
  return (
    <button
      className={`group flex w-full cursor-pointer items-center justify-between rounded-xl px-3 py-2 text-sm ${
        active ? "bg-neutral-900/70" : "hover:bg-neutral-900/50"
      }`}
      onClick={handleChangeConvo}
    >
      <span className="truncate text-neutral-300">{title}</span>
      <span
        className="opacity-0 transition-opacity group-hover:opacity-100 hover:opacity-50"
        onClick={(e) => {
          e.stopPropagation();
          handleDeleteConvo();
        }}
      >
        <TrashIcon className="h-4 w-4 text-neutral-500" />
      </span>
    </button>
  );
}

/* ------------------------------ Search UI ------------------------------- */

function SearchModal({
  query,
  onQueryChange,
  results,
  onSelect,
  onClose,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  results: Thread[];
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4">
      <div className="mt-20 w-full max-w-xl rounded-2xl border border-neutral-800 bg-[#121212] shadow-xl">
        <div className="flex items-center gap-2 border-b border-neutral-800 px-4 py-3">
          <Search className="h-4 w-4 text-neutral-400" />
          <input
            autoFocus
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search claims by title…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-neutral-500"
          />
          <button
            onClick={onClose}
            className="rounded-md p-1 text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-2 py-2">
          {results.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-neutral-500">
              No matches
            </div>
          ) : (
            results.map((t) => (
              <button
                key={t.id}
                onClick={() => onSelect(t.id)}
                className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-neutral-900"
              >
                <div className="truncate">
                  <div className="text-sm text-neutral-200">{t.title}</div>
                  <div className="text-xs text-neutral-500">{t.id}</div>
                </div>
                {t.active ? (
                  <span className="rounded-md border border-neutral-700 px-2 py-0.5 text-xs text-neutral-400">
                    Active
                  </span>
                ) : null}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------- Seed ----------------------------------- */

function seedMessages(): Message[] {
  return [
    {
      id: "welcome",
      role: "assistant",
      content:
        "## Welcome\nStart a claim in this thread. Create new threads in the sidebar to keep conversations separated.",
    },
  ];
}
