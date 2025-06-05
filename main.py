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

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    print("Warning: aiofiles not available - audio file handling will be limited")

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
from knowledge_manager import KnowledgeManager

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
knowledge_manager = KnowledgeManager(db_manager)
logger.info("Database manager and knowledge manager initialized")

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
        self.agent_asked_demo = False  # Track if agent asked for demo
        self.meeting_booking_mode = False  # Track if agent is in meeting booking mode
        self.meeting_info = {
            "cal_link": None,
            "available_slots": [],
            "selected_date": None,
            "selected_time": None,
            "user_email": None,
            "user_name": None,
        }
          # Create session in database
        db_manager.create_session(session_id, self.lead_info)

    def update_lead_info(self, key, value):
        if key in self.lead_info:
            self.lead_info[key] = value
            # Update database
            db_manager.update_session(self.session_id, self.lead_info, self.current_stage)
            return True
        return False

    def update_session_state(self, **kwargs):
        """Update session state variables like demo tracking."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"Updated session state: {key} = {value}")

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

Demo and Meeting Booking Flow:
1. Qualification Phase: First, collect the required information (company, domain, problem, budget).
2. Demo Offer: Once you have sufficient information, offer to show a product demo.
3. Demo Presentation: If the user agrees to see a demo, present it and then ask for their feedback.
4. Meeting Transition: After showing the demo and getting positive feedback, offer to schedule a meeting with an Account Executive.
5. Meeting Booking: If the user agrees to a meeting, help them book it through our calendar system.

IMPORTANT: Always follow this sequence and don't skip steps. After showing a demo, always ask if they found it helpful and if they think it's a good fit for their needs. Listen carefully to their response before offering a meeting.

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

# Function to get AI response using knowledge manager
async def get_ai_response(conversation_state, user_input):
    """Get AI response using knowledge manager for intelligent conversation flow."""
    try:
        logger.info(f"Getting AI response for input: {user_input[:50]}...")
          # Get contextual response from knowledge manager
        session_context = {
            "conversation_history": conversation_state.conversation_history,
            "current_stage": conversation_state.current_stage,
            "agent_asked_demo": getattr(conversation_state, 'agent_asked_demo', False),
            "lead_info": conversation_state.lead_info
        }
        response_data = knowledge_manager.get_contextual_response(
            user_input, 
            session_context, 
            conversation_state.lead_info
        )

        # Handle demo offer flag - agent will ask for demo in response
        if response_data.get("agent_will_ask_demo"):
            conversation_state.agent_asked_demo = True
            logger.info("Agent offering demo - setting flag to True")

        # Handle meeting booking flag - agent will start meeting booking mode
        if response_data.get("start_meeting_booking"):
            conversation_state.meeting_booking_mode = True
            # Generate cal.com link
            cal_link = f"https://cal.com/{CAL_COM_EVENT_TYPE_ID}"
            # Store the cal.com link in meeting_info
            conversation_state.meeting_info["cal_link"] = cal_link
            logger.info("Agent starting meeting booking mode - setting flag to True")

        # Check if agent will ask for demo in the next response (fallback)
        final_response = knowledge_manager.format_agent_response(response_data, user_input)
        if final_response and ("would you like to see" in final_response.lower() or ("demo" in final_response.lower() and "?" in final_response)):
            conversation_state.agent_asked_demo = True
            logger.info("Agent asking for demo - setting flag to True")

        # Update lead info with extracted information
        if response_data.get("updated_lead_info"):
            for key, value in response_data["updated_lead_info"].items():
                if key in conversation_state.lead_info and value:
                    conversation_state.update_lead_info(key, value)
            # Check for media recommendations or demo triggers
        media_suggestion = knowledge_manager.should_show_media(user_input, session_context)

        # If agent asked about demo and user response indicates interest, ensure we show the demo
        if session_context.get("agent_asked_demo") and any(keyword in user_input.lower() for keyword in ["yes", "sure", "okay", "show", "demo", "see"]):
            media_suggestion = {"type": "demo", "topic": "product_overview"}
            logger.info("Demo interest detected in user response - forcing demo display")

        # Handle meeting booking flow if in meeting booking mode
        if conversation_state.meeting_booking_mode:
            text_lower = user_input.lower()

            # Check if user wants to book directly using cal.com link
            if any(keyword in text_lower for keyword in ["book", "myself", "direct", "calendar", "link", "cal.com"]):
                # User wants to book directly - remind them of the cal.com link
                cal_link = conversation_state.meeting_info.get("cal_link", "https://cal.com")
                response_data["direct_booking_response"] = f"Great! You can book a meeting directly using our calendar system at {cal_link}. Just select a time that works for you, and we'll send you a confirmation email with all the details."
                logger.info("User wants to book directly - providing cal.com link")

            # Check if user wants agent to guide them through booking process
            elif any(keyword in text_lower for keyword in ["guide", "help", "assist", "you", "agent"]):
                # User wants agent to guide them - ask for their email
                response_data["guided_booking_response"] = "I'd be happy to help you schedule a meeting! To get started, could you please share your email address so we can send you the meeting confirmation?"
                conversation_state.meeting_info["booking_stage"] = "collecting_email"
                logger.info("User wants guided booking - asking for email")

            # Check if user is providing their email (if we're collecting it)
            elif conversation_state.meeting_info.get("booking_stage") == "collecting_email" and "@" in text_lower:
                # User provided email - store it and ask for name
                conversation_state.meeting_info["user_email"] = user_input
                response_data["guided_booking_response"] = "Thanks for your email! And what's your name for the booking?"
                conversation_state.meeting_info["booking_stage"] = "collecting_name"
                logger.info(f"Collected user email: {user_input}")

            # Check if user is providing their name (if we're collecting it)
            elif conversation_state.meeting_info.get("booking_stage") == "collecting_name":
                # User provided name - store it and ask for preferred date
                conversation_state.meeting_info["user_name"] = user_input
                response_data["guided_booking_response"] = "Great! What day would work best for you for a 30-minute meeting? (e.g., tomorrow, Monday, July 15th)"
                conversation_state.meeting_info["booking_stage"] = "collecting_date"
                logger.info(f"Collected user name: {user_input}")

            # Check if user is providing a date (if we're collecting it)
            elif conversation_state.meeting_info.get("booking_stage") == "collecting_date":
                # User provided date - store it and ask for preferred time
                conversation_state.meeting_info["selected_date"] = user_input
                response_data["guided_booking_response"] = "And what time would work best for you? (e.g., 10am, 2:30pm)"
                conversation_state.meeting_info["booking_stage"] = "collecting_time"
                logger.info(f"Collected preferred date: {user_input}")

            # Check if user is providing a time (if we're collecting it)
            elif conversation_state.meeting_info.get("booking_stage") == "collecting_time":
                # User provided time - store it and confirm booking
                conversation_state.meeting_info["selected_time"] = user_input

                # Prepare booking data
                booking_data = {
                    "session_id": conversation_state.session_id,
                    "name": conversation_state.meeting_info.get("user_name", "User"),
                    "email": conversation_state.meeting_info.get("user_email", "user@example.com"),
                    "start_time": f"{conversation_state.meeting_info.get('selected_date', 'tomorrow')} {user_input}"
                }

                # Add company name if available
                if conversation_state.lead_info.get("company_name"):
                    booking_data["company"] = conversation_state.lead_info.get("company_name")

                # Store booking data for later use
                conversation_state.meeting_info["booking_data"] = booking_data

                # Confirm booking details
                response_data["guided_booking_response"] = f"Great! I'll book a 30-minute meeting for {booking_data['name']} ({booking_data['email']}) on {booking_data['start_time']}. Is that correct?"
                conversation_state.meeting_info["booking_stage"] = "confirming_booking"
                logger.info(f"Collected preferred time: {user_input}")

            # Check if user is confirming booking
            elif conversation_state.meeting_info.get("booking_stage") == "confirming_booking":
                # Check if user confirmed
                if any(keyword in text_lower for keyword in ["yes", "correct", "right", "good", "confirm", "book it"]):
                    # User confirmed - book the meeting
                    booking_data = conversation_state.meeting_info.get("booking_data", {})

                    try:
                        # Call the cal.com API to book the meeting
                        if CAL_COM_API_KEY and CAL_COM_EVENT_TYPE_ID:
                            headers = {
                                "Authorization": f"Bearer {CAL_COM_API_KEY}",
                                "Content-Type": "application/json"
                            }

                            # Prepare booking data for Cal.com API
                            cal_booking_data = {
                                "eventTypeId": int(CAL_COM_EVENT_TYPE_ID),
                                "start": booking_data["start_time"],
                                "responses": {
                                    "name": booking_data["name"],
                                    "email": booking_data["email"],
                                    "notes": "Meeting booked via Willow AI agent"
                                },
                                "metadata": {
                                    "session_id": booking_data["session_id"],
                                    "source": "willow_ai_agent"
                                }
                            }

                            # Add company name if available
                            if "company" in booking_data:
                                cal_booking_data["responses"]["company"] = booking_data["company"]

                            # Make booking request to Cal.com
                            url = f"{CAL_COM_BASE_URL}/bookings"
                            response = requests.post(url, headers=headers, json=cal_booking_data)

                            if response.status_code == 201:
                                booking_response = response.json()
                                booking_id = booking_response.get("id")
                                booking_url = booking_response.get("url")

                                # Update lead info with meeting details
                                conversation_state.lead_info["meeting_booked"] = True
                                conversation_state.lead_info["meeting_id"] = booking_id
                                conversation_state.lead_info["meeting_time"] = booking_data.get("start_time")
                                conversation_state.lead_info["attendee_email"] = booking_data.get("email")
                                conversation_state.lead_info["attendee_name"] = booking_data.get("name")

                                # Reset meeting booking mode
                                conversation_state.meeting_booking_mode = False

                                # Provide confirmation message with booking URL if available
                                if booking_url:
                                    response_data["guided_booking_response"] = f"Perfect! I've booked your meeting for {booking_data.get('start_time')}. You'll receive a confirmation email shortly with all the details. You can also view or manage your booking at {booking_url}. Is there anything else you'd like to know about Willow AI before our meeting?"
                                else:
                                    response_data["guided_booking_response"] = f"Perfect! I've booked your meeting for {booking_data.get('start_time')}. You'll receive a confirmation email shortly with all the details. Is there anything else you'd like to know about Willow AI before our meeting?"

                                logger.info(f"Meeting booked successfully with Cal.com API. Booking ID: {booking_id}")
                            else:
                                # Booking failed - provide error message
                                logger.error(f"Cal.com booking error: {response.status_code} - {response.text}")
                                response_data["guided_booking_response"] = "I apologize, but I'm having trouble booking your meeting through our calendar system. Could you try booking directly using our calendar link? Alternatively, I can try again or we can reschedule for a different time."
                        else:
                            # Cal.com API not configured - simulate successful booking
                            logger.warning("Cal.com API not configured - simulating successful booking")

                            # Update lead info with meeting details
                            conversation_state.lead_info["meeting_booked"] = True
                            conversation_state.lead_info["meeting_time"] = booking_data.get("start_time")
                            conversation_state.lead_info["attendee_email"] = booking_data.get("email")
                            conversation_state.lead_info["attendee_name"] = booking_data.get("name")

                            # Reset meeting booking mode
                            conversation_state.meeting_booking_mode = False

                            # Provide confirmation message
                            response_data["guided_booking_response"] = f"Perfect! I've booked your meeting for {booking_data.get('start_time')}. You'll receive a confirmation email shortly with all the details. Is there anything else you'd like to know about Willow AI before our meeting?"
                            logger.info(f"Meeting booked (simulated) for {booking_data.get('start_time')}")
                    except Exception as e:
                        # Error handling
                        logger.error(f"Error booking meeting: {str(e)}")
                        response_data["guided_booking_response"] = "I apologize, but I'm having trouble booking your meeting. Could you try booking directly using our calendar link? Alternatively, I can try again or we can reschedule for a different time."
                else:
                    # User didn't confirm - ask what needs to be changed
                    response_data["guided_booking_response"] = "I apologize for the confusion. What would you like to change about the booking?"
                    conversation_state.meeting_info["booking_stage"] = "collecting_date"  # Reset to date collection
                    logger.info("User didn't confirm booking - resetting to date collection")

        if media_suggestion or response_data.get("show_demo"):
            if response_data.get("show_demo") or (media_suggestion and media_suggestion.get("type") == "demo"):
                conversation_state.media_to_display = {"type": "demo", "topic": "product_overview"}
                # Set demo_shown flag in lead_info for future meeting offers
                conversation_state.update_lead_info("demo_shown", True)
                logger.info("Demo triggered by user agreement")
            else:
                conversation_state.media_to_display = media_suggestion
                logger.info(f"Media suggested: {conversation_state.media_to_display}")

        # Reset demo flag after showing demo
        if response_data.get("show_demo"):
            conversation_state.agent_asked_demo = False
            conversation_state.update_session_state(agent_asked_demo=False)
            logger.info("Demo shown - resetting agent_asked_demo flag")

        # Generate dynamic system prompt based on current context
        dynamic_prompt = knowledge_manager.generate_system_prompt(session_context, conversation_state.lead_info)

        # Format the final response using knowledge manager
        final_response = knowledge_manager.format_agent_response(response_data, user_input)

        # Replace {cal_link} placeholder with actual cal.com link if in meeting booking mode
        if conversation_state.meeting_booking_mode and "{cal_link}" in final_response:
            cal_link = conversation_state.meeting_info.get("cal_link", "https://cal.com")
            final_response = final_response.replace("{cal_link}", cal_link)
            logger.info(f"Replaced cal_link placeholder with {cal_link}")

        # If we have a formatted response, use it directly
        if final_response and final_response.strip():
            logger.info(f"Knowledge manager response: {final_response[:100]}...")
            return final_response

        # Fallback to AI generation with dynamic prompt
        return await get_ai_response_with_prompt(conversation_state, user_input, dynamic_prompt)

    except Exception as e:
        logger.error(f"Knowledge manager error: {str(e)}")
        return await get_ai_response_fallback(conversation_state, user_input)

# Fallback AI response function with dynamic prompt
async def get_ai_response_with_prompt(conversation_state, user_input, system_prompt):
    """Get AI response using dynamic system prompt."""
    try:
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return "I'm sorry, I'm having trouble connecting to my AI service. Please try again later."

        async_client = AsyncGroq(api_key=groq_api_key)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # Add conversation history
        for entry in conversation_state.conversation_history[-10:]:
            role = "assistant" if entry["speaker"] == "agent" else "user"
            messages.append({"role": role, "content": entry["message"]})

        messages.append({"role": "user", "content": user_input})

        chat_completion = await async_client.chat.completions.create(
            messages=messages,
            model="llama3-70b-8192",
            temperature=0.7,
            max_tokens=200,
            top_p=0.9
        )

        response_text = chat_completion.choices[0].message.content
        logger.info(f"AI response with dynamic prompt: {response_text[:100]}...")
        return response_text

    except Exception as e:
        logger.error(f"AI response with prompt error: {str(e)}")
        return "I'm sorry, I'm having trouble processing that. Could you please repeat?"

# Original fallback function
async def get_ai_response_fallback(conversation_state, user_input):
    """Fallback AI response using original static prompt."""
    try:
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return "I'm sorry, I'm having trouble connecting to my AI service. Please try again later."

        async_client = AsyncGroq(api_key=groq_api_key)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        for entry in conversation_state.conversation_history[-10:]:
            role = "assistant" if entry["speaker"] == "agent" else "user"
            messages.append({"role": role, "content": entry["message"]})

        messages.append({"role": "user", "content": user_input})

        chat_completion = await async_client.chat.completions.create(
            messages=messages,
            model="llama3-70b-8192",
            temperature=0.7,
            max_tokens=200,
            top_p=0.9
        )

        response_text = chat_completion.choices[0].message.content
        return response_text

    except Exception as e:
        logger.error(f"Fallback AI response error: {str(e)}")
        return "I'm sorry, I'm having trouble processing that. Could you please repeat?"

# Legacy functions - kept for reference but no longer used
# The knowledge manager now handles all lead information extraction

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

@app.get("/api/session/new")
async def create_new_session():
    """Generate a new unique session ID"""
    try:
        # Generate a unique session ID using UUID
        new_session_id = f"session_{uuid.uuid4().hex[:12]}"
        logger.info(f"Generated new session ID: {new_session_id}")
        return JSONResponse(content={"session_id": new_session_id})
    except Exception as e:
        logger.error(f"Error generating new session ID: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to generate new session ID"}
        )

@app.get("/api/session/{session_id}/start")
async def start_session(session_id: str, restore: bool = False):
    """Start a new session and return initial greeting"""
    try:
        logger.info(f"Starting session: {session_id}, restore: {restore}")

        # Initialize conversation state
        if session_id not in active_connections:
            active_connections[session_id] = ConversationState(session_id)
            # Only load existing session data if restore=True
            if restore:
                active_connections[session_id].load_from_database()

        conv_state = active_connections[session_id]

        # Generate dynamic initial greeting using knowledge manager
        session_context = {
            "conversation_history": conv_state.conversation_history,
            "current_stage": conv_state.current_stage,
            "lead_info": conv_state.lead_info
        }

        # Use knowledge manager to generate appropriate greeting
        if len(conv_state.conversation_history) == 0 or not restore:
            # First time greeting for new sessions
            initial_greeting = "Hi there! I'm Jane, an AI Sales Development Representative for Willow AI. I'd love to learn more about your company and see how we might be able to help you. Could you start by telling me your name and what company you're with?"
        else:
            # Returning session - generate contextual greeting (only when restore=True)
            completion_percentage = knowledge_manager.calculate_completion_percentage(conv_state.lead_info)
            if completion_percentage < 50:
                initial_greeting = "Welcome back! Let's continue where we left off. Could you tell me more about your company and what challenges you're facing?"
            else:
                initial_greeting = "Welcome back! I see we've gathered some information about your needs. Would you like to continue our conversation or see a demo of how Willow AI could help your team?"

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

@app.get("/api/session/{session_id}/analytics")
async def get_session_analytics(session_id: str):
    """Get session analytics including persona detection, completion status, and recommendations"""
    try:
        if session_id not in active_connections:
            # Try to load from database
            conv_state = ConversationState(session_id)
            if not conv_state.load_from_database():
                raise HTTPException(status_code=404, detail="Session not found")
            active_connections[session_id] = conv_state

        conv_state = active_connections[session_id]

        # Get latest user message for persona detection
        latest_user_message = ""
        for entry in reversed(conv_state.conversation_history):
            if entry["speaker"] == "user":
                latest_user_message = entry["message"]
                break

        # Generate analytics using knowledge manager
        session_context = {
            "conversation_history": conv_state.conversation_history,
            "current_stage": conv_state.current_stage,
            "lead_info": conv_state.lead_info
        }

        analytics = {
            "lead_completion": knowledge_manager.calculate_completion_percentage(conv_state.lead_info),
            "persona": knowledge_manager.detect_persona(latest_user_message) if latest_user_message else "unknown",
            "missing_info": knowledge_manager.get_missing_lead_info(conv_state.lead_info),
            "conversation_length": len(conv_state.conversation_history),
            "lead_info": conv_state.lead_info,
            "recommended_next_questions": []
        }

        # Get recommended next questions if qualification isn't complete
        if analytics["lead_completion"] < 100:
            analytics["recommended_next_questions"] = knowledge_manager.get_next_questions(
                analytics["persona"], 
                analytics["missing_info"]
            )

        return JSONResponse(content=analytics)

    except Exception as e:
        logger.error(f"Error getting analytics for {session_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve session analytics"}
        )

@app.get("/api/knowledge/search")
async def search_knowledge_base(query: str, limit: int = 5):
    """Search the knowledge base for relevant information"""
    try:
        results = db_manager.search_knowledge_base(query, limit)
        return JSONResponse(content={"results": results})
    except Exception as e:
        logger.error(f"Error searching knowledge base: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to search knowledge base"}
        )

@app.get("/api/knowledge/questions/{persona}")
async def get_qualification_questions(persona: str, category: str = None):
    """Get qualification questions for a specific persona and category"""
    try:
        questions = db_manager.get_qualification_questions(persona, category)
        return JSONResponse(content={"questions": questions})
    except Exception as e:
        logger.error(f"Error getting questions for persona {persona}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve qualification questions"}
        )

@app.get("/api/sessions/summary")
async def get_all_sessions_summary():
    """Get summary of all sessions for analytics dashboard"""
    try:
        # This would typically query the database for session summaries
        # For now, return active session summaries
        summaries = {}
        for session_id, conv_state in active_connections.items():
            completion = knowledge_manager.calculate_completion_percentage(conv_state.lead_info)
            summaries[session_id] = {
                "completion_percentage": completion,
                "conversation_length": len(conv_state.conversation_history),
                "lead_info": conv_state.lead_info,
                "current_stage": conv_state.current_stage
            }

        return JSONResponse(content={"sessions": summaries})

    except Exception as e:
        logger.error(f"Error getting sessions summary: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve sessions summary"}
        )

# Cal.com API configuration
CAL_COM_API_KEY = os.getenv("CAL_COM_API_KEY")
CAL_COM_BASE_URL = os.getenv("CAL_COM_BASE_URL", "https://api.cal.com/v1")
CAL_COM_EVENT_TYPE_ID = os.getenv("CAL_COM_EVENT_TYPE_ID")  # Your event type ID

@app.get("/api/calendar/availability")
async def get_calendar_availability(date: str = None):
    """Get available time slots for meeting booking"""
    try:
        if not CAL_COM_API_KEY or not CAL_COM_EVENT_TYPE_ID:
            return JSONResponse(
                status_code=500,
                content={"error": "Cal.com configuration missing"}
            )

        # Default to today if no date provided
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        headers = {
            "Authorization": f"Bearer {CAL_COM_API_KEY}",
            "Content-Type": "application/json"
        }

        # Get availability for the specified date
        url = f"{CAL_COM_BASE_URL}/availability"
        params = {
            "eventTypeId": CAL_COM_EVENT_TYPE_ID,
            "dateFrom": date,
            "dateTo": date
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            availability_data = response.json()

            # Transform the data to a more user-friendly format
            slots = []
            if "available" in availability_data:
                for slot in availability_data["available"]:
                    slots.append({
                        "time": slot["start"],
                        "duration": slot.get("duration", 30),  # Default 30 min
                        "available": True
                    })

            return JSONResponse(content={
                "date": date,
                "slots": slots,
                "timezone": availability_data.get("timezone", "UTC")
            })
        else:
            logger.error(f"Cal.com API error: {response.status_code} - {response.text}")
            return JSONResponse(
                status_code=response.status_code,
                content={"error": "Failed to fetch availability"}
            )

    except Exception as e:
        logger.error(f"Error fetching calendar availability: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch availability"}
        )

@app.post("/api/calendar/book")
async def book_meeting(request: Request):
    """Book a meeting via Cal.com API"""
    try:
        if not CAL_COM_API_KEY or not CAL_COM_EVENT_TYPE_ID:
            return JSONResponse(
                status_code=500,
                content={"error": "Cal.com configuration missing"}
            )

        booking_data = await request.json()

        # Validate required fields
        required_fields = ["session_id", "name", "email", "start_time"]
        for field in required_fields:
            if field not in booking_data:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Missing required field: {field}"}
                )

        headers = {
            "Authorization": f"Bearer {CAL_COM_API_KEY}",
            "Content-Type": "application/json"
        }

        # Prepare booking data for Cal.com
        cal_booking_data = {
            "eventTypeId": int(CAL_COM_EVENT_TYPE_ID),
            "start": booking_data["start_time"],
            "responses": {
                "name": booking_data["name"],
                "email": booking_data["email"],
                "notes": booking_data.get("notes", "Meeting booked via Willow AI")
            },
            "metadata": {
                "session_id": booking_data["session_id"],
                "source": "willow_ai"
            }
        }

        # Add custom questions if provided
        if "company" in booking_data:
            cal_booking_data["responses"]["company"] = booking_data["company"]

        if "phone" in booking_data:
            cal_booking_data["responses"]["phone"] = booking_data["phone"]

        # Make booking request to Cal.com
        url = f"{CAL_COM_BASE_URL}/bookings"
        response = requests.post(url, headers=headers, json=cal_booking_data)

        if response.status_code == 201:
            booking_response = response.json()

            # Update session with meeting booking info
            session_id = booking_data["session_id"]
            if session_id in active_connections:
                conv_state = active_connections[session_id]

                # Add meeting info to lead data
                conv_state.lead_info["meeting_booked"] = True
                conv_state.lead_info["meeting_id"] = booking_response.get("id")
                conv_state.lead_info["meeting_time"] = booking_data["start_time"]
                conv_state.lead_info["attendee_email"] = booking_data["email"]
                conv_state.lead_info["attendee_name"] = booking_data["name"]

                # Save to database
                try:
                    db_manager.update_session_data(
                        session_id, 
                        conv_state.lead_info, 
                        conv_state.conversation_history,
                        completion_percentage=knowledge_manager.calculate_completion_percentage(conv_state.lead_info),
                        current_stage="meeting_booked"
                    )
                except Exception as db_error:
                    logger.error(f"Failed to update database after booking: {str(db_error)}")

            return JSONResponse(content={
                "success": True,
                "booking_id": booking_response.get("id"),
                "booking_url": booking_response.get("url"),
                "meeting_time": booking_data["start_time"],
                "message": "Meeting successfully booked! You'll receive a confirmation email shortly."
            })
        else:
            logger.error(f"Cal.com booking error: {response.status_code} - {response.text}")
            return JSONResponse(
                status_code=response.status_code,
                content={"error": "Failed to book meeting"}
            )

    except Exception as e:
        logger.error(f"Error booking meeting: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to book meeting"}
        )

@app.get("/api/calendar/meetings/{session_id}")
async def get_session_meetings(session_id: str):
    """Get meetings booked for a specific session"""
    try:
        if session_id in active_connections:
            conv_state = active_connections[session_id]
            meeting_info = {
                "has_meeting": conv_state.lead_info.get("meeting_booked", False),
                "meeting_id": conv_state.lead_info.get("meeting_id"),
                "meeting_time": conv_state.lead_info.get("meeting_time"),
                "attendee_email": conv_state.lead_info.get("attendee_email"),
                "attendee_name": conv_state.lead_info.get("attendee_name")
            }
            return JSONResponse(content=meeting_info)
        else:
            # Try to get from database
            session_data = db_manager.get_session_data(session_id)
            if session_data:
                lead_info = json.loads(session_data[2]) if session_data[2] else {}
                meeting_info = {
                    "has_meeting": lead_info.get("meeting_booked", False),
                    "meeting_id": lead_info.get("meeting_id"),
                    "meeting_time": lead_info.get("meeting_time"),
                    "attendee_email": lead_info.get("attendee_email"),
                    "attendee_name": lead_info.get("attendee_name")
                }
                return JSONResponse(content=meeting_info)
            else:
                raise HTTPException(status_code=404, detail="Session not found")

    except Exception as e:
        logger.error(f"Error getting session meetings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve meeting information"}
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
