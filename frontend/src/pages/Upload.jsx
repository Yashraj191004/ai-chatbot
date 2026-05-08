import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { FileUp } from "lucide-react";
import ThemeToggle from "../components/ThemeToggle";

export default function Upload() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const currentChat = searchParams.get("chatId");
  const [uploading, setUploading] = useState(false);

  const uploadFile = async (files) => {
    if (!currentChat) {
      alert("Please create or select a chat first.");
      return;
    }

    const file = files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`http://127.0.0.1:8000/upload/${currentChat}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        body: formData,
      });

      if (res.status === 401) {
        localStorage.removeItem("token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert("Upload failed: " + (data.detail || data.error || res.statusText));
        return;
      }

      navigate(`/?chatId=${currentChat}`, { replace: true });
    } catch (err) {
      alert("Upload error: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="upload-page">
      <ThemeToggle className="auth-theme-toggle" />
      <div className="upload-card">
        <h2>Upload study material</h2>
        <p style={{ marginTop: 0, fontSize: "14px" }}>
          Add a PDF, image, Word, Excel, or text file. The assistant will use it as context in this chat.
        </p>

        {!currentChat ? <p className="error-text">No chat selected.</p> : null}

        <label
          className="drop-zone"
          onDrop={(e) => {
            e.preventDefault();
            if (!uploading) uploadFile(e.dataTransfer.files);
          }}
          onDragOver={(e) => e.preventDefault()}
          style={{
            display: "block",
            cursor: uploading ? "not-allowed" : "pointer",
            opacity: uploading ? 0.6 : 1,
          }}
        >
          <FileUp size={34} style={{ marginBottom: "10px" }} />
          <div>{uploading ? "Uploading..." : "Drop file here or choose one"}</div>
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tiff,.txt,.md,.csv,.docx,.xlsx,.xlsm"
            onChange={(e) => uploadFile(e.target.files)}
            disabled={uploading}
            style={{ display: "none" }}
          />
        </label>

        <button
          className="secondary-button"
          onClick={() => navigate(currentChat ? `/?chatId=${currentChat}` : "/")}
          style={{ width: "100%", marginTop: "14px" }}
        >
          Back to chat
        </button>
      </div>
    </div>
  );
}
