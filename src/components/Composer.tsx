// Claude-style Composer (drop anywhere in your page or extract to a component)
import { useEffect, useRef, useState } from "react";

const ACCENT = "#c8643c";           // orange
const BG     = "#262624";           // the non-transparent composer fill

type ComposerProps = {
  onSend?: (text: string) => void;
  maxRows?: number;   // default 8
  minRows?: number;   // default 1
  disabledd?: any;
};

export function ClaudeComposer({
  onSend,
  maxRows = 8,
  minRows = 1,
  disabledd
}: ComposerProps) {
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow textarea height between minRows and maxRows.
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;

    // compute a single row height (roughly) from line-height
    const lineHeight = parseFloat(
      getComputedStyle(el).lineHeight || "20"
    );
    const minH = minRows * lineHeight + 14; // + padding
    const maxH = maxRows * lineHeight + 14;

    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, maxH) + "px";
    // lock min height
    if (el.scrollHeight < minH) el.style.height = `${minH}px`;
  }, [value, minRows, maxRows]);

  const disabled = disabledd || value.trim().length === 0;

  function send() {
    if (disabled) return;
    onSend?.(value.trim());
    setValue("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-0 z-10 mx-auto w-full max-w-3xl pb-6">
      <div
        className="pointer-events-auto rounded-2xl border px-4 py-3"
        style={{
          background: BG,
          borderColor: isFocused ? ACCENT : "rgba(255,255,255,0.12)",
          boxShadow: isFocused
            ? `0 0 0 1px ${ACCENT} inset, 0 10px 30px -20px rgba(0,0,0,.8)`
            : "0 10px 30px -20px rgba(0,0,0,.8)",
        }}
      >
        <div className="flex items-start gap-3">
          {/* Growing textarea */}
          <div className="relative flex-1">
            <textarea
              ref={taRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              onKeyDown={onKeyDown}
              placeholder="Reply to Claude..."
              rows={minRows}
              className="w-full resize-none bg-transparent px-1 py-2 text-[15px] leading-6 text-neutral-100 placeholder:text-neutral-400 outline-none"
              style={{
                // keep the caret area visible; overflow handled by maxRows clamp
                overflowY: "auto",
              }}
            />
          </div>

          {/* Right: model label + send */}
          <div className="mt-1 flex items-center gap-2 pl-2">
            <button
              onClick={send}
              disabled={disabled}
              title="Send"
              className="flex h-9 w-9 items-center justify-center rounded-lg transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: ACCENT,
                boxShadow: "inset 0 -1px 0 rgba(0,0,0,.15)",
              }}
            >
              <ArrowUpIcon className="h-4 w-4 text-white" />
            </button>
          </div>
        </div>
      </div>

      <style>{`
        /* smooth focus transitions */
        * { transition: background-color .2s ease, color .2s ease, border-color .2s ease; }
      `}</style>
    </div>
  );
}

/* ----------------------------- inline icons ---------------------------- */

function ChevronIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path d="M8 10l4 4 4-4" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function ArrowUpIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path d="M12 5l0 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      <path d="M7 10l5-5 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
