# AI Voice Agent - Quick Start Guide

## 🚀 Quick Start

### Option 1: One-Click Install & Run (Windows)
Double-click `install_and_run.bat` to automatically install dependencies and start the server.

### Option 2: Manual Installation
```bash
# Install dependencies
pip install fastapi uvicorn groq python-dotenv aiofiles pydantic requests libsql-experimental==0.0.54

# Start the server
python main.py
```

### Option 3: Production
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?name=willow-ai-project&type=docker&image=ghcr.io%2Fgreeenboi%2Fwillow-ai-project%3Alatest&instance_type=free&regions=was&instances_min=0&autoscaling_sleep_idle_delay=300&env%5BGROQ_API_KEY%5D=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&env%5BTURSO_DATABASE_URL%5D=libsql%3A%2F%2Fwillow-ai-project-greeenboi.aws-ap-south-1.turso.io&env%5BTURSO_AUTH_TOKEN%5D=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NDg4ODg4NjAsImlkIjoiYTMwYzYyNDItYTAxYi00ZWRiLTk0NjktZjBjMzg3ODc1YzhhIiwicmlkIjoiZDhjYTY5YjEtYTQyZC00Mzk1LTgzZjktZWRlYzI2ZTIwZmI4In0.Um0VQSfKjRNOR2-7kbCGIElkL40GDhI0lcUavVgbqFaC3hlr41RF-ZP7vrABbaAOPnY3CwdEDT_bTbB4djHbAA&env%5BVERCEL_DOMAIN%5D=https%3A%2F%2Fwillow-project.vercel.app%2F&env%5BALLOW_ALL_ORIGINS%5D=true&env%5BPRODUCTION_DOMAIN%5D=https%3A%2F%2Fwillow-project.vercel.app%2F&env%5BPORT%5D=8000&hc_protocol%5B8000%5D=http&hc_path%5B8000%5D=%2Fhealth)

## 🌐 Access the Application

Once running, the AI voice agent will be available at:
- **Backend API**: http://localhost:8000
- **Frontend UI**: http://localhost:8000 (React app served by FastAPI)
- **API Documentation**: http://localhost:8000/docs

## 🔑 Environment Variables

The following environment variables are already configured in `.env`:
- `GROQ_API_KEY`: For Groq AI STT/TTS services
- `TURSO_DATABASE_URL`: Cloud database URL
- `TURSO_AUTH_TOKEN`: Database authentication token

## 📱 How to Use

1. **Start a session**: Open http://localhost:8000 in your browser
2. **Voice interaction**: Click the microphone button to speak
3. **Text interaction**: Type messages in the chat interface
4. **Lead qualification**: The AI will ask for:
   - Company name
   - Domain/Industry
   - Problem statement
   - Budget information
5. **Media display**: Images/videos will appear based on conversation context
6. **Session management**: All interactions are saved to the cloud database

## 🔧 API Endpoints

- `POST /api/chat/text` - Text-based conversation
- `POST /api/chat/audio` - Audio-based conversation (STT/TTS)
- `GET /api/sessions` - List all sessions
- `GET /api/session/{session_id}/summary` - Get session summary
- `POST /api/session/{session_id}/start` - Start a new session
- `POST /api/session/{session_id}/close` - Close a session

## 🎯 Features

✅ **Real-time voice interaction** with Groq AI Whisper (STT) and PlayAI (TTS)  
✅ **Lead qualification workflow** with structured data collection  
✅ **Dynamic media display** based on conversation context  
✅ **Session persistence** with Turso cloud database  
✅ **Comprehensive logging** of all interactions  
✅ **React frontend** with shadcn UI components  
✅ **FastAPI backend** with automatic API documentation  
✅ **Multi-session support** with unique session IDs  

## 🛠️ Technology Stack

- **Frontend**: React + Vite + shadcn UI
- **Backend**: FastAPI + Python
- **Database**: Turso (libSQL) - Cloud database
- **AI Services**: Groq AI (Whisper STT + PlayAI TTS)
- **Audio Processing**: Web Audio API + aiofiles

## 📊 Database Schema

The application uses three main tables:
- `sessions` - Session information and lead data
- `chat_history` - All conversation messages
- `media_interactions` - Logged media display events

All data is automatically synchronized with the cloud database for persistence and analytics.
