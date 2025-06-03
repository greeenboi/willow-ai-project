@echo off
echo 🚀 Building AI Voice Agent Backend...

echo 📦 Building Docker image...
docker build -t ai-voice-agent-backend .

echo ✅ Docker image built successfully!

echo 🔧 To run the container locally:
echo docker run -p 8000:8000 --env-file .env ai-voice-agent-backend

echo 🌐 To run with docker-compose:
echo docker-compose up -d

echo 📋 Environment variables needed:
echo - GROQ_API_KEY
echo - TURSO_DATABASE_URL  
echo - TURSO_AUTH_TOKEN
echo - VERCEL_DOMAIN (optional, for Vercel frontend)
echo - ALLOW_ALL_ORIGINS=true (for development)

echo ✨ Backend ready for deployment!
