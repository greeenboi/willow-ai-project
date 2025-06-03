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
app = FastAPI(title="AI Voice Agent", description="SDR AI Voice Agent API", version="1.0.0")

# Configure CORS for both development and production
allowed_origins = [
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:5173",  # Local dev
    "https://localhost:5173",  # HTTPS dev
]

# Add production domains if environment variables are set
production_domain = os.getenv("PRODUCTION_DOMAIN")
if production_domain:
    allowed_origins.extend([
        f"https://{production_domain}",
        f"http://{production_domain}",
    ])

# Add Vercel domains (they use *.vercel.app pattern)
vercel_domain = os.getenv("VERCEL_DOMAIN")
if vercel_domain:
    allowed_origins.extend([
        f"https://{vercel_domain}",
        f"https://{vercel_domain}.vercel.app",
    ])

# For development, allow all origins if specified
if os.getenv("ALLOW_ALL_ORIGINS") == "true":
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# # Mount static files (backend only - for agent image and media)
app.mount("/static", StaticFiles(directory="static"), name="static")
# # Mount the React client files
# app.mount("/client", StaticFiles(directory="static/client"), name="client")


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
                logger.warning(f"Failed to parse media command: {str(e)}")        # Update lead info based on AI response
        update_lead_info_from_conversation(conversation_state, user_input, response_text)
        
        # Try AI extraction as fallback if pattern matching didn't find everything
        await extract_lead_info_with_ai(conversation_state, user_input)

        return response_text
    except Exception as e:
        logger.error(f"AI response error: {str(e)}")
        return "I'm sorry, I'm having trouble processing that. Could you please repeat?"

# Function to update lead info based on conversation
def update_lead_info_from_conversation(state, user_input, ai_response):
    """Enhanced lead information extraction using AI-powered analysis."""
    user_text = user_input.lower()
    original_text = user_input  # Keep original case for proper names
    
    # Company name detection with improved patterns
    if state.lead_info["company_name"] is None:
        company_patterns = [
            r"(?:work (?:for|at)|company (?:is|called|named)|at (?:a )?company called|employed (?:by|at)) ([A-Za-z][A-Za-z0-9\s&.-]{1,30})",
            r"(?:i'm from|we're|company:?) ([A-Z][A-Za-z0-9\s&.-]{1,30})",
            r"(?:my company|our company) (?:is )?([A-Z][A-Za-z0-9\s&.-]{1,30})",
            r"([A-Z][A-Za-z0-9&.-]{2,20})(?: (?:inc|corp|llc|ltd|company|technologies|tech|solutions|systems))",
        ]
        
        for pattern in company_patterns:
            matches = re.findall(pattern, original_text, re.IGNORECASE)
            if matches:
                company_name = matches[0].strip()
                # Filter out common false positives
                false_positives = ["google", "linkedin", "facebook", "microsoft", "amazon", "apple", "the company", "my company", "our company"]
                if company_name.lower() not in false_positives and len(company_name) > 2:
                    state.update_lead_info("company_name", company_name.title())
                    logger.info(f"Extracted company name: {company_name}")
                    break

    # Enhanced domain/industry detection
    if state.lead_info["domain"] is None:
        # Industry keywords with context
        industry_keywords = {
            "technology": ["tech", "software", "saas", "platform", "development", "programming", "coding", "app", "mobile", "web", "digital", "it", "information technology"],
            "healthcare": ["healthcare", "medical", "hospital", "clinic", "pharmaceutical", "pharma", "biotech", "health", "medicine", "patient", "doctor"],
            "finance": ["finance", "financial", "banking", "bank", "investment", "insurance", "trading", "accounting", "fintech"],
            "education": ["education", "school", "university", "college", "learning", "training", "academic", "student", "teacher", "curriculum"],
            "retail": ["retail", "ecommerce", "e-commerce", "store", "shopping", "consumer", "merchandise", "sales"],
            "manufacturing": ["manufacturing", "factory", "production", "industrial", "automotive", "aerospace", "machinery"],
            "marketing": ["marketing", "advertising", "branding", "agency", "digital marketing", "social media", "content"],
            "consulting": ["consulting", "advisory", "professional services", "consulting firm"],
            "real estate": ["real estate", "property", "housing", "construction", "development"],
            "logistics": ["logistics", "shipping", "transportation", "supply chain", "delivery", "warehouse"],
            "energy": ["energy", "utilities", "power", "renewable", "oil", "gas", "solar", "wind"],
            "government": ["government", "public sector", "municipal", "federal", "state", "agency"]
        }
        
        # Score each industry based on keyword matches
        industry_scores = {}
        for industry, keywords in industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in user_text)
            if score > 0:
                industry_scores[industry] = score
        
        # Select industry with highest score
        if industry_scores:
            best_industry = max(industry_scores, key=industry_scores.get)
            state.update_lead_info("domain", best_industry.title())
            logger.info(f"Extracted domain: {best_industry}")

    # Enhanced problem detection with context extraction
    if state.lead_info["problem"] is None:
        problem_patterns = [
            r"(?:problem|challenge|issue|struggle|difficulty|pain point|trouble|concern)(?:\s+(?:is|we have|with|that))?\s+(.{10,100})",
            r"(?:we need|looking for|trying to|want to|hoping to|need help with)\s+(.{10,100})",
            r"(?:can't|cannot|unable to|struggling to|having trouble|difficult to)\s+(.{10,100})",
            r"(?:improve|solve|fix|address|handle|deal with|overcome)\s+(.{10,100})",
        ]
        
        for pattern in problem_patterns:
            matches = re.findall(pattern, user_text, re.IGNORECASE)
            if matches:
                problem_text = matches[0].strip()
                # Clean up the extracted text
                problem_text = re.sub(r'\s+', ' ', problem_text)  # Remove extra whitespace
                problem_text = problem_text.split('.')[0]  # Take first sentence
                
                if len(problem_text) > 10 and len(problem_text) < 200:
                    state.update_lead_info("problem", problem_text.capitalize())
                    logger.info(f"Extracted problem: {problem_text}")
                    break

    # Enhanced budget detection with better number parsing
    if state.lead_info["budget"] is None:
        budget_patterns = [
            r"budget.*?(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?)",
            r"(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?).*?budget",
            r"spend.*?(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?)",
            r"(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?).*?(?:per|each|every)\s+(?:month|year)",
            r"around.*?(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?)",
            r"approximately.*?(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?)",
            r"up to.*?(\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|thousand|m|million|b|billion))?)",
            r"(\d+)(?:\s*(?:k|thousand|m|million|b|billion))?\s*(?:dollar|buck)",
        ]
        
        for pattern in budget_patterns:
            matches = re.findall(pattern, user_text, re.IGNORECASE)
            if matches:
                budget_text = matches[0]
                # Normalize budget format
                budget_text = budget_text.replace(',', '').strip()
                if not budget_text.startswith('$'):
                    budget_text = f"${budget_text}"
                
                state.update_lead_info("budget", budget_text)
                logger.info(f"Extracted budget: {budget_text}")
                break
        
        # Also check for budget ranges or qualitative descriptions
        if state.lead_info["budget"] is None:
            qualitative_budgets = {
                "small": ["small", "limited", "tight", "minimal", "low"],
                "medium": ["medium", "moderate", "reasonable", "standard"],
                "large": ["large", "significant", "substantial", "big", "high"],
                "enterprise": ["enterprise", "corporate", "unlimited", "flexible"]
            }
            
            for category, keywords in qualitative_budgets.items():
                if any(keyword in user_text for keyword in keywords):
                    budget_context = [word for word in user_text.split() if any(bkw in word for bkw in ["budget", "spend", "cost", "price"])]
                    if budget_context:
                        state.update_lead_info("budget", f"{category.title()} budget range")
                        logger.info(f"Extracted qualitative budget: {category}")
                        break

# AI-powered lead extraction fallback
async def extract_lead_info_with_ai(conversation_state, user_input):
    """Use AI to extract lead information when pattern matching fails."""
    try:
        # Only try AI extraction if we're missing critical information
        missing_fields = [k for k, v in conversation_state.lead_info.items() if v is None]
        if not missing_fields:
            return
            
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return
            
        async_client = AsyncGroq(api_key=groq_api_key)
        
        extraction_prompt = f"""
Extract the following information from this conversation text. Return ONLY a JSON object with the requested fields. If information is not present, use null.

Fields to extract:
- company_name: The name of the user's company/organization (if mentioned)
- domain: The industry/business domain (technology, healthcare, finance, etc.)
- problem: The main challenge or problem they're trying to solve
- budget: Any budget information mentioned (keep original format)

Conversation text: "{user_input}"

Current missing fields: {missing_fields}

Return format: {{"company_name": "value or null", "domain": "value or null", "problem": "value or null", "budget": "value or null"}}
"""

        response = await async_client.chat.completions.create(
            messages=[{"role": "user", "content": extraction_prompt}],
            model="llama3-70b-8192",
            temperature=0.1,
            max_tokens=150
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Try to parse JSON response
        try:
            extracted_data = json.loads(ai_response)
            
            # Update conversation state with extracted information
            for field, value in extracted_data.items():
                if field in conversation_state.lead_info and value and value != "null":
                    if conversation_state.lead_info[field] is None:  # Only update if currently empty
                        conversation_state.update_lead_info(field, value)
                        logger.info(f"AI extracted {field}: {value}")
                        
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse AI extraction response: {ai_response}")
            
    except Exception as e:        logger.error(f"AI lead extraction error: {str(e)}")

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
@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "AI Voice Agent API is running"}


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
