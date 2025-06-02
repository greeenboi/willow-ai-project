import os
import json
import base64
import uuid
import re
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal

import aiofiles
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq, AsyncGroq
from dotenv import load_dotenv
import uvicorn
import asyncio

from database import DatabaseManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware for React development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the React client
app.mount("/static", StaticFiles(directory="static"), name="static")
# Mount the React client files
app.mount("/client", StaticFiles(directory="static/client"), name="client")


groq_api_key = os.getenv("GROQ_API_KEY")

try:
    client = Groq(api_key=groq_api_key)
except Exception as e:
    print(f"Error initializing Groq client: {e}")
    # Initialize with minimal config
    client = Groq(api_key=groq_api_key or "dummy")

# Configure directories
AUDIO_DIR = Path("static/audio")
AUDIO_DIR.mkdir(exist_ok=True, parents=True)
TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Initialize database manager
db_manager = DatabaseManager()
logger.info("Database manager initialized")

# Define message models for chat completion
class MessageRole(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

# Request/Response models for HTTP API
class TextMessageRequest(BaseModel):
    session_id: str
    message: str

class AudioMessageRequest(BaseModel):
    session_id: str
    audio_data: str  # base64 encoded audio

class AgentResponse(BaseModel):
    type: str
    text: str
    audio: str = None
    transcript: str = None
    media: dict = None
    lead_info: dict = None

# Voice agent context
class ConversationState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.lead_info = {
            "company_name": None,
            "domain": None,
            "problem": None,
            "budget": None,
        }
        self.conversation_history = []
        self.current_stage = "greeting"
        self.media_to_display = None
        
        # Create session in database
        db_manager.create_session(session_id, self.lead_info)

    def update_lead_info(self, key, value):
        if key in self.lead_info:
            self.lead_info[key] = value
            # Update database
            db_manager.update_session(self.session_id, self.lead_info, self.current_stage)
            return True
        return False

    def add_to_history(self, speaker, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_entry = {"timestamp": timestamp, "speaker": speaker, "message": message}
        self.conversation_history.append(history_entry)
        
        # Add to database
        db_manager.add_message(self.session_id, speaker, message)

    def get_summary(self):
        filled_info = {k: v for k, v in self.lead_info.items() if v}
        missing_info = [k for k, v in self.lead_info.items() if not v]
        return {
            "collected_info": filled_info,
            "missing_info": missing_info,
            "conversation_length": len(self.conversation_history)
        }

    def save_transcript(self, session_id):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{TRANSCRIPTS_DIR}/{session_id}_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump({
                "lead_info": self.lead_info,
                "conversation": self.conversation_history,
                "summary": self.get_summary()
            }, f, indent=2)
        return filename
    
    def load_from_database(self):
        """Load existing session data from database."""
        session_data = db_manager.get_session(self.session_id)
        if session_data:
            self.lead_info = session_data.get("lead_info", self.lead_info)
            self.current_stage = session_data.get("current_stage", "greeting")
            
            # Load chat history
            chat_history = db_manager.get_chat_history(self.session_id)
            self.conversation_history = [
                {
                    "timestamp": msg["timestamp"],
                    "speaker": msg["speaker"], 
                    "message": msg["message"]
                }
                for msg in chat_history
            ]
            
            logger.info(f"Loaded session {self.session_id} from database with {len(self.conversation_history)} messages")
            return True
        return False


# Active connections and their states
active_connections: Dict[str, ConversationState] = {}

# System prompt template for the AI agent
SYSTEM_PROMPT = """
You are Jane, an AI Sales Development Representative (SDR) and a warm, friendly, and highly empathetic customer relations specialist. Your core mission is to identify and qualify high-potential leads for the sales team by collecting key information: Company name, Domain/Industry, Problem they're trying to solve, and Budget range.

Your Communication & Relationship Building Guidelines:
- Keep your responses concise and natural. Speak as a helpful, friendly, and approachable sales representative would.
- Briefly introduce yourself with a warm, friendly tone when starting a conversation, aiming to build immediate rapport.
- Actively listen to understand the user's needs and emotions. Gently guide the conversation toward collecting the required information, making them feel heard and understood throughout.
- Your approach should feel like a genuine conversation, not an interrogation.
- Answer product questions generally, focusing on how our solutions can address their specific pain points.
- Always steer the focus back to understanding their situation and qualifying the lead, connecting the product to their unique challenges.
- Cultivate a safe, non-pressuring, and trustworthy environment. Make the user feel comfortable sharing information, ensuring they perceive you as a helpful resource rather than just a salesperson.
- End the conversation politely and respectfully once you have all the necessary information, or if the user indicates they want to end. Always leave them with a positive impression.

Media Suggestion & JSON Command:
If the user mentions keywords related to product demos, pricing, or features, suggest showing relevant media that can provide clarity and build their understanding. When suggesting media, include a JSON command in your response: {"show_media": "demo", "topic": "feature_name"} (replace "demo" with the relevant media type and "feature_name" with the specific topic). Available media topics: demo, pricing, features, testimonials.

Your Core SDR Responsibilities (Internal Focus):
- Conduct thorough, insightful prospecting to identify target companies and decision-makers who would genuinely benefit from our solutions.
- Initiate personalized, relationship-focused outreach, always striving to connect on a human level.
- Expertly qualify leads using a consultative approach, focusing on understanding their unique challenges and ensuring a mutual fit.
- Your primary goal is to schedule qualified, mutually beneficial meetings or demos for Account Executives.
- Maintain accurate records of each conversation, reflecting the nuances and building lasting positive first impressions.
- Prioritize efficiency, professionalism, and genuine care for the prospect's success.

Remember: You are Jane - be personable, empathetic, and genuinely interested in helping prospects find solutions to their challenges.
"""

# Function to transcribe audio using Groq
def transcribe_audio(audio_file_path):
    """Transcribe audio file using Groq Whisper model."""
    try:
        logger.info(f"Starting audio transcription for file: {audio_file_path}")
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            logger.error("GROQ_API_KEY not found in environment variables")
            return None

        # Use synchronous client for transcription
        sync_client = Groq(api_key=groq_api_key)
        
        with open(audio_file_path, "rb") as file:
            transcription = sync_client.audio.transcriptions.create(
                file=(audio_file_path, file.read()),
                model="whisper-large-v3",
                response_format="text",
                language="en",
                temperature=0.0
            )
        
        # Extract text from response
        if hasattr(transcription, 'text'):
            transcript_text = transcription.text
        else:
            transcript_text = str(transcription)
        
        logger.info(f"Transcription successful: {transcript_text[:100]}...")
        
        # Clean up the audio file
        try:
            os.remove(audio_file_path)
        except Exception as e:
            logger.warning(f"Failed to remove audio file {audio_file_path}: {str(e)}")
        
        return transcript_text
    except Exception as e:
        logger.error(f"Error transcribing audio {audio_file_path}: {str(e)}")
        # Try to clean up the file even if transcription failed
        try:
            os.remove(audio_file_path)
        except:
            pass
        return None

# Function to get AI response
async def get_ai_response(conversation_state, user_input):
    """Get AI response from Groq LLM."""
    try:
        logger.info(f"Getting AI response for input: {user_input[:50]}...")
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            logger.error("GROQ_API_KEY not found in environment variables")
            return "I'm sorry, I'm having trouble connecting to my AI service. Please try again later."

        # Create async client within the function
        async_client = AsyncGroq(api_key=groq_api_key)
        
        # Create properly typed messages for the chat completion
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Add conversation history
        for entry in conversation_state.conversation_history[-10:]:  # Include last 10 messages for context
            role = "assistant" if entry["speaker"] == "agent" else "user"
            messages.append({"role": role, "content": entry["message"]})

        # Add current user input
        messages.append({"role": "user", "content": user_input})

        # Get response from Groq
        chat_completion = await async_client.chat.completions.create(
            messages=messages,
            model="llama3-70b-8192",
            temperature=0.7,
            max_tokens=200,
            top_p=0.9
        )

        response_text = chat_completion.choices[0].message.content
        logger.info(f"AI response generated: {response_text[:100]}...")

        # Check for media commands in the response
        if '{"show_media":' in response_text:
            try:
                # Extract JSON command
                start_idx = response_text.find('{"show_media":')
                end_idx = response_text.find('}', start_idx) + 1
                media_command = json.loads(response_text[start_idx:end_idx])                # Set media to display
                conversation_state.media_to_display = {
                    "type": media_command.get("show_media", "demo"),
                    "topic": media_command.get("topic", "general")
                }

                # Remove JSON command from response
                response_text = response_text[:start_idx].strip() + " " + response_text[end_idx:].strip()
                logger.info(f"Media command extracted: {media_command}")
            except Exception as e:
                logger.warning(f"Failed to parse media command: {str(e)}")

        # Update lead info based on AI response
        update_lead_info_from_conversation(conversation_state, user_input, response_text)

        return response_text
    except Exception as e:
        logger.error(f"AI response error: {str(e)}")
        return "I'm sorry, I'm having trouble processing that. Could you please repeat?"

# Function to update lead info based on conversation
def update_lead_info_from_conversation(state, user_input, ai_response):
    # Simple keyword extraction for demo purposes
    # Normally you'd use NER or a more sophisticated extraction method

    user_text = user_input.lower()

    # Company name detection
    if state.lead_info["company_name"] is None:
        company_indicators = ["company", "work for", "work at", "called", "named"]
        if any(indicator in user_text for indicator in company_indicators):
            words = user_text.split()
            # Very simple extraction - would need to be more sophisticated in production
            for i, word in enumerate(words):
                if word in company_indicators and i+1 < len(words):
                    state.update_lead_info("company_name", words[i+1].title())
                    break

    # Domain detection
    if state.lead_info["domain"] is None:
        domains = ["tech", "healthcare", "finance", "education", "retail", "manufacturing",
                  "software", "insurance", "banking", "marketing"]
        for domain in domains:
            if domain in user_text:
                state.update_lead_info("domain", domain.title())
                break

    # Problem detection
    if state.lead_info["problem"] is None and ("problem" in user_text or "challenge" in user_text or "issue" in user_text):
        # Extract sentence containing "problem"
        sentences = user_text.split('.')
        for sentence in sentences:
            if "problem" in sentence or "challenge" in sentence or "issue" in sentence:
                state.update_lead_info("problem", sentence.strip())
                break

    # Budget detection
    if state.lead_info["budget"] is None:
        budget_indicators = ["budget", "spend", "cost", "price", "pricing", "$", "dollar"]
        if any(indicator in user_text for indicator in budget_indicators):
            # Look for numbers near budget indicators
            import re
            numbers = re.findall(r'\$?\d+[k,m]?|\d+\s?thousand|\d+\s?million', user_text)            
            if numbers:
                state.update_lead_info("budget", numbers[0])

# Function to convert text to speech using Groq
def text_to_speech(text):
    """Convert text to speech using Groq PlayAI model via HTTP API."""
    try:
        logger.info(f"Starting TTS for text: {text[:50]}...")
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            logger.error("GROQ_API_KEY not found in environment variables")
            return None

        # Make HTTP request to Groq TTS API
        url = "https://api.groq.com/openai/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "playai-tts",
            "input": text,
            "voice": "Cheyenne-PlayAI",
            "response_format": "wav"
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            # Convert response content to base64
            audio_content = response.content
            audio_base64 = base64.b64encode(audio_content).decode('utf-8')
            
            logger.info(f"TTS successful, generated {len(audio_base64)} characters of base64 audio")
            return audio_base64
        else:
            logger.error(f"TTS API request failed with status {response.status_code}: {response.text}")
            return None
        
    except Exception as e:
        logger.error(f"Error in text-to-speech conversion: {str(e)}")
        return None

# Routes and HTTP handlers
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return FileResponse("static/client/index.html")

@app.post("/api/chat/text")
async def process_text_message(request: TextMessageRequest):
    """Process text message and return AI response with streaming"""
    try:
        session_id = request.session_id
        user_message = request.message
        
        logger.info(f"Processing text message from {session_id}: {user_message}")
        
        # Initialize conversation state if not exists
        if session_id not in active_connections:
            active_connections[session_id] = ConversationState(session_id)
            # Try to load existing session data
            active_connections[session_id].load_from_database()
        
        conv_state = active_connections[session_id]
        conv_state.add_to_history("user", user_message)
        
        # Get AI response
        ai_response = await get_ai_response(conv_state, user_message)
        conv_state.add_to_history("agent", ai_response)
          # Convert to speech
        speech_audio = await asyncio.get_event_loop().run_in_executor(
            None, text_to_speech, ai_response
        )
        
        # Prepare response
        response_data = {
            "type": "agent_response",
            "text": ai_response,
            "audio": speech_audio,
            "lead_info": conv_state.lead_info
        }
        
        # Add media if any was triggered
        if conv_state.media_to_display:
            response_data["media"] = conv_state.media_to_display
            # Log media interaction to database
            db_manager.log_media_interaction(
                session_id, 
                conv_state.media_to_display["type"], 
                conv_state.media_to_display["topic"]
            )
            conv_state.media_to_display = None
        
        logger.info(f"Sent text response to {session_id}")
        return JSONResponse(content=response_data)
        
    except Exception as e:
        logger.error(f"Error processing text message: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"type": "error", "message": "Failed to process your message"}
        )

@app.post("/api/chat/audio")
async def process_audio_message(session_id: str = Form(...), audio_file: UploadFile = File(...)):
    """Process audio message and return AI response"""
    try:
        logger.info(f"Processing audio message from {session_id}")
        
        # Initialize conversation state if not exists
        if session_id not in active_connections:
            active_connections[session_id] = ConversationState(session_id)
            # Try to load existing session data
            active_connections[session_id].load_from_database()
        
        conv_state = active_connections[session_id]
        
        # Save uploaded audio file
        audio_filename = f"{AUDIO_DIR}/{session_id}_{uuid.uuid4()}.wav"
        
        # Read and save audio content
        audio_content = await audio_file.read()
        async with aiofiles.open(audio_filename, 'wb') as f:
            await f.write(audio_content)        # Transcribe audio
        transcript = await asyncio.get_event_loop().run_in_executor(
            None, transcribe_audio, audio_filename
        )
        if transcript:
            logger.info(f"Audio transcribed from {session_id}: {transcript}")
            conv_state.add_to_history("user", transcript)
              # Get AI response
            ai_response = await get_ai_response(conv_state, transcript)
            conv_state.add_to_history("agent", ai_response)
            
            # Convert to speech
            speech_audio = await asyncio.get_event_loop().run_in_executor(
                None, text_to_speech, ai_response
            )
              # Prepare response
            response_data = {
                "type": "agent_response",
                "text": ai_response,
                "transcript": transcript,
                "audio": speech_audio,
                "lead_info": conv_state.lead_info
            }
            
            # Add media if any was triggered
            if conv_state.media_to_display:
                response_data["media"] = conv_state.media_to_display
                # Log media interaction to database
                db_manager.log_media_interaction(
                    session_id, 
                    conv_state.media_to_display["type"], 
                    conv_state.media_to_display["topic"]
                )
                conv_state.media_to_display = None
            
            logger.info(f"Sent audio response to {session_id}")
            return JSONResponse(content=response_data)
        else:
            logger.error(f"Failed to transcribe audio from {session_id}")
            return JSONResponse(
                status_code=400,
                content={"type": "error", "message": "Failed to transcribe audio"}
            )
            
    except Exception as e:
        logger.error(f"Error processing audio message: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"type": "error", "message": "Failed to process audio message"}
        )

@app.get("/api/session/{session_id}/start")
async def start_session(session_id: str):
    """Start a new session and return initial greeting"""
    try:
        logger.info(f"Starting new session: {session_id}")
        
        # Initialize conversation state
        if session_id not in active_connections:
            active_connections[session_id] = ConversationState(session_id)
            # Try to load existing session data
            active_connections[session_id].load_from_database()
        
        conv_state = active_connections[session_id]
        
        # Send initial greeting
        initial_greeting = "Hi there! I'm Jane, an AI Sales Development Representative. I'd like to learn more about your company and how we might be able to help you. Could you tell me the name of your company?"
        conv_state.add_to_history("agent", initial_greeting)
        
        # Generate greeting audio
        greeting_audio = await asyncio.get_event_loop().run_in_executor(
            None, text_to_speech, initial_greeting
        )
        
        response_data = {
            "type": "agent_response",
            "text": initial_greeting,
            "audio": greeting_audio,
            "lead_info": conv_state.lead_info
        }
        
        logger.info(f"Session started for {session_id}")
        return JSONResponse(content=response_data)
        
    except Exception as e:
        logger.error(f"Error starting session {session_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"type": "error", "message": "Failed to start session"}
        )

@app.get("/summary/{session_id}")
async def get_summary(session_id: str):
    if session_id in active_connections:
        return JSONResponse(content=active_connections[session_id].get_summary())
    raise HTTPException(status_code=404, detail="Session not found")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "AI Voice Agent API is running"}

@app.get("/api/test")
async def test_endpoint():
    return {"message": "Backend is working!", "timestamp": datetime.now().isoformat()}

@app.get("/api/sessions")
async def get_all_sessions():
    """Get all sessions with basic information"""
    try:
        sessions = db_manager.get_all_sessions()
        return JSONResponse(content={"sessions": sessions})
    except Exception as e:
        logger.error(f"Error retrieving sessions: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve sessions"}
        )

@app.get("/api/session/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Get comprehensive summary of a session"""
    try:
        summary = db_manager.get_session_summary(session_id)
        if summary:
            return JSONResponse(content=summary)
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found"}
            )
    except Exception as e:
        logger.error(f"Error retrieving session summary for {session_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve session summary"}
        )

@app.post("/api/session/{session_id}/close")
async def close_session(session_id: str):
    """Close a session"""
    try:
        success = db_manager.close_session(session_id)
        if success:
            # Remove from active connections if present
            if session_id in active_connections:
                del active_connections[session_id]
            return JSONResponse(content={"message": "Session closed successfully"})
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found"}
            )
    except Exception as e:
        logger.error(f"Error closing session {session_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to close session"}
        )

@app.get("/api/session/{session_id}/history")
async def get_session_history(session_id: str, limit: int = 50):
    """Get chat history for a session"""
    try:
        history = db_manager.get_chat_history(session_id, limit)
        return JSONResponse(content={"history": history})
    except Exception as e:
        logger.error(f"Error retrieving history for {session_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve session history"}
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
