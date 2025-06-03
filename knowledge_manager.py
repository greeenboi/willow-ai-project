import re
from typing import Dict, List, Optional, Tuple
from database import DatabaseManager
import logging

logger = logging.getLogger(__name__)

class KnowledgeManager:
    """Manages knowledge base queries and intelligent response generation for the AI agent."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
        # Persona detection patterns
        self.persona_patterns = {
            "vp_sales": ["vp", "vice president", "head of sales", "sales director", "sales manager", "sales lead"],
            "sales_ops": ["sales ops", "revenue ops", "revops", "sales operations", "revenue operations"],
            "marketing_leader": ["cmo", "marketing", "demand gen", "growth", "pmm", "product marketing"],
            "plg_founder": ["founder", "ceo", "plg", "product-led", "self-serve", "freemium"]
        }
          # Intent detection patterns
        self.intent_patterns = {
            "product_question": ["how does", "what is", "can you", "do you", "features", "capabilities"],
            "pricing_question": ["cost", "price", "pricing", "budget", "expensive", "cheap"],
            "objection": ["but", "however", "already have", "don't need", "not interested", "too expensive", "concerns", "worried"],
            "interest": ["interested", "tell me more", "sounds good", "like that", "demo", "meeting"],
            "demo_request": ["demo", "show me", "see it", "preview", "walkthrough", "demonstration"],
            "demo_agreement": ["yes", "sure", "okay", "alright", "sounds good", "let's do it", "show me"],
            "meeting_interest": ["meeting", "call", "schedule", "book", "talk to", "speak with"],
            "qualification_info": ["we use", "our company", "we have", "currently", "right now"]
        }
        
        # Common objections and responses
        self.objection_responses = {
            "already_have_chatbot": "That's great! Unlike traditional chatbots, Willow AI doesn't just collect emails—it actually talks to leads, qualifies them like an SDR, and schedules meetings automatically. Have you seen gaps in your current chatbot where leads still fall through?",
            
            "prefer_human_sdrs": "Willow AI isn't replacing SDRs—it's making them more efficient. Instead of spending time on repetitive qualification, your reps can focus on closing high-intent leads.",
            
            "need_personal_touch": "That's exactly why we designed Willow AI to sound human-like and handle objections dynamically. It's trained on sales conversations, so it engages naturally, just like your best SDR would.",
            
            "ai_mistakes": "You define the qualification criteria, and Willow AI follows those rules. It can even flag leads for manual review if they need further evaluation.",
            
            "no_budget": "I understand! Many of our customers see a fast ROI because Willow AI increases inbound conversion rates and reduces SDR workload. Would it make sense to explore a pilot program to see the impact firsthand?",
            
            "too_expensive": "I understand cost is a concern. Willow AI typically pays for itself within the first month by converting more leads and reducing SDR overhead. Would you like to see how the ROI works for companies similar to yours?",
            
            "not_ready": "That makes sense. When would be a better time to revisit this? I can also send you some case studies showing how companies like yours have benefited from Willow AI.",
            
            "need_approval": "Absolutely, that's common for decisions like this. Would it help if I scheduled a quick demo with your team so everyone can see how Willow AI works? This way you'll have all the information needed for the discussion."
        }
    
    def detect_persona(self, text: str) -> str:
        """Detect the prospect's persona based on their input."""
        text_lower = text.lower()
        
        for persona, keywords in self.persona_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return persona
        
        return "general"
    def detect_objection(self, text: str) -> Optional[str]:
        """Detect specific objections in the user's message."""
        text_lower = text.lower()
        
        objection_patterns = {
            "already_have_chatbot": ["already have", "using drift", "using intercom", "have a chatbot", "current chatbot"],
            "prefer_human_sdrs": ["prefer human", "human touch", "real person", "not ai", "human sdrs"],
            "need_personal_touch": ["personal touch", "personalized", "human interaction", "real conversation"],
            "ai_mistakes": ["ai mistakes", "errors", "wrong information", "inaccurate", "trust ai"],
            "no_budget": ["no budget", "can't afford", "too expensive", "budget constraints", "tight budget"],
            "too_expensive": ["expensive", "costly", "price", "cost too much", "cheaper option"],
            "not_ready": ["not ready", "timing", "maybe later", "not right now", "future"],
            "need_approval": ["need approval", "talk to team", "discuss internally", "get buy-in", "check with"]
        }
        
        for objection_type, patterns in objection_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return objection_type
        
        return None

    def detect_demo_interest(self, text: str) -> bool:
        """Detect if the user is interested in seeing a demo."""
        text_lower = text.lower()
        demo_indicators = [
            "yes", "sure", "okay", "alright", "sounds good", "let's do it", 
            "show me", "i'd like to see", "demo", "walkthrough", "preview"
        ]
        
        return any(indicator in text_lower for indicator in demo_indicators)

    def detect_meeting_readiness(self, text: str, lead_info: Dict) -> bool:
        """Detect if the prospect is ready for a meeting."""
        completion = self.calculate_completion_percentage(lead_info)
        text_lower = text.lower()
        
        meeting_indicators = [
            "meeting", "call", "schedule", "book", "talk to", "speak with",
            "next step", "move forward", "interested", "good fit", "demo was great",
            "looks good", "this could work", "let's proceed", "sounds perfect",
            "exactly what we need", "when can we start", "pricing looks good"
        ]
        
        # Check if demo was completed successfully
        demo_completed = self.check_demo_completion(text, lead_info)
        
        # Only suggest meeting if lead is well qualified (>75% complete) AND demo was shown
        return (completion > 75 and 
                any(indicator in text_lower for indicator in meeting_indicators) and
                (demo_completed or lead_info.get("demo_shown", False)))

    def check_demo_completion(self, text: str, lead_info: Dict) -> bool:
        """Check if user has seen and responded positively to demo"""
        text_lower = text.lower()
        
        positive_demo_responses = [
            "demo was great", "looks good", "impressive", "exactly what we need",
            "this could work", "looks perfect", "very interesting", "this is helpful",
            "i like it", "looks promising", "this would work", "perfect solution"
        ]
        
        return any(response in text_lower for response in positive_demo_responses)

    def detect_intent(self, text: str) -> str:
        """Detect the intent behind the prospect's message."""
        text_lower = text.lower()
        
        for intent, keywords in self.intent_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return intent
        
        return "general_inquiry"
    
    def extract_company_info(self, text: str) -> Dict[str, str]:
        """Extract company information from prospect's message."""
        info = {}
        
        # Company name extraction patterns
        company_patterns = [
            r"(?:work at|from|with|at)\s+([A-Z][a-zA-Z\s&\.]+?)(?:\s|$|\.)",
            r"(?:company is|company:)\s+([A-Z][a-zA-Z\s&\.]+?)(?:\s|$|\.)",
            r"(?:I'm|I am)\s+(?:at|with|from)\s+([A-Z][a-zA-Z\s&\.]+?)(?:\s|$|\.)"
        ]
        
        for pattern in company_patterns:
            match = re.search(pattern, text)
            if match:
                company = match.group(1).strip()
                if len(company) > 2 and company.lower() not in ["the", "and", "inc", "llc"]:
                    info["company_name"] = company
                    break
        
        # Domain/Industry extraction
        industry_keywords = {
            "saas": ["saas", "software", "platform", "app", "application"],
            "ecommerce": ["ecommerce", "e-commerce", "retail", "online store", "marketplace"],
            "fintech": ["fintech", "financial", "banking", "payment", "finance"],
            "healthcare": ["healthcare", "medical", "health", "hospital", "clinic"],
            "education": ["education", "edtech", "learning", "school", "university"],
            "marketing": ["marketing", "advertising", "agency", "digital marketing"],
            "consulting": ["consulting", "services", "advisory", "consultancy"]
        }
        
        text_lower = text.lower()
        for domain, keywords in industry_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    info["domain"] = domain
                    break
            if "domain" in info:
                break
        
        return info
    
    def extract_pain_points(self, text: str) -> Optional[str]:
        """Extract pain points or problems from prospect's message."""
        pain_indicators = [
            "problem", "issue", "challenge", "struggle", "difficult", "hard",
            "frustrating", "painful", "bottleneck", "gap", "missing", "lack"
        ]
        
        text_lower = text.lower()
        for indicator in pain_indicators:
            if indicator in text_lower:
                # Extract the sentence containing the pain point
                sentences = text.split('.')
                for sentence in sentences:
                    if indicator in sentence.lower():
                        return sentence.strip()
        
        return None
    
    def extract_budget_info(self, text: str) -> Optional[str]:
        """Extract budget information from prospect's message."""
        budget_patterns = [
            r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:per|/)\s*(?:month|year|annually))?",
            r"budget.*?\$[\d,]+",
            r"(?:around|about|up to|less than|more than)\s*\$[\d,]+"
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        # Budget range indicators
        budget_ranges = {
            "under 10k": ["small budget", "tight budget", "limited budget", "startup budget"],
            "10k-50k": ["mid-range", "moderate budget", "reasonable budget"],
            "50k+": ["enterprise budget", "significant budget", "large budget", "substantial investment"]
        }
        
        text_lower = text.lower()
        for range_name, indicators in budget_ranges.items():
            for indicator in indicators:
                if indicator in text_lower:
                    return range_name
        
        return None
    
    def get_contextual_response(self, user_message: str, session_context: Dict, lead_info: Dict) -> Dict:
        """Generate a contextual response based on user message and session context."""
        persona = self.detect_persona(user_message)
        intent = self.detect_intent(user_message)
        
        # Check for objections first
        objection_type = self.detect_objection(user_message)
        if objection_type and objection_type in self.objection_responses:
            return {
                "objection_response": self.objection_responses[objection_type],
                "persona": persona,
                "intent": "objection_handling",
                "updated_lead_info": lead_info
            }
        
        # Check for demo interest
        completion = self.calculate_completion_percentage(lead_info)
        demo_interest = self.detect_demo_interest(user_message)
        agent_asked_demo = session_context.get("agent_asked_demo", False)
        
        if agent_asked_demo and demo_interest:
            # User agreed to see demo - this will trigger video display via should_show_media
            return {
                "demo_response": "Perfect! Here's a quick overview of how Willow AI works in action. This demo shows how Willow AI engages with prospects, qualifies them, and books meetings automatically.",
                "follow_up": "After you've had a chance to see this, I'd love to hear your thoughts. Do you feel like this could be a good fit for your team?",
                "persona": persona,
                "intent": "demo_viewing",
                "show_demo": True,
                "updated_lead_info": lead_info
            }
        
        # Check if we should offer a demo (new logic)
        if self.should_offer_demo(user_message, session_context):
            # Return demo offer message but don't show video yet
            return {
                "demo_offer": "That's great to hear! I'd love to show you exactly how Willow AI works. Would you like to see a quick product demo? It's just a 2-minute walkthrough of how we engage and qualify leads.",
                "persona": persona,
                "intent": "demo_offer",
                "updated_lead_info": lead_info,
                "agent_will_ask_demo": True  # Flag to set agent_asked_demo = True
            }
          # Check if we should offer a meeting with AE
        if self.should_offer_meeting(user_message, lead_info):
            return {
                "meeting_offer": "I'm so glad you found the demo helpful! It sounds like Willow AI could be a great fit for your team. I'd love to set up a customized strategy call with John, our account executive, who can walk you through exactly how this would work for your specific use case and discuss implementation. Would you like to schedule a 30-minute call this week?",
                "persona": persona,
                "intent": "meeting_offer",
                "updated_lead_info": lead_info
            }
        
        # Check for meeting readiness after demo (fallback)
        if completion >= 75 and self.detect_meeting_readiness(user_message, lead_info):
            return {
                "meeting_response": "Excellent! It sounds like Willow AI could be a great fit for your team. I'd love to set up a customized demo call with John, our account executive, who can walk you through exactly how this would work for your specific use case. Would you mind sharing your availability this week?",
                "persona": persona,
                "intent": "meeting_booking",
                "updated_lead_info": lead_info
            }
        
        # Extract new information
        company_info = self.extract_company_info(user_message)
        pain_point = self.extract_pain_points(user_message)
        budget_info = self.extract_budget_info(user_message)
        
        # Update lead info with extracted information
        updated_lead_info = lead_info.copy()
        if company_info:
            updated_lead_info.update(company_info)
        if pain_point:
            updated_lead_info["problem"] = pain_point
        if budget_info:
            updated_lead_info["budget"] = budget_info
        
        response_data = {
            "persona": persona,
            "intent": intent,
            "updated_lead_info": updated_lead_info,
            "next_questions": [],
            "knowledge_response": "",
            "objection_response": "",
            "recommended_action": "continue_qualification"
        }
        
        # Handle different intents
        if intent == "objection":
            objection_response = self.db.get_objection_response(user_message)
            if objection_response:
                response_data["objection_response"] = objection_response["response"]
        
        elif intent == "product_question":
            knowledge_results = self.db.search_knowledge_base(user_message, limit=3)
            if knowledge_results:
                response_data["knowledge_response"] = knowledge_results[0]["content"]
        
        # Get next qualification questions based on persona and current stage
        missing_info = self.get_missing_lead_info(updated_lead_info)
        if missing_info:
            questions = self.get_next_questions(persona, missing_info)
            response_data["next_questions"] = questions
        else:
            response_data["recommended_action"] = "ready_for_demo"
        
        return response_data
    
    def get_missing_lead_info(self, lead_info: Dict) -> List[str]:
        """Identify what lead information is still missing."""
        required_fields = ["company_name", "domain", "problem", "budget"]
        missing = []
        
        for field in required_fields:
            if not lead_info.get(field):
                missing.append(field)
        
        return missing
    
    def get_next_questions(self, persona: str, missing_info: List[str]) -> List[str]:
        """Get the next qualification questions to ask based on persona and missing info."""
        questions = []
        
        # Prioritize questions based on missing information
        for info_type in missing_info[:2]:  # Ask max 2 questions at a time
            if info_type == "company_name":
                category = "business_fit"
            elif info_type == "domain":
                category = "business_fit"
            elif info_type == "problem":
                category = "pain_points"
            elif info_type == "budget":
                category = "budget"
            else:
                continue
            
            question_results = self.db.get_qualification_questions(persona, category)
            if question_results:
                questions.append(question_results[0]["question"])
        
        return questions
    
    def generate_system_prompt(self, session_context: Dict, lead_info: Dict) -> str:
        """Generate a dynamic system prompt based on current session context."""
        
        # Determine completion status
        completion_percentage = self.calculate_completion_percentage(lead_info)
        missing_info = self.get_missing_lead_info(lead_info)
        
        # Base prompt
        prompt = """You are Jane, an AI SDR for Willow AI. You are professional, helpful, and focused on qualifying B2B leads.

CURRENT SESSION STATUS:
"""
        
        # Add lead info status
        prompt += f"Lead Qualification: {completion_percentage}% complete\n"
        if missing_info:
            prompt += f"Missing Information: {', '.join(missing_info)}\n"
        
        # Add context about the prospect
        if lead_info.get("company_name"):
            prompt += f"Prospect Company: {lead_info['company_name']}\n"
        if lead_info.get("domain"):
            prompt += f"Industry/Domain: {lead_info['domain']}\n"
        
        prompt += "\nRULES:\n"
        prompt += "1. Keep responses conversational and natural\n"
        prompt += "2. Ask only ONE qualification question at a time\n"
        prompt += "3. Listen for objections and address them with empathy\n"
        prompt += "4. Focus on the prospect's specific pain points\n"
        prompt += "5. Be concise - maximum 2-3 sentences per response\n"
        prompt += "6. Use the knowledge base to answer product questions accurately\n"
        
        # Add stage-specific guidance
        if completion_percentage < 25:
            prompt += "\nCURRENT FOCUS: Build rapport and understand their business\n"
        elif completion_percentage < 75:
            prompt += "\nCURRENT FOCUS: Qualify their needs and pain points\n"
        else:
            prompt += "\nCURRENT FOCUS: Confirm fit and move toward demo booking\n"
        
        return prompt
    
    def calculate_completion_percentage(self, lead_info: Dict) -> int:
        """Calculate what percentage of lead qualification is complete."""
        required_fields = ["company_name", "domain", "problem", "budget"]
        completed = sum(1 for field in required_fields if lead_info.get(field))
        return int((completed / len(required_fields)) * 100)
    
    def should_offer_demo(self, user_message: str, session_context: Dict) -> bool:
        """Determine if the agent should offer to show a demo based on user interest."""
        text_lower = user_message.lower()
        
        # Don't offer demo if we already asked for one recently
        agent_asked_demo = session_context.get("agent_asked_demo", False)
        if agent_asked_demo:
            return False
        
        # Keywords that indicate demo interest
        demo_interest_indicators = [
            "demo", "show me", "see it", "walkthrough", "preview", 
            "demonstration", "how it works", "see how", "product tour",
            "can you show", "i'd like to see", "want to see"
        ]
        
        return any(indicator in text_lower for indicator in demo_interest_indicators)
    
    def should_offer_meeting(self, user_message: str, lead_info: Dict) -> bool:
        """Determine if the agent should proactively offer a meeting based on user interest and lead qualification."""
        text_lower = user_message.lower()
        completion = self.calculate_completion_percentage(lead_info)
        
        # Meeting interest indicators
        meeting_interest_keywords = [
            "next step", "move forward", "interested", "good fit", "demo was great",
            "looks good", "this could work", "let's proceed", "sounds perfect",
            "exactly what we need", "when can we start", "pricing looks good",
            "this is helpful", "i like it", "looks promising", "perfect solution",
            "very interesting", "impressive", "sounds great", "this would work"
        ]
        
        # Demo completion indicators (positive response to demo)
        demo_completion_keywords = [
            "demo was", "after watching", "after seeing", "that demo", "the video",
            "the demonstration", "what i saw", "looks like", "seems like"
        ]
        
        # Check if user showed positive response to demo content
        has_demo_interest = any(keyword in text_lower for keyword in demo_completion_keywords)
        has_meeting_interest = any(keyword in text_lower for keyword in meeting_interest_keywords)
        
        # Offer meeting if:
        # 1. Lead is well qualified (>75% complete)
        # 2. User showed positive interest in demo or mentioned meeting-related keywords
        # 3. Demo was likely shown (check if demo_shown flag exists)
        demo_shown = lead_info.get("demo_shown", False)
        
        return (completion > 75 and 
                (has_meeting_interest or has_demo_interest) and
                demo_shown)

    def should_show_media(self, user_message: str, session_context: Dict) -> Optional[Dict]:
        """Determine if media should be shown based on the conversation context."""
        text_lower = user_message.lower()
        
        # Check for demo agreement/interest after agent asked for demo
        demo_interest_keywords = ["yes", "sure", "okay", "alright", "sounds good", "let's do it", "show me"]
        agent_asked_demo = session_context.get("agent_asked_demo", False)
        
        if agent_asked_demo and any(keyword in text_lower for keyword in demo_interest_keywords):
            return {"type": "demo", "topic": "product_overview"}
        
        # Media trigger keywords (removed automatic demo triggers)
        media_triggers = {
            "features": {"type": "features", "topic": "core_features"},
            "pricing": {"type": "pricing", "topic": "pricing_overview"},
            "testimonials": {"type": "testimonials", "topic": "customer_success"},
            "case study": {"type": "testimonials", "topic": "case_studies"},
            "integration": {"type": "features", "topic": "integrations"},
            "security": {"type": "features", "topic": "security"}
        }
        
        for trigger, media_info in media_triggers.items():
            if trigger in text_lower:
                return media_info
        
        return None
    
    def format_agent_response(self, response_data: Dict, user_message: str) -> str:
        """Format the final agent response based on all the context."""
        
        # Handle objections first
        if response_data.get("objection_response"):
            return response_data["objection_response"]
        
        # Handle demo offer (new separate message)
        if response_data.get("demo_offer"):
            return response_data["demo_offer"]
        
        # Handle demo responses
        if response_data.get("demo_response"):
            base_response = response_data["demo_response"]
            if response_data.get("follow_up"):
                base_response += f"\n\n{response_data['follow_up']}"
            return base_response
        
        # Handle meeting booking
        if response_data.get("meeting_response"):
            return response_data["meeting_response"]
        
        # Handle product questions
        if response_data.get("knowledge_response"):
            base_response = response_data["knowledge_response"]
            
            # Add a follow-up question if appropriate
            if response_data.get("next_questions"):
                base_response += f"\n\n{response_data['next_questions'][0]}"
            
            return base_response
        
        # Handle qualification flow
        if response_data.get("next_questions"):
            if len(response_data["next_questions"]) == 1:
                return response_data["next_questions"][0]
            else:
                return f"{response_data['next_questions'][0]} Also, {response_data['next_questions'][1].lower()}"
        
        # Default responses based on completion
        lead_info = response_data.get("updated_lead_info", {})
        completion = self.calculate_completion_percentage(lead_info)
        
        if completion >= 75:
            return "It sounds like Willow AI could be a great fit for your team! Would you like to see a quick demo of how it works?"
        elif completion >= 50:
            return "Thanks for sharing that information. Let me ask you one more thing to better understand your needs."
        else:
            return "I'd love to learn more about your current setup. Can you tell me about your company and what you do?"
