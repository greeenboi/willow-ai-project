import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from agno.agent import Agent
from agno.models.groq import Groq
from agno.tools.calcom import CalComTools

logger = logging.getLogger(__name__)

class CalendarBookingAgent:
    """Specialized agent for handling calendar booking after lead qualification."""
    
    def __init__(self):
        """Initialize the calendar booking agent with Cal.com integration."""
        groq_api_key = os.getenv("GROQ_API_KEY")
        calcom_api_key = os.getenv("CALCOM_API_KEY")
        calcom_event_type_id = os.getenv("CALCOM_EVENT_TYPE_ID")
        self.agent = Agent(
            name="Calendar Assistant",
            instructions=[
                f"You're a scheduling assistant. Today is {datetime.now()}.",
                "You can help users by:",
                "    - Finding available time slots",
                "    - Creating new bookings",
                "    - Managing existing bookings (view, reschedule, cancel)",
                "    - Getting booking details",
                "    - IMPORTANT: In case of rescheduling or cancelling booking, call the get_upcoming_bookings function to get the booking uid. check available slots before making a booking for given time",
                "Always confirm important details before making bookings or changes.",
                "Keep responses concise and professional.",
                "Focus on scheduling the meeting efficiently."
            ],
            model=Groq(id="llama-3.3-70b-versatile", api_key=groq_api_key),
            tools=[CalComTools(user_timezone="America/New_York", api_key=calcom_api_key, event_type_id=calcom_event_type_id)],
            show_tool_calls=True,
            markdown=False  # Keep responses simple for TTS
        )
        
    async def get_response(self, user_message: str, lead_info: Dict) -> str:
        """Get a response from the calendar booking agent."""
        try:
            # Add context about the lead for personalized booking
            context_message = f"""
            Lead Context:
            - Company: {lead_info.get('company_name', 'Not provided')}
            - Domain: {lead_info.get('domain', 'Not provided')}
            - Problem: {lead_info.get('problem', 'Not provided')}
            
            User message: {user_message}
            """
            
            # Get response from the agent
            response = await asyncio.to_thread(
                self.agent.print_response, 
                context_message, 
                stream=False
            )
            
            # Extract the text response
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"Calendar agent error: {str(e)}")
            return "I'm having trouble accessing the calendar system. Let me help you schedule a meeting manually. What times work best for you this week?"
    
    def should_end_booking_session(self, user_message: str) -> bool:
        """Determine if the booking session should end."""
        text_lower = user_message.lower()
        
        end_indicators = [
            "thank you", "thanks", "that's all", "goodbye", "bye",
            "booked", "scheduled", "confirmed", "perfect", "great",
            "see you then", "talk to you", "looking forward"
        ]
        
        return any(indicator in text_lower for indicator in end_indicators)
