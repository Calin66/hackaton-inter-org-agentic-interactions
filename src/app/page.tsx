// app/page.tsx
"use client";

import { ClaudeComposer } from "@/Composer";
import { Plus, Search, MessageSquare } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type Message = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  ts?: string;
};

const ACCENT = "#c8643c";

export default function Page() {
  const [messages, setMessages] = useState<Message[]>(() => seedMessages());
  const [input, setInput] = useState("");
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // auto-scroll to bottom on mount & new messages
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages.length]);

  const disabled = input.trim().length === 0;

  function handleSend() {
    if (disabled) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", content: text },
      // mock assistant echo; replace with your API call
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          "Thanks! (This is a placeholder response.) Wire your model call here.",
      },
    ]);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
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
              <SidebarButton label="New claim" accent />
              <SidebarButton label="Search claim" />
              <SidebarButton label="Previous claims" />
            </nav>

            <div className="mt-6 px-4 text-xs uppercase tracking-wider text-neutral-400">
              Recents
            </div>
            <div className="mt-2 space-y-1 px-2">
              <RecentItem title="Claim title" active />
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

          <ClaudeComposer
            onSend={(text) => {
              // your send logic
              console.log("SEND:", text);
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
    if (isUser)
      return "bg-[rgba(200,100,60,0.12)] border-[rgba(200,100,60,0.45)]";
    if (isAssistant) return "bg-[#121212] border-neutral-800";
    return "bg-transparent border-transparent";
  }, [isUser, isAssistant]);

  return (
    <div className="flex gap-3">

      <div
        className={`w-full rounded-2xl border px-4 py-3 leading-relaxed ${bubbleClass}`}
      >
        <RichText content={msg.content} />
      </div>
    </div>
  );
}

// Minimal "rich text" renderer for headings/bullets like in the screenshot
function RichText({ content }: { content: string }) {
  // naive markdown-ish treatment for demo
  const lines = content.split("\n");
  return (
    <div className="prose prose-invert max-w-none prose-p:my-3 prose-li:my-1 prose-strong:text-neutral-100 prose-headings:tracking-tight prose-h2:mb-2 prose-h2:mt-0 prose-h2:text-xl prose-h3:text-lg">
      {lines.map((l, i) => {
        if (l.startsWith("## ")) {
          return <h2 key={i}>{l.slice(3)}</h2>;
        }
        if (l.startsWith("- ")) {
          return (
            <ul key={i} className="my-2 list-disc pl-6">
              <li>{l.slice(2)}</li>
            </ul>
          );
        }
        return <p key={i}>{l}</p>;
      })}
    </div>
  );
}

function SidebarButton({
  label,
  accent = false,
}: {
  label: string;
  accent?: boolean;
}) {
  let Icon = MessageSquare; // default
  if (label.toLowerCase().startsWith("new")) Icon = Plus;
  else if (label.toLowerCase().startsWith("search")) Icon = Search;
  else if (label.toLowerCase().startsWith("previous")) Icon = MessageSquare;

  return (
    <button
      className={`mb-1 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-neutral-900 ${
        accent
          ? "border border-neutral-800 bg-[#151515] text-neutral-100"
          : "text-neutral-300"
      }`}
    >
      <span
        className={`inline-flex h-6 w-6 items-center justify-center rounded-md ${
          accent ? "" : "bg-neutral-700/60"
        }`}
        style={accent ? { background: ACCENT } : undefined}
      >
        <Icon className="h-3 w-3" />
      </span>
      {label}
    </button>
  );
}

function RecentItem({ title, active = false }: { title: string; active?: boolean }) {
  return (
    <button
      className={`group flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm ${
        active ? "bg-neutral-900/70" : "hover:bg-neutral-900/50"
      }`}
    >
      <span className="truncate text-neutral-300">{title}</span>
      <span className="opacity-0 transition-opacity group-hover:opacity-100">
        <DotsIcon className="h-4 w-4 text-neutral-500" />
      </span>
    </button>
  );
}

/* ------------------------------ Icons ---------------------------------- */

function ChevronIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path d="M8 10l4 4 4-4" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function PlusIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function SendIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path
        d="M22 2L11 13"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M22 2L15 22l-4-9-9-4 20-7Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DotsIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <circle cx="5" cy="12" r="1.5" fill="currentColor" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      <circle cx="19" cy="12" r="1.5" fill="currentColor" />
    </svg>
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
