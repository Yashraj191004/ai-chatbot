# AI ChatBot

A full-stack AI-powered chatbot application built with FastAPI and React, featuring user authentication, document uploads, and intelligent conversation capabilities.

## 🎯 Features

- **User Authentication**: Secure login and signup with JWT tokens
- **OAuth Integration**: Google OAuth support for easy authentication
- **Document Upload**: Upload and process documents for AI context
- **Real-time Chat**: Interactive chat interface with AI responses
- **Vector Store**: Semantic search using vector embeddings
- **Dark/Light Theme**: Toggle between dark and light modes
- **Protected Routes**: Secure endpoints with authentication

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI (Python)
- **Database**: SQLite with SQLAlchemy ORM
- **Authentication**: JWT tokens
- **API Key Management**: Resend for email services
- **Vector Store**: AI-powered semantic search

### Frontend
- **Framework**: React 18
- **Build Tool**: Vite
- **Styling**: Tailwind CSS, PostCSS
- **HTTP Client**: Axios
- **State Management**: React Context API

## How the System Works

The assistant is **agentic**: every message goes to a single `/agent` endpoint, where the local Ollama model is given a toolbox and decides itself — in a multi-step loop — which tools to use. There are no keyword commands; asking naturally ("what's on this page?", "find the deadline in my PDF", "open word and write the essay there") is enough.

```text
User message
  |
  v
React frontend --- streams NDJSON events (tool status + answer tokens)
  |
  v
FastAPI /agent endpoint
  |
  v
Agent loop (agent.py) <----> Ollama /api/chat with tool schemas
  |          model returns tool calls until it can answer
  v
Tools (tools.py)
  - web_search            real DuckDuckGo results
  - fetch_webpage         headless Selenium read + save to chat memory
  - read_pdf              download + extract a PDF by URL
  - search_documents      semantic search over uploads/scrapes (FAISS)
  - list_documents
  - open_browser / browser_navigate / read_browser_page / close_browser
                          visible Chrome the user can log into
  - read_quiz_questions / select_quiz_answers (never submits)
  - open_app / type_text / send_keys   Windows desktop control
  - create_file           docx / xlsx / pptx / txt with model-written content
```

Models with native tool support (qwen3, qwen2.5, llama3.1/3.2, mistral, ...) use Ollama's tools API; other models fall back to a JSON tool protocol automatically. Uploaded files and scraped pages are chunked into a per-chat vector memory the agent searches on demand. Recommended models: `qwen3:8b` (default) and `qwen2.5vl:7b` for vision.

## 📋 Prerequisites

- **Node.js** 16+ (for frontend)
- **Python** 3.8+ (for backend)
- **Git** (for version control)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Yashraj191004/ai-chatbot.git
cd ai-chatbot
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (copy from .env.example)
cp .env.example .env

# Update .env with your API keys and secrets
# Required variables:
# - JWT_SECRET: Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
# - GOOGLE_CLIENT_ID: From Google Cloud Console
# - GOOGLE_CLIENT_SECRET: From Google Cloud Console
# - RESEND_API_KEY: From Resend dashboard

# Run the backend server
python -m uvicorn main:app --reload
```

The backend will be available at `http://127.0.0.1:8000`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env file if needed
# Update frontend API endpoints if backend is on different URL

# Run the development server
npm run dev
```

The frontend will be available at `http://127.0.0.1:5173`

## 📁 Project Structure

```
ai-chatbot/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── models.py            # Database models
│   ├── database.py          # Database configuration and setup
│   ├── auth.py              # Authentication logic
│   ├── scraper.py           # Web scraping utilities
│   ├── vector_store.py      # Vector embeddings and semantic search
│   ├── requirements.txt      # Python dependencies
│   ├── .env.example         # Environment variables template
│   └── generated/           # Generated files and cache
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main app component
│   │   ├── main.jsx         # React entry point
│   │   ├── api.js           # API client configuration
│   │   ├── ProtectedRoute.jsx # Route protection component
│   │   ├── components/
│   │   │   ├── ChatWindow.jsx    # Chat display component
│   │   │   ├── InputBar.jsx      # Chat input component
│   │   │   ├── Message.jsx       # Message display component
│   │   │   ├── Sidebar.jsx       # Sidebar navigation
│   │   │   └── ThemeToggle.jsx   # Theme toggle component
│   │   └── pages/
│   │       ├── Login.jsx         # Login page
│   │       ├── Signup.jsx        # Signup page
│   │       └── Upload.jsx        # Document upload page
│   │
│   ├── index.html           # HTML template
│   ├── package.json         # Node dependencies
│   ├── tailwind.config.js   # Tailwind CSS configuration
│   └── postcss.config.js    # PostCSS configuration
│
├── .gitignore              # Git ignore rules
└── README.md               # This file
```

## 🔐 Environment Variables

### Backend (.env)

```
# URLs
FRONTEND_URL=http://127.0.0.1:5173
BACKEND_PUBLIC_URL=http://127.0.0.1:8000

# JWT Configuration
JWT_SECRET=your-long-random-secret-key
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=60
JWT_REFRESH_EXPIRE_DAYS=7

# Email Service (Resend)
RESEND_API_KEY=your-resend-api-key
EMAIL_FROM=Study Assistant <onboarding@resend.dev>

# OAuth (Google)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

## 📚 API Endpoints

### Authentication
- `POST /api/auth/signup` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `POST /api/auth/refresh` - Refresh access token

### Chat
- `GET /api/chat/messages` - Get chat history
- `POST /api/chat/message` - Send a message
- `DELETE /api/chat/messages/{id}` - Delete a message

### Documents
- `POST /api/documents/upload` - Upload document
- `GET /api/documents` - List user documents
- `DELETE /api/documents/{id}` - Delete document

## 🔄 Development Workflow

1. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit:
   ```bash
   git add .
   git commit -m "Add your feature description"
   ```

3. Push to GitHub:
   ```bash
   git push origin feature/your-feature-name
   ```

4. Create a Pull Request on GitHub

## 🐛 Troubleshooting

### Backend issues
- **Port 8000 already in use**: Change port with `--port 8001`
- **Module not found**: Ensure virtual environment is activated and dependencies installed
- **Database errors**: Delete `app.db` and restart (fresh database)

### Frontend issues
- **Port 5173 already in use**: Change port in `vite.config.js`
- **API connection failed**: Verify `VITE_API_URL` matches backend URL
- **Blank page**: Check browser console for errors

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

## 👤 Author

**Yashraj191004**

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Contact

For questions or suggestions, please open an issue on GitHub.

---

Happy coding! 🚀
