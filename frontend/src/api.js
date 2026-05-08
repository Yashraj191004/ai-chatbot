export const API = "http://127.0.0.1:8000";

export const getToken = () => localStorage.getItem("token");

const authHeaders = () => ({
  Authorization: `Bearer ${getToken()}`,
});

const handleAuthError = (res) => {
  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
    return true;
  }
  return false;
};

export const createChat = async () => {
  const res = await fetch(`${API}/chat/create`, {
    method: "POST",
    headers: authHeaders()
  });
  if (handleAuthError(res)) return { error: "unauthorized" };
  return res.json();
};

export const getChats = async () => {
  const res = await fetch(`${API}/chats`, {
    headers: authHeaders()
  });
  if (handleAuthError(res)) return [];
  return res.json();
};

export const getModelStatus = async () => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  try {
    const res = await fetch(`${API}/models/status`, {
      headers: authHeaders(),
      signal: controller.signal,
    });
    if (handleAuthError(res)) return null;
    return res.json();
  } catch (err) {
    return {
      ollama: "offline",
      default: null,
      models: {},
      error: err.name === "AbortError" ? "Backend timed out" : "Backend offline",
    };
  } finally {
    clearTimeout(timeout);
  }
};

export const renameChat = async (chatId, title) => {
  const res = await fetch(`${API}/chat/${chatId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ title }),
  });
  if (handleAuthError(res)) return { error: "unauthorized" };
  return res.json();
};

export const deleteChat = async (chatId) => {
  const res = await fetch(`${API}/chat/${chatId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (handleAuthError(res)) return { error: "unauthorized" };
  return res.json();
};

export const uploadFileToChat = async (chatId, file, signal, model) => {
  const formData = new FormData();
  formData.append("file", file);
  if (model) formData.append("model", model);

  const res = await fetch(`${API}/upload/${chatId}`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
    signal,
  });
  if (handleAuthError(res)) return { error: "unauthorized" };
  return res.json();
};

export const scrapeAssignmentPage = async (chatId, url, signal, options = {}) => {
  const res = await fetch(`${API}/scrape/${chatId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      url,
      headless: !options.manualLogin,
      wait_seconds: 2,
      include_pdfs: true,
      manual_login: Boolean(options.manualLogin),
      login_wait_seconds: options.loginWaitSeconds || 90,
    }),
    signal,
  });
  if (handleAuthError(res)) return { error: "unauthorized" };
  return res.json();
};

export const runAssistantAction = async (chatId, message, signal) => {
  const res = await fetch(`${API}/action`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ chat_id: chatId, message }),
    signal,
  });
  if (handleAuthError(res)) return { error: "unauthorized" };
  return res.json();
};

export const pinChat = async (chatId) => {
  return { msg: "pin not supported by backend" };
};
