import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";
import { API, getToken } from "../api";

const urlPattern = /(https?:\/\/[^\s)]+|\/generated\/[^\s)]+)/g;

function copyText(text, setCopied) {
  navigator.clipboard?.writeText(text).then(() => {
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  });
}

function InlineText({ text }) {
  const parts = text.split(urlPattern);
  return parts.map((part, index) => {
    if (!part) return null;
    if (part.match(urlPattern)) {
      const href = part.startsWith("/generated/")
        ? `${API}${part}?token=${encodeURIComponent(getToken() || "")}`
        : part;
      return (
        <a key={`${part}-${index}`} href={href} target="_blank" rel="noreferrer">
          {part}
        </a>
      );
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function CodeBlock({ code, language }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code-block">
      <div className="code-toolbar">
        <span>{language || "code"}</span>
        <button type="button" onClick={() => copyText(code, setCopied)} title="Copy code">
          {copied ? <Check size={14} /> : <Copy size={14} />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

function RenderedMessage({ text }) {
  const segments = useMemo(() => {
    const blocks = [];
    const regex = /```(\w+)?\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        blocks.push({ type: "text", value: text.slice(lastIndex, match.index) });
      }
      blocks.push({ type: "code", language: match[1] || "", value: match[2].trimEnd() });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < text.length) {
      blocks.push({ type: "text", value: text.slice(lastIndex) });
    }
    return blocks;
  }, [text]);

  return segments.map((segment, index) => {
    if (segment.type === "code") {
      return <CodeBlock key={`code-${index}`} code={segment.value} language={segment.language} />;
    }
    return (
      <p key={`text-${index}`} className="message-paragraph">
        <InlineText text={segment.value} />
      </p>
    );
  });
}

export default function Message({ msg }) {
  const [copied, setCopied] = useState(false);
  const isUser = msg.role === "user";

  return (
    <div className={`message-row ${isUser ? "user" : "ai"}`}>
      <div className={`message-bubble ${isUser ? "user" : "ai"}`}>
        {msg.text === "typing" ? (
          <span className="thinking">
            <span>Thinking</span>
            <span className="thinking-dots">
              <span>.</span><span>.</span><span>.</span>
            </span>
          </span>
        ) : (
          <>
            <RenderedMessage text={msg.text || ""} />
            {!isUser && msg.text && (
              <button
                className="message-copy"
                type="button"
                onClick={() => copyText(msg.text, setCopied)}
                title="Copy message"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
