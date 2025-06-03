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
            "objection": ["but", "however", "already have", "don't need", "not interested", "too expensive"],
            "interest": ["interested", "tell me more", "sounds good", "like that", "demo", "meeting"],
            "qualification_info": ["we use", "our company", "we have", "currently", "right now"]
        }
    
    def detect_persona(self, text: str) -> str:
        """Detect the prospect's persona based on their input."""
        text_lower = text.lower()
        
        for persona, keywords in self.persona_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return persona
        
        return "general"
    
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
    
    def should_show_media(self, user_message: str, session_context: Dict) -> Optional[Dict]:
        """Determine if media should be shown based on the conversation context."""
        text_lower = user_message.lower()
        
        # Media trigger keywords
        media_triggers = {
            "demo": {"type": "demo", "topic": "product_overview"},
            "features": {"type": "features", "topic": "core_features"},
            "how it works": {"type": "demo", "topic": "how_it_works"},
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
        
        # Start with objection handling if needed
        if response_data.get("objection_response"):
            return response_data["objection_response"]
        
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
