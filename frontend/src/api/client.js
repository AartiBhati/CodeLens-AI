import axios from "axios";

const client = axios.create({
  baseURL: "/api/v1",
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("codelens_access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("codelens_access_token");
      localStorage.removeItem("codelens_refresh_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default client;

/**
 * Streams a chat answer via SSE (fetch + ReadableStream, since EventSource
 * doesn't support custom Authorization headers). Calls onToken for each
 * text chunk and onDone once with { source_references, conversation_id }.
 */
export async function streamAsk({ repositoryId, conversationId, question, mode, filePath, onToken, onDone, onError }) {
  const token = localStorage.getItem("codelens_access_token");

  const response = await fetch("/api/v1/chat/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      repository_id: repositoryId,
      conversation_id: conversationId ?? null,
      question,
      mode: mode ?? "ask_codebase",
      file_path: filePath ?? null,
    }),
  });

  if (!response.ok || !response.body) {
    const errText = await response.text().catch(() => "Request failed");
    onError?.(errText);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const jsonStr = line.slice("data: ".length);
      try {
        const event = JSON.parse(jsonStr);
        if (event.type === "token") onToken?.(event.content);
        else if (event.type === "done") onDone?.(event);
        else if (event.type === "error") onError?.(event.message);
      } catch {
        // ignore malformed frame
      }
    }
  }
}
