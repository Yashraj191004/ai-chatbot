import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { Link, Mic, MicOff, Paperclip, SendHorizontal, Square } from "lucide-react";

export default function InputBar({ send, upload, attachLink, stop, disabled = false, busy = false }) {
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const fileInputRef = useRef(null);
  const recognitionRef = useRef(null);
  const canUse = typeof send === "function" && !disabled;

  const handleSend = () => {
    if (!canUse || !input.trim()) return;
    send(input);
    setInput("");
  };

  const handleFile = (file) => {
    if (!file || typeof upload !== "function" || disabled) return;
    upload(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleLink = () => {
    if (typeof attachLink !== "function" || disabled) return;
    const url = prompt("Paste page link:");
    if (!url?.trim()) return;
    const manualLogin = confirm(
      "Does this page require login? Choose OK to open a visible browser for login, or Cancel for normal reading."
    );
    attachLink(url.trim(), { manualLogin, loginWaitSeconds: manualLogin ? 90 : 0 });
  };

  const toggleVoice = () => {
    if (disabled) return;

    if (recognitionRef.current && listening) {
      recognitionRef.current.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setVoiceError("Voice typing is not supported in this browser. Try Chrome or Edge.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    let finalTranscript = "";
    recognition.onstart = () => {
      setVoiceError("");
      setListening(true);
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      const spokenText = `${finalTranscript}${interimTranscript}`.trim();
      if (spokenText) {
        setInput((prev) => {
          const base = prev.replace(/\s*\[listening:.*?\]\s*$/i, "").trim();
          const suffix = interimTranscript ? ` [listening: ${spokenText}]` : spokenText;
          return `${base ? `${base} ` : ""}${suffix}`;
        });
      }
    };

    recognition.onerror = (event) => {
      setVoiceError(event.error === "not-allowed"
        ? "Microphone permission was blocked."
        : "Voice typing stopped. Try again.");
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
      setInput((prev) => prev.replace(/\s*\[listening: (.*?)\]\s*$/i, " $1").trim());
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  return (
    <div className="composer">
      <div className="composer-inner">
        <button
          className="attach-button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title="Attach file"
        >
          <Paperclip size={20} />
        </button>

        <button
          className="attach-button"
          onClick={handleLink}
          disabled={disabled}
          title="Attach page link"
        >
          <Link size={20} />
        </button>

        <button
          className={`attach-button ${listening ? "listening" : ""}`}
          onClick={toggleVoice}
          disabled={disabled}
          title={listening ? "Stop voice typing" : "Voice typing"}
        >
          {listening ? <MicOff size={20} /> : <Mic size={20} />}
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tiff,.txt,.md,.csv,.docx,.xlsx,.xlsm"
          onChange={(e) => handleFile(e.target.files?.[0])}
          style={{ display: "none" }}
        />

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything..."
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          disabled={!canUse}
          className="chat-input"
        />

        {busy ? (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={stop}
            className="stop-button"
            title="Stop response"
          >
            <Square size={18} fill="currentColor" />
          </motion.button>
        ) : (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleSend}
            disabled={!canUse || !input.trim()}
            className="send-button"
            style={{ opacity: canUse && input.trim() ? 1 : 0.65 }}
            title="Send"
          >
            <SendHorizontal size={20} />
          </motion.button>
        )}
      </div>
      {voiceError ? <div className="voice-error">{voiceError}</div> : null}
    </div>
  );
}
