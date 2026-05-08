import { Routes, Route, useLocation } from "react-router-dom";
import { useState, useEffect } from "react";

import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Upload from "./pages/Upload";
import ProtectedRoute from "./ProtectedRoute";


// 🔒 Protected App (your current UI)
function ChatApp() {
  const location = useLocation();
  const [currentChat, setCurrentChat] = useState(null);

  // If navigated back from upload with a chatId (state or query), select it and clean the URL
  useEffect(() => {
    const stateCid = location.state?.chatId;
    const params = new URLSearchParams(location.search);
    const searchCid = params.get("chatId");
    const cid = stateCid ?? searchCid;

    if (cid) {
      setCurrentChat(cid);
      try {
        // remove state/search from history to keep URL clean
        window.history.replaceState({}, document.title, "/");
      } catch (e) {}
    }
  }, [location.search, location.state]);

  return (
    <div className="app-shell">
      <Sidebar currentChat={currentChat} setCurrentChat={setCurrentChat} />

      <div className="chat-pane">
        <ChatWindow currentChat={currentChat} setCurrentChat={setCurrentChat} />
      </div>
    </div>
  );
}

// 🚀 MAIN APP WITH ROUTES
export default function App() {
  return (
    <Routes>

        {/* Default → Chat */}
        <Route 
          path="/" 
          element={
            <ProtectedRoute>
              <ChatApp />
            </ProtectedRoute>
          } 
        />

        {/* Auth Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route
          path="/upload"
          element={
            <ProtectedRoute>
              <Upload />
            </ProtectedRoute>
          }
        />

    </Routes>
  );
}
