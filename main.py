import os
import json
import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal

import aiofiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from groq import Groq, AsyncGroq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
async_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

# Configure directories
AUDIO_DIR = Path("static/audio")
AUDIO_DIR.mkdir(exist_ok=True, parents=True)
TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Define message models for chat completion
class MessageRole(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

# Voice agent context
class ConversationState:
    def __init__(self):
        self.lead_info = {
            "company_name": None,
            "domain": None,
            "problem": None,
            "budget": None,
        }
        self.conversation_history = []
        self.current_stage = "greeting"
        self.media_to_display = None

    def update_lead_info(self, key, value):
        if key in self.lead_info:
            self.lead_info[key] = value
            return True
        return False

    def add_to_history(self, speaker, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conversation_history.append({"timestamp": timestamp, "speaker": speaker, "message": message})

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


# Active connections and their states
active_connections: Dict[str, ConversationState] = {}

# System prompt template for the AI agent
SYSTEM_PROMPT = """
You are an AI voice agent acting as an SDR (Sales Development Representative) for a software company. 
Your task is to qualify leads by collecting specific information in a natural, conversational way.

The information you need to collect:
1. Company name
2. Domain/Industry
3. Problem they're trying to solve
4. Budget range

Keep your responses concise and natural. Speak as a helpful, friendly sales representative would.
Introduce yourself briefly when starting. Guide the conversation toward collecting the required information.
Answer product questions generally but focus on qualifying the lead. 
End the call politely when you have all the information or if the user wants to end.

If the user mentions keywords related to product demos, pricing, or features, suggest showing relevant media.
When suggesting media, include a JSON command in your response like: 
{"show_media": "demo", "topic": "feature_name"}
Available media topics: demo, pricing, features, testimonials.
"""

# Function to transcribe audio using Groq
async def transcribe_audio(audio_file_path):
    try:
        with open(audio_file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=file,
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                language="en",
                temperature=0.0
            )
        return transcription.text
    except Exception as e:
        print(f"Transcription error: {str(e)}")
        return None

# Function to get AI response
async def get_ai_response(conversation_state, user_input):
    try:
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

        # Check for media commands in the response
        if '{"show_media":' in response_text:
            try:
                # Extract JSON command
                start_idx = response_text.find('{"show_media":')
                end_idx = response_text.find('}', start_idx) + 1
                media_command = json.loads(response_text[start_idx:end_idx])

                # Set media to display
                conversation_state.media_to_display = {
                    "type": media_command.get("show_media", "demo"),
                    "topic": media_command.get("topic", "general")
                }

                # Remove JSON command from response
                response_text = response_text[:start_idx].strip() + " " + response_text[end_idx:].strip()
            except:
                pass

        # Update lead info based on AI response
        update_lead_info_from_conversation(conversation_state, user_input, response_text)

        return response_text
    except Exception as e:
        print(f"AI response error: {str(e)}")
        return "I'm sorry, I'm having trouble processing that. Could you please repeat?"

# Function to update lead info based on conversation
def update_lead_info_from_conversation(state, user_input, ai_response):
    # Simple keyword extraction for demo purposes
    # In a real system, you'd use NER or a more sophisticated extraction method

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

# Simple text-to-speech using pre-recorded samples
# In production, integrate with a proper TTS service
async def text_to_speech(text):
    try:
        # Use Groq's TTS API
        speech_file_path = f"{AUDIO_DIR}/temp_{uuid.uuid4()}.wav"

        model = "playai-tts"
        voice = "Fritz-PlayAI"  # You can change this to another voice if preferred
        response_format = "wav"

        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format=response_format
        )

        # Save the file
        response.write_to_file(speech_file_path)

        # Read the file and convert to base64 for sending over websocket
        with open(speech_file_path, "rb") as audio_file:
            audio_content = audio_file.read()
            base64_audio = base64.b64encode(audio_content).decode('utf-8')

        # Optionally cleanup the file if needed
        # os.remove(speech_file_path)

        return base64_audio
    except Exception as e:
        print(f"TTS error: {str(e)}")
        return None

# Routes and WebSocket handlers
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Initialize conversation state for this connection
    if session_id not in active_connections:
        active_connections[session_id] = ConversationState()

    conv_state = active_connections[session_id]

    # Send initial greeting
    initial_greeting = "Hi there! I'm AI Agent, a virtual sales representative. I'd like to learn more about your company and how we might be able to help you. Could you tell me the name of your company?"
    conv_state.add_to_history("agent", initial_greeting)

    greeting_audio = await text_to_speech(initial_greeting)
    await websocket.send_json({
        "type": "agent_response",
        "text": initial_greeting,
        "audio": greeting_audio
    })

    try:
        while True:
            data = await websocket.receive()

            # Handle different message types
            if "text" in data:
                # Text input from user
                user_message = data["text"]
                conv_state.add_to_history("user", user_message)

                # Get AI response
                ai_response = await get_ai_response(conv_state, user_message)
                conv_state.add_to_history("agent", ai_response)

                # Convert to speech
                speech_audio = await text_to_speech(ai_response)

                # Send response to client
                response_data = {
                    "type": "agent_response",
                    "text": ai_response,
                    "audio": speech_audio
                }

                # Add media if any was triggered
                if conv_state.media_to_display:
                    response_data["media"] = conv_state.media_to_display
                    conv_state.media_to_display = None

                await websocket.send_json(response_data)

            elif "audio" in data:
                # Audio input from user
                audio_data = base64.b64decode(data["audio"].split(",")[1])

                # Save audio to file
                audio_filename = f"{AUDIO_DIR}/{session_id}_{uuid.uuid4()}.wav"
                async with aiofiles.open(audio_filename, 'wb') as f:
                    await f.write(audio_data)

                # Transcribe audio
                transcript = await transcribe_audio(audio_filename)
                if transcript:
                    conv_state.add_to_history("user", transcript)

                    # Get AI response
                    ai_response = await get_ai_response(conv_state, transcript)
                    conv_state.add_to_history("agent", ai_response)

                    # Convert to speech
                    speech_audio = await text_to_speech(ai_response)

                    # Send response to client
                    response_data = {
                        "type": "agent_response",
                        "text": ai_response,
                        "transcript": transcript,
                        "audio": speech_audio
                    }

                    # Add media if any was triggered
                    if conv_state.media_to_display:
                        response_data["media"] = conv_state.media_to_display
                        conv_state.media_to_display = None

                    await websocket.send_json(response_data)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Failed to transcribe audio"
                    })

            # Check if we have all the information needed
            summary = conv_state.get_summary()
            if not summary["missing_info"]:
                # All information collected
                conv_state.save_transcript(session_id)

    except WebSocketDisconnect:
        # Save conversation transcript when user disconnects
        if session_id in active_connections:
            active_connections[session_id].save_transcript(session_id)
            del active_connections[session_id]

@app.get("/summary/{session_id}")
async def get_summary(session_id: str):
    if session_id in active_connections:
        return JSONResponse(content=active_connections[session_id].get_summary())
    raise HTTPException(status_code=404, detail="Session not found")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
