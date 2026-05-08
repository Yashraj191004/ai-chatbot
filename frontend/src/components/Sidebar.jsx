import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { LogOut, MessageSquare, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Trash } from "lucide-react";
import { createChat, deleteChat, getChats, renameChat } from "../api";
import ThemeToggle from "./ThemeToggle";

export default function Sidebar({ currentChat, setCurrentChat }) {
  const [chats, setChats] = useState([]);
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar") === "closed");

  const loadChats = async () => {
    const data = await getChats();
    if (!Array.isArray(data)) {
      setChats([]);
      return;
    }
    if (!currentChat && data.length === 0) {
      const chat = await createChat();
      if (!chat?.error) {
        setChats([chat]);
        setCurrentChat(chat.id);
      }
      return;
    }
    setChats(data);
    if (!currentChat && data.length > 0) setCurrentChat(data[0].id);
  };

  useEffect(() => {
    loadChats();
  }, []);

  useEffect(() => {
    const refresh = () => loadChats();
    window.addEventListener("chats-updated", refresh);
    return () => window.removeEventListener("chats-updated", refresh);
  }, [currentChat]);

  useEffect(() => {
    localStorage.setItem("sidebar", collapsed ? "closed" : "open");
  }, [collapsed]);

  const handleNewChat = async () => {
    const chat = await createChat();
    if (!chat || chat.error) return;
    setChats((prev) => [chat, ...prev]);
    setCurrentChat(chat.id);
  };

  const handleRename = async (chat) => {
    const newTitle = prompt("Rename chat:", chat.title || "New Chat");
    if (!newTitle?.trim()) return;

    await renameChat(chat.id, newTitle.trim());
    setChats((prev) =>
      prev.map((c) => (c.id === chat.id ? { ...c, title: newTitle.trim() } : c))
    );
  };

  const handleDelete = async (chat) => {
    if (!confirm("Delete this chat?")) return;

    await deleteChat(chat.id);
    const remaining = chats.filter((c) => c.id !== chat.id);
    setChats(remaining);
    if (currentChat === chat.id) setCurrentChat(remaining[0]?.id || null);
  };

  const filteredChats = chats.filter((c) =>
    (c.title || "New Chat").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-top">
        <button
          className="icon-button sidebar-toggle"
          onClick={() => setCollapsed((value) => !value)}
          title={collapsed ? "Open sidebar" : "Close sidebar"}
          aria-label={collapsed ? "Open sidebar" : "Close sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>

        <motion.button
          whileHover={{ scale: 1.02 }}
          onClick={handleNewChat}
          className={collapsed ? "icon-button sidebar-new-icon" : "primary-button sidebar-new-button"}
          title="New chat"
          aria-label="New chat"
        >
          <Plus size={17} />
          {!collapsed ? <span>New chat</span> : null}
        </motion.button>
      </div>

      {!collapsed ? (
        <>
          <div className="brand-block">
            <h2 className="brand-title">Study Assistant</h2>
            <p className="brand-subtitle">Chats and study context</p>
          </div>

          <input
            className="search-input"
            placeholder="Search chats"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </>
      ) : null}

      <div className="chat-list">
        {filteredChats.map((chat) => (
          <motion.div
            key={chat.id}
            whileHover={{ x: 2 }}
            onClick={() => setCurrentChat(chat.id)}
            className={`chat-list-item ${currentChat === chat.id ? "active" : ""} ${collapsed ? "compact" : ""}`}
            title={chat.title || "New Chat"}
          >
            {collapsed ? (
              <MessageSquare size={17} />
            ) : (
              <>
                <span className="chat-title">{chat.title || "New Chat"}</span>
                <span className="chat-actions">
                  <button
                    className="icon-button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRename(chat);
                    }}
                    title="Rename"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    className="icon-button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(chat);
                    }}
                    title="Delete"
                  >
                    <Trash size={14} />
                  </button>
                </span>
              </>
            )}
          </motion.div>
        ))}
      </div>

      <div className="sidebar-footer">
        <ThemeToggle />
        <button
          className={collapsed ? "icon-button sidebar-logout-icon" : "danger-button"}
          onClick={() => {
            localStorage.removeItem("token");
            localStorage.removeItem("refresh_token");
            window.location.href = "/login";
          }}
          title="Logout"
          aria-label="Logout"
        >
          <LogOut size={16} />
          {!collapsed ? <span>Logout</span> : null}
        </button>
      </div>
    </aside>
  );
}
