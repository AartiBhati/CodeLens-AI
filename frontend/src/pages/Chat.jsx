import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { streamAsk } from "../api/client";

const MODES = [
  { value: "ask_codebase", label: "Ask Codebase" },
  { value: "explain_file", label: "Explain File" },
  { value: "generate_docs", label: "Generate Docs" },
  { value: "architecture_analyzer", label: "Architecture" },
  { value: "bug_investigation", label: "Bug Investigation" },
  { value: "related_files", label: "Related Files" },
];

export default function Chat() {
  const { repositoryId } = useParams();
  const [messages, setMessages] = useState([]); // { role, content, sources }
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("ask_codebase");
  const [filePath, setFilePath] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef(null);

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  async function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || streaming) return;

    const question = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setStreaming(true);
    scrollToBottom();

    await streamAsk({
      repositoryId,
      conversationId,
      question,
      mode,
      filePath: mode === "explain_file" || mode === "generate_docs" ? filePath : null,
      onToken: (token) => {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: next[next.length - 1].content + token,
          };
          return next;
        });
        scrollToBottom();
      },
      onDone: (event) => {
        setConversationId(event.conversation_id);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], sources: event.source_references };
          return next;
        });
        setStreaming(false);
      },
      onError: (msg) => {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: `⚠️ ${msg}` };
          return next;
        });
        setStreaming(false);
      },
    });
  }

  return (
    <main className="mx-auto flex h-[calc(100vh-73px)] max-w-4xl flex-col px-6 py-6">
      <div className="mb-4 flex items-center justify-between">
        <Link to={`/repositories/${repositoryId}`} className="text-sm text-slate-400 hover:text-slate-200">
          ← Repository
        </Link>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-brand-500 focus:outline-none"
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {(mode === "explain_file" || mode === "generate_docs") && (
        <input
          placeholder="File path, e.g. app/services/auth_service.py"
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          className="mb-3 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-brand-500 focus:outline-none"
        />
      )}

      <div ref={scrollRef} className="scrollbar-thin flex-1 space-y-4 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-500">
            Ask anything about this codebase. Answers are grounded only in the indexed repository.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm ${
                m.role === "user" ? "bg-brand-600 text-white" : "bg-slate-800 text-slate-100"
              }`}
            >
              {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
              {m.sources?.length > 0 && (
                <div className="mt-2 border-t border-slate-700 pt-2 text-xs text-slate-400">
                  Sources: {m.sources.join(", ")}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSend} className="mt-4 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about this codebase…"
          className="flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={streaming}
          className="rounded-md bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 transition"
        >
          {streaming ? "Thinking…" : "Send"}
        </button>
      </form>
    </main>
  );
}
