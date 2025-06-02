---
applyTo: '**'
---
Your task is to build an efficient, low-latency AI voice agent that can engage users in natural, human-like conversations to qualify leads, simulating the role of an SDR (Sales Development Representative). The agent should be able to:
Greet the user.
Ask qualifying questions: Company name, Domain, Problem statement, and Budget.
Answer basic product/service-related questions.
Display images or videos based on the context of the conversation.
Collect and summarize lead information for handoff to a human.
End the call gracefully.



🛠️ Technical Requirements
Speech Recognition (STT): Use open-source or free APIs to convert voice input to text.
Conversational Logic: Use any conversational AI for processing the input.


Text-to-Speech (TTS): Use fast, open-source, and cost-effective TTS options.


Streaming & Real-Time: Build a system with minimal latency; sub-second round-trip preferred.


User Interface: Build a React (vite + shadcn ui) where the user can interact with the voice agent.


Display Media: The agent should be able to dynamically display images/videos in the UI based on detected keywords or topics.


Backend is built using  FastAPI, and can be run locally or deployed for demo purposes.


❗ Constraints
Do not use paid, closed platforms like Vapi, AssemblyAI, Descript, Play.ht, or Google Dialogflow.


Use groq ai Whisper model for stt and groq playai for tts.
Do not use any paid APIs or services for STT or TTS.

📌 Guidelines
The system should handle interruptions, allow recovery from errors, and stay on topic.


Log the full interaction (voice or text-based transcript) for review.


The initial code has been provided in the repository. You can build upon it to meet the requirements.
The agent should be able to handle multiple users in a single session, maintaining context for each user.

