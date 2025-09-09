// app/page.tsx
"use client";

import { ClaudeComposer } from "@/Composer";
import { Plus, Search, MessageSquare, TrashIcon, ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type Message = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  ts?: string;
  tool_result?: any; // <- NEW: carry tool result alongside assistant message
};

const ACCENT = "#c8643c";
const NEXT_PUBLIC_API_BASE="http://localhost:8000"
const API_BASE = NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? ""; // e.g. http://localhost:8000

export default function Page() {
  const [messages, setMessages] = useState<Message[]>(() => seedMessages());
  const [items, setItems] = useState([{ title: "Claim 1", id: 1, active: true }]);
  const [pending, setPending] = useState(false);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages.length]);

  function newClaim() {
    handleChangeConvo(items.length + 1);
    setItems((prev) => {
      const maxId = prev.length > 0 ? Math.max(...prev.map((i) => i.id)) : 0;
      return [...prev, { title: `Claim ${maxId + 1}`, id: maxId + 1, active: false }];
    });
  }

  function handleChangeConvo(id: number) {
    setItems(items.map((i) => ({ ...i, active: i.id === id })));
  }

  function handleDeleteConvo(id: number) {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

  async function sendToBackend(text: string) {
    const controller = new AbortController();
    setPending(true);
    try {
      const res = await fetch(`${API_BASE}/doctor_message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail || `Request failed with ${res.status}`);
      }

      const data: { message: string; tool_result?: any } = await res.json();

      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.message ?? "",
          tool_result: data.tool_result, // <- will render under the bubble
        },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `⚠️ Sorry, I couldn't process that request.\n- ${e?.message ?? e}`,
        },
      ]);
    } finally {
      setPending(false);
    }
  }

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
              <SidebarButton label="New claim" accent onClick={() => newClaim()} />
              <SidebarButton label="Search claim" />
            </nav>

            <div className="mt-6 px-4 text-xs uppercase tracking-wider text-neutral-400">
              Recents
            </div>
            <div className="mt-2 space-y-1 px-2">
              {items.map((i) => (
                <RecentItem
                  title={i.title}
                  key={i.id}
                  active={i.active}
                  handleChangeConvo={() => handleChangeConvo(i.id)}
                  handleDeleteConvo={() => handleDeleteConvo(i.id)}
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
            <div className="max-w-3xl space-y-6 left-1/2 relative -translate-x-1/2 mt-10 ">
              {messages.map((m) => (
                <ChatMessage key={m.id} msg={m} />
              ))}
              <div className="py-8" />
            </div>
          </div>

          {/* Composer — call backend on send */}
          <ClaudeComposer
            disabledd={pending}
            onSend={(text) => {
              const trimmed = (text ?? "").trim();
              if (!trimmed) return;
              // optimistic user bubble
              setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: trimmed }]);
              // server call
              sendToBackend(trimmed);
            }}
          />
        </main>
      </div>

      {/* Smooth transitions everywhere */}
      <style>{`
        * { transition: background-color .2s ease, color .2s ease, border-color .2s ease; }
        ::selection { background: ${ACCENT}66; color: white; }
        /* Nice scrollbars */
        *::-webkit-scrollbar { height: 12px; width: 12px; }
        *::-webkit-scrollbar-thumb { background: #262626; border-radius: 999px; border: 3px solid #121212; }
        *::-webkit-scrollbar-track { background: transparent; }
      `}</style>
    </div>
  );
}

/* ----------------------------- Components ------------------------------ */

function ChatMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isAssistant = msg.role === "assistant";

  const bubbleClass = useMemo(() => {
    if (isUser) return "bg-[rgba(200,100,60,0.12)] border-[rgba(200,100,60,0.45)]";
    if (isAssistant) return "bg-[#121212] border-neutral-800";
    return "bg-transparent border-transparent";
  }, [isUser, isAssistant]);

  return (
    <div className="flex gap-3">
      <div className={`w-full rounded-2xl border px-4 py-3 leading-relaxed ${bubbleClass}`}>
        <RichText content={msg.content} />
        {/* Render tool_result under assistant messages when present */}
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
        {open ? <ChevronUp className="h-4 w-4 text-neutral-400" /> : <ChevronDown className="h-4 w-4 text-neutral-400" />}
      </button>
      {open && (
        <pre className="overflow-x-auto whitespace-pre-wrap px-3 pb-3 text-xs text-neutral-300">
{JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// Minimal "rich text" renderer for headings/bullets like in the screenshot
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
        <Icon className="h-3 w-3" />
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

/* ------------------------------ Seed ----------------------------------- */

function seedMessages(): Message[] {
  return [
    {
      id: "m1",
      role: "assistant",
      content:
        "## Text colors\n- Warm whites and light browns that complement the dark backgrounds\n- Border colors: subtle browns for definition without being harsh\n- Button states: darker variants for hover/active\n- Assistant messages: slightly lighter than the main background for contrast\n\n## Key Features:\n- **Input focus**: The input border turns orange (#c8643c) when focused\n- **User messages**: Orange-tinted background matching the accent color\n- **Assistant messages**: Subtle dark background that stands out\n- **Smooth transitions**: All interactive elements have smooth color transitions\n\nThe interface has a warm, sophisticated dark theme similar to Claude’s. The orange accent provides contrast while maintaining readability.",
    },
  ];
}
