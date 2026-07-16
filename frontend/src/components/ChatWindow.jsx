import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { API, createChat, getModelStatus, scrapeAssignmentPage, uploadFileToChat } from "../api";
import InputBar from "./InputBar";
import Message from "./Message";

export default function ChatWindow({ currentChat, setCurrentChat }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("qwen3:8b");
  const [modelStatus, setModelStatus] = useState(null);
  const bottomRef = useRef(null);
  const skipHistoryForChatRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let active = true;

    const loadModelStatus = async () => {
      const status = await getModelStatus();
      if (active) setModelStatus(status);
    };

    loadModelStatus();
    const interval = setInterval(loadModelStatus, 15000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const availableModels = Object.keys(modelStatus?.models || {});
    if (!availableModels.length || availableModels.includes(model)) return;
    setModel(modelStatus.default && availableModels.includes(modelStatus.default)
      ? modelStatus.default
      : availableModels[0]);
  }, [modelStatus, model]);

  useEffect(() => {
    if (!currentChat) {
      setMessages([]);
      return;
    }

    if (skipHistoryForChatRef.current === currentChat) {
      skipHistoryForChatRef.current = null;
      return;
    }

    const loadHistory = async () => {
      setLoading(true);
      try {
        const token = localStorage.getItem("token");
        const res = await fetch(`http://127.0.0.1:8000/history/${currentChat}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (res.status === 401) {
          localStorage.removeItem("token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
          return;
        }

        const data = await res.json();
        setMessages(
          Array.isArray(data)
            ? data.map((m) => ({
                role: m.role === "assistant" ? "ai" : "user",
                text: m.content,
              }))
            : []
        );
      } catch (err) {
        console.error("Error loading history:", err);
        setMessages([]);
      } finally {
        setLoading(false);
      }
    };

    loadHistory();
  }, [currentChat]);

  useEffect(() => {
    const refreshHistory = async () => {
      if (!currentChat) return;
      try {
        const token = localStorage.getItem("token");
        const res = await fetch(`http://127.0.0.1:8000/history/${currentChat}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        if (Array.isArray(data)) {
          setMessages(data.map((m) => ({
            role: m.role === "assistant" ? "ai" : "user",
            text: m.content,
          })));
        }
      } catch (err) {
        console.error("Error refreshing history:", err);
      }
    };

    window.addEventListener("chat-history-updated", refreshHistory);
    return () => window.removeEventListener("chat-history-updated", refreshHistory);
  }, [currentChat]);

  const ensureChat = async () => {
    if (currentChat) return currentChat;

    const chat = await createChat();
    if (!chat || chat.error) throw new Error("Could not create a new chat.");
    skipHistoryForChatRef.current = chat.id;
    setCurrentChat(chat.id);
    window.dispatchEvent(new Event("chats-updated"));
    return chat.id;
  };

  const replaceLastAiMessage = (text) => {
    setMessages((prev) => {
      const updated = [...prev];
      const lastIndex = updated.length - 1;
      if (lastIndex >= 0 && updated[lastIndex]?.role === "ai") {
        updated[lastIndex] = { role: "ai", text };
      }
      return updated;
    });
  };

  const send = async (input) => {
    if (!input?.trim() || busy) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", text: input },
      { role: "ai", text: "typing" },
    ]);
    setBusy(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const chatId = await ensureChat();
      const token = localStorage.getItem("token");
      const res = await fetch(`${API}/agent`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: input, chat_id: chatId, model }),
        signal: abortController.signal,
      });

      if (res.status === 401) {
        localStorage.removeItem("token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
        return;
      }

      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Could not start AI response");
      }

      // The agent streams NDJSON events: status (tool activity), token
      // (answer text), error, done. Show tool activity live, then the answer.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answer = "";
      let statusLog = [];

      const render = () => {
        const activity = statusLog.map((s) => `🔧 ${s}`).join("\n");
        const text = answer.trim()
          ? answer
          : activity
            ? `${activity}\n\n_working..._`
            : "typing";
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "ai", text };
          return updated;
        });
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          let event;
          try {
            event = JSON.parse(line);
          } catch {
            continue;
          }
          if (event.type === "status") {
            statusLog.push(event.text);
            answer = "";
          } else if (event.type === "token") {
            answer += event.text;
          } else if (event.type === "error") {
            answer = answer || event.text;
          }
          render();
        }
      }

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "ai",
          text: answer.trim() || "Done.",
        };
        return updated;
      });
      window.dispatchEvent(new Event("chats-updated"));
    } catch (err) {
      console.error("Stream error:", err);
      if (err.name === "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          updated[updated.length - 1] = {
            role: "ai",
            text: last?.text && last.text !== "typing"
              ? `${last.text}\n\n[Response stopped]`
              : "Response stopped.",
          };
          return updated;
        });
        return;
      }
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "ai",
          text: err.message || "Something went wrong while streaming.",
        };
        return updated;
      });
    } finally {
      abortControllerRef.current = null;
      setBusy(false);
    }
  };

  const upload = async (file) => {
    if (!file || busy) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", text: `Uploaded file: ${file.name}` },
      { role: "ai", text: "Reading and indexing the file..." },
    ]);
    setBusy(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const progressMessages = [
      "Reading the file...",
      "Extracting text and tables...",
      "Creating searchable memory...",
      "Checking what useful details were found...",
    ];
    let progressIndex = 0;
    const progressTimer = setInterval(() => {
      progressIndex = (progressIndex + 1) % progressMessages.length;
      replaceLastAiMessage(progressMessages[progressIndex]);
    }, 2200);

    try {
      const chatId = await ensureChat();
      const result = await uploadFileToChat(chatId, file, abortController.signal, model);

      if (result.error || result.detail) {
        throw new Error(result.detail || result.error || "Upload failed");
      }

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "ai",
          text: result.assistant_message || `I added ${result.filename} to this chat and saved ${result.chunks} searchable chunks. Ask me anything about it.`,
        };
        return updated;
      });
      window.dispatchEvent(new Event("chats-updated"));
    } catch (err) {
      if (err.name === "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "ai", text: "Upload stopped." };
          return updated;
        });
        return;
      }
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "ai",
          text: err.message || "Upload failed.",
        };
        return updated;
      });
    } finally {
      clearInterval(progressTimer);
      abortControllerRef.current = null;
      setBusy(false);
    }
  };

  const attachLink = async (url, options = {}) => {
    if (busy) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", text: `Added page: ${url}` },
      {
        role: "ai",
        text: options.manualLogin
          ? "Opening a visible browser. Log in there if needed, then leave it on the page while I read it..."
          : "Opening the page, reading visible text, and checking linked PDFs...",
      },
    ]);
    setBusy(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const progressMessages = options.manualLogin
      ? [
          "Waiting for the browser login to finish...",
          "Reading the page now...",
          "Finding linked PDFs, files, and references...",
          "Saving the useful page context...",
        ]
      : [
          "Opening the page...",
          "Reading visible text...",
          "Finding linked PDFs, files, and references...",
          "Saving the useful page context...",
        ];
    let progressIndex = 0;
    const progressTimer = setInterval(() => {
      progressIndex = (progressIndex + 1) % progressMessages.length;
      replaceLastAiMessage(progressMessages[progressIndex]);
    }, 2500);

    try {
      const chatId = await ensureChat();
      const result = await scrapeAssignmentPage(chatId, url, abortController.signal, options);

      if (result.error || result.detail) {
        throw new Error(result.detail || result.error || "Could not read that page.");
      }

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "ai",
          text: result.assistant_message || `I added ${result.title || "that page"} to this chat and saved ${result.chunks} searchable chunks.`,
        };
        return updated;
      });
      window.dispatchEvent(new Event("chats-updated"));
    } catch (err) {
      if (err.name === "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "ai", text: "Page read stopped." };
          return updated;
        });
        return;
      }
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "ai",
          text: err.message || "Could not read that page link.",
        };
        return updated;
      });
    } finally {
      clearInterval(progressTimer);
      abortControllerRef.current = null;
      setBusy(false);
    }
  };

  const stopCurrentWork = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      return;
    }

    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last?.role === "ai" && (last.text === "typing" || last.text.includes("Reading") || last.text.includes("Opening"))) {
        updated[updated.length - 1] = { role: "ai", text: "Stopped." };
      }
      return updated;
    });
    setBusy(false);
  };

  const selectedModelStatus = modelStatus?.models?.[model];
  const modelAvailable = selectedModelStatus?.available;
  const availableModelEntries = Object.entries(modelStatus?.models || {});
  const modelLabel = !modelStatus
    ? "Checking"
    : modelStatus.ollama === "offline"
      ? "Ollama offline"
      : modelAvailable
        ? "Active"
        : "Not installed";

  return (
    <>
      <div className="chat-header">
        <div>
          <h1>AI Study Assistant</h1>
          <span>
            {currentChat
              ? "Chat with your notes, PDFs, and images"
              : "Start typing or attach a file"}
          </span>
        </div>
        <div className="model-control" title={`Selected model: ${modelLabel}`}>
          <span
            className={`model-dot ${
              !modelStatus ? "checking" : modelAvailable ? "active" : "inactive"
            }`}
          />
          <select
            className="model-select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            title="Ollama model"
            disabled={modelStatus?.ollama === "offline"}
          >
            {availableModelEntries.length ? (
              availableModelEntries.map(([modelKey, info]) => (
                <option key={modelKey} value={modelKey}>
                  {info.vision ? `${modelKey} (vision)` : modelKey}
                </option>
              ))
            ) : (
              <>
                <option value="qwen3:8b">Qwen 3 8B</option>
                <option value="qwen2.5vl:7b">Qwen 2.5 VL (vision)</option>
              </>
            )}
          </select>
          <span className="model-status-text">{modelLabel}</span>
        </div>
      </div>

      <div className="message-scroll">
        <div className="message-column">
          {!currentChat ? (
            <div className="empty-state">
              <h2>How can I help you study?</h2>
                  <p>Type a message, attach a file, or add a page link. I will create the chat automatically.</p>
            </div>
          ) : loading ? (
            [1, 2, 3].map((i) => (
              <div
                key={i}
                style={{
                  height: "20px",
                  width: `${58 + i * 9}%`,
                  background: "var(--skeleton)",
                  borderRadius: "8px",
                  marginBottom: "15px",
                  animation: "pulse 1.5s infinite",
                }}
              />
            ))
          ) : (
            <AnimatePresence>
              {messages.length === 0 ? (
                <div className="empty-state">
                  <h2>New chat</h2>
                  <p>Ask anything, attach a file, or add a page link below.</p>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <motion.div
                    key={`${i}-${msg.role}`}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                  >
                    <Message msg={msg} />
                  </motion.div>
                ))
              )}
            </AnimatePresence>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <InputBar
        send={send}
        upload={upload}
        attachLink={attachLink}
        stop={stopCurrentWork}
        disabled={loading || busy}
        busy={busy}
      />

      <style>
        {`
        @keyframes pulse {
          0% { opacity: 0.35; }
          50% { opacity: 0.7; }
          100% { opacity: 0.35; }
        }
        `}
      </style>
    </>
  );
}
