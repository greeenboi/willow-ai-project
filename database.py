import libsql_experimental as libsql
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages Turso database operations for agent memory persistence."""
    
    def __init__(self, local_db_path: str = "agent_memory.db"):
        self.local_db_path = local_db_path
        self.url = os.getenv("TURSO_DATABASE_URL")
        self.auth_token = os.getenv("TURSO_AUTH_TOKEN")
        
        if not self.url or not self.auth_token:
            raise ValueError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set in environment variables")
        
        # Use local replica with cloud sync pattern as specified by user
        self.conn = libsql.connect(self.local_db_path, sync_url=self.url, auth_token=self.auth_token)
        self.conn.sync()  # Sync with remote database on initialization
        self.init_database()

    def init_database(self):
        """Initialize the database with required tables."""
        try:
            # Create sessions table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    lead_info TEXT,
                    current_stage TEXT DEFAULT 'greeting'
                )
            """)
            
            # Create chat_history table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    speaker TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_type TEXT DEFAULT 'text',
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
            """)
              # Create media_interactions table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS media_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    media_type TEXT,
                    media_topic TEXT,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
            """)
            
            # Create knowledge_base table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    keywords TEXT,
                    priority INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create qualification_questions table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS qualification_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    persona TEXT NOT NULL,
                    category TEXT NOT NULL,
                    question TEXT NOT NULL,
                    priority INTEGER DEFAULT 1,
                    stage TEXT DEFAULT 'qualification',
                    follow_up_questions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create objection_responses table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS objection_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    objection_category TEXT NOT NULL,
                    objection_text TEXT NOT NULL,
                    response TEXT NOT NULL,
                    alternative_responses TEXT,
                    priority INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_base_category ON knowledge_base(category)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_base_keywords ON knowledge_base(keywords)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_qualification_questions_persona ON qualification_questions(persona)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_objection_responses_category ON objection_responses(objection_category)")            
            self.conn.commit()
            self.conn.sync()  # Sync after database initialization
            
            # Initialize knowledge base with default data
            self.populate_default_knowledge()
            
            logger.info("Turso database initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def create_session(self, session_id: str, lead_info: Dict = None) -> bool:
        """Create a new session in the database."""
        try:
            lead_info_json = json.dumps(lead_info) if lead_info else json.dumps({
                "company_name": None,
                "domain": None,
                "problem": None,
                "budget": None
            })
            
            self.conn.execute("""
                INSERT OR REPLACE INTO sessions (session_id, lead_info, created_at, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (session_id, lead_info_json))
            
            self.conn.commit()
            self.conn.sync()  # Sync after commit
            
            logger.info(f"Created session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Retrieve session information from the database."""
        try:
            result = self.conn.execute("""
                SELECT session_id, created_at, updated_at, status, lead_info, current_stage
                FROM sessions WHERE session_id = ?
            """, (session_id,))
            
            row = result.fetchone()
            if row:
                return {
                    "session_id": row[0],
                    "created_at": row[1],
                    "updated_at": row[2],
                    "status": row[3],
                    "lead_info": json.loads(row[4]) if row[4] else {},
                    "current_stage": row[5]
                }
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving session {session_id}: {e}")
            return None

    def update_session(self, session_id: str, lead_info: Dict = None, current_stage: str = None) -> bool:
        """Update session information."""
        try:
            # Get current session data
            current_session = self.get_session(session_id)
            if not current_session:
                return False
            
            # Update lead_info if provided
            if lead_info is not None:
                current_lead_info = current_session.get("lead_info", {})
                current_lead_info.update(lead_info)
                lead_info_json = json.dumps(current_lead_info)
            else:
                lead_info_json = json.dumps(current_session.get("lead_info", {}))
            
            # Update current_stage if provided
            if current_stage is None:
                current_stage = current_session.get("current_stage", "greeting")
            
            self.conn.execute("""
                UPDATE sessions 
                SET lead_info = ?, current_stage = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (lead_info_json, current_stage, session_id))
            
            self.conn.commit()
            self.conn.sync()  # Sync after commit
            
            logger.info(f"Updated session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {e}")
            return False

    def add_message(self, session_id: str, speaker: str, message: str, message_type: str = "text") -> bool:
        """Add a message to chat history."""
        try:
            self.conn.execute("""
                INSERT INTO chat_history (session_id, speaker, message, message_type)
                VALUES (?, ?, ?, ?)
            """, (session_id, speaker, message, message_type))
            
            self.conn.commit()
            self.conn.sync()  # Sync after commit
            
            logger.debug(f"Added message to session {session_id}: {speaker[:10]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error adding message to session {session_id}: {e}")
            return False

    def get_chat_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Retrieve chat history for a session."""
        try:
            result = self.conn.execute("""
                SELECT speaker, message, timestamp, message_type
                FROM chat_history 
                WHERE session_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (session_id, limit))
            
            rows = result.fetchall()
            return [
                {
                    "speaker": row[0],
                    "message": row[1],
                    "timestamp": row[2],
                    "message_type": row[3]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving chat history for session {session_id}: {e}")
            return []

    def log_media_interaction(self, session_id: str, media_type: str, media_topic: str) -> bool:
        """Log media interaction."""
        try:
            self.conn.execute("""
                INSERT INTO media_interactions (session_id, media_type, media_topic)
                VALUES (?, ?, ?)
            """, (session_id, media_type, media_topic))
            
            self.conn.commit()
            self.conn.sync()  # Sync after commit
            
            logger.info(f"Logged media interaction: {media_type}/{media_topic} for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error logging media interaction for session {session_id}: {e}")
            return False

    def get_session_summary(self, session_id: str) -> Dict:
        """Get a comprehensive summary of a session."""
        try:
            session = self.get_session(session_id)
            if not session:
                return {}
            
            chat_history = self.get_chat_history(session_id)
            
            # Calculate summary statistics
            total_messages = len(chat_history)
            user_messages = len([msg for msg in chat_history if msg["speaker"] == "user"])
            agent_messages = len([msg for msg in chat_history if msg["speaker"] == "agent"])
            
            # Get lead info completion
            lead_info = session.get("lead_info", {})
            filled_fields = sum(1 for v in lead_info.values() if v is not None)
            total_fields = len(lead_info)
            completion_percentage = (filled_fields / total_fields * 100) if total_fields > 0 else 0
            
            return {
                "session_id": session_id,
                "created_at": session["created_at"],
                "updated_at": session["updated_at"],
                "status": session["status"],
                "current_stage": session["current_stage"],
                "lead_info": lead_info,
                "lead_completion_percentage": completion_percentage,
                "total_messages": total_messages,
                "user_messages": user_messages,
                "agent_messages": agent_messages,
                "chat_history": chat_history
            }
            
        except Exception as e:
            logger.error(f"Error getting session summary for {session_id}: {e}")
            return {}

    def get_all_sessions(self, limit: int = 100) -> List[Dict]:
        """Get all sessions with basic info."""
        try:
            result = self.conn.execute("""
                SELECT s.session_id, s.created_at, s.updated_at, s.status, s.lead_info,
                       COUNT(ch.id) as message_count
                FROM sessions s
                LEFT JOIN chat_history ch ON s.session_id = ch.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
            """, (limit,))
            
            rows = result.fetchall()
            return [
                {
                    "session_id": row[0],
                    "created_at": row[1],
                    "updated_at": row[2],
                    "status": row[3],
                    "lead_info": json.loads(row[4]) if row[4] else {},
                    "message_count": row[5]                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving all sessions: {e}")
            return []

    def close_session(self, session_id: str) -> bool:
        """Mark a session as closed."""
        try:
            self.conn.execute("""
                UPDATE sessions 
                SET status = 'closed', updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (session_id,))
            
            self.conn.commit()
            self.conn.sync()  # Sync after commit
            
            logger.info(f"Closed session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}")
            return False
            
    def close(self):
        """Close the database connection."""
        try:
            if self.conn:
                self.conn.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")
    
    # Knowledge Base Methods
    def populate_default_knowledge(self):
        """Populate the database with default knowledge base, questions, and objection responses."""
        try:
            # Check if knowledge base is already populated
            result = self.conn.execute("SELECT COUNT(*) FROM knowledge_base")
            count = result.fetchone()[0]
            
            if count > 0:
                logger.info("Knowledge base already populated")
                return
            
            # Willow AI Knowledge Base
            knowledge_entries = [
                {
                    "category": "product_overview",
                    "topic": "what_is_willow_ai",
                    "content": "Willow AI is an AI-powered sales agent designed to engage, qualify, and convert inbound leads for B2B companies. It acts like an SDR that instantly engages website visitors, qualifies them through natural conversations, and either books sales calls or provides demos in real-time.",
                    "keywords": "willow ai, ai sales agent, sdr, lead qualification, b2b sales"
                },
                {
                    "category": "product_features",
                    "topic": "instant_engagement",
                    "content": "Willow AI engages website visitors instantly - no waiting for human SDRs. It starts conversations immediately when prospects visit your site, preventing lead drop-off and ensuring maximum engagement rates.",
                    "keywords": "instant engagement, real-time, website visitors, lead drop-off, engagement rates"
                },
                {
                    "category": "product_features",
                    "topic": "intelligent_qualification",
                    "content": "The AI qualifies leads using natural conversation, asking relevant questions based on the prospect's role and company. It can identify decision-makers, understand budget, timeline, and pain points just like a human SDR.",
                    "keywords": "lead qualification, natural conversation, decision makers, budget, timeline, pain points"
                },
                {
                    "category": "product_features",
                    "topic": "crm_integration",
                    "content": "Willow AI integrates seamlessly with popular CRMs like Salesforce, HubSpot, and Pipedrive. All conversations, lead data, and qualification notes are automatically synced to your CRM for full visibility.",
                    "keywords": "crm integration, salesforce, hubspot, pipedrive, lead data, conversation sync"
                },
                {
                    "category": "product_features",
                    "topic": "meeting_booking",
                    "content": "Qualified leads can book meetings directly through Willow AI. It integrates with calendar systems and can schedule demos or sales calls based on your team's availability.",
                    "keywords": "meeting booking, calendar integration, demo scheduling, sales calls, availability"
                },
                {
                    "category": "benefits",
                    "topic": "increased_conversion",
                    "content": "Companies using Willow AI see 3-5x higher conversion rates from website visitors to qualified leads. The instant engagement and human-like conversation significantly reduces bounce rates.",
                    "keywords": "conversion rates, qualified leads, bounce rates, website visitors, performance metrics"
                },
                {
                    "category": "benefits",
                    "topic": "sdr_efficiency",
                    "content": "Willow AI handles initial qualification, allowing your human SDRs to focus on high-value activities like closing deals and building relationships with qualified prospects.",
                    "keywords": "sdr efficiency, initial qualification, closing deals, relationships, qualified prospects"
                },
                {
                    "category": "benefits",
                    "topic": "24_7_availability",
                    "content": "Unlike human SDRs, Willow AI works 24/7 across all time zones. International prospects get immediate attention, and you never miss leads due to time differences or after-hours inquiries.",
                    "keywords": "24/7 availability, time zones, international prospects, after hours, global coverage"
                },
                {
                    "category": "technical",
                    "topic": "implementation",
                    "content": "Willow AI can be implemented in under 24 hours. It's a simple widget that integrates with your website, requiring minimal technical setup. Our team handles the configuration and training.",
                    "keywords": "implementation, 24 hours, website widget, technical setup, configuration, training"
                },
                {
                    "category": "technical",
                    "topic": "security",
                    "content": "Willow AI is SOC 2 compliant and uses enterprise-grade security. All data is encrypted in transit and at rest. We follow GDPR and CCPA compliance standards.",
                    "keywords": "soc 2, security, encryption, gdpr, ccpa, compliance, data protection"
                },
                {
                    "category": "pricing",
                    "topic": "value_proposition",
                    "content": "Willow AI typically pays for itself within the first month through increased lead conversion. Most customers see ROI of 300-500% in the first quarter.",
                    "keywords": "roi, value proposition, lead conversion, cost savings, first month, quarterly results"
                },
                {
                    "category": "competitive",
                    "topic": "vs_chatbots",
                    "content": "Unlike traditional chatbots that just collect emails, Willow AI conducts full sales conversations, handles objections, and makes qualification decisions. It's like having a top-performing SDR available 24/7.",
                    "keywords": "chatbots, email collection, sales conversations, objection handling, qualification decisions"
                }
            ]
            
            # Qualification Questions by Persona
            qualification_questions = [
                # VP of Sales / Head of Sales
                {
                    "persona": "vp_sales",
                    "category": "business_fit",
                    "question": "How does your sales team currently handle inbound leads from your website?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "vp_sales",
                    "category": "pain_points",
                    "question": "What's your biggest challenge in converting website visitors into qualified sales meetings?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "vp_sales",
                    "category": "current_process",
                    "question": "Do you have SDRs qualifying leads, or do your AEs handle them directly?",
                    "priority": 2,
                    "stage": "qualification"
                },
                {
                    "persona": "vp_sales",
                    "category": "metrics",
                    "question": "What's your current conversion rate from website visitors to booked meetings?",
                    "priority": 2,
                    "stage": "qualification"
                },
                
                # Sales Ops / RevOps Managers
                {
                    "persona": "sales_ops",
                    "category": "automation",
                    "question": "Are you currently using any AI automation in your sales funnel?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "sales_ops",
                    "category": "tools",
                    "question": "What CRM and sales tools is your team currently using?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "sales_ops",
                    "category": "integration",
                    "question": "How important is seamless CRM integration for your sales process?",
                    "priority": 2,
                    "stage": "qualification"
                },
                
                # Marketing Leaders
                {
                    "persona": "marketing_leader",
                    "category": "lead_generation",
                    "question": "What's your current strategy for converting website traffic into leads?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "marketing_leader",
                    "category": "conversion_optimization",
                    "question": "Are you facing drop-offs because prospects don't want to fill out demo forms?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "marketing_leader",
                    "category": "attribution",
                    "question": "How do you currently track and attribute website conversions to revenue?",
                    "priority": 2,
                    "stage": "qualification"
                },
                
                # PLG Founders
                {
                    "persona": "plg_founder",
                    "category": "self_serve",
                    "question": "How do you currently balance self-serve signup with sales-assisted conversions?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "plg_founder",
                    "category": "product_qualified_leads",
                    "question": "Do you have a process for identifying when product users are ready for sales conversations?",
                    "priority": 1,
                    "stage": "qualification"
                },
                
                # General Budget and Timeline Questions
                {
                    "persona": "general",
                    "category": "budget",
                    "question": "Do you have a budget allocated for AI or sales automation tools this quarter?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "general",
                    "category": "timeline",
                    "question": "Are you actively looking for solutions to improve inbound lead conversion?",
                    "priority": 1,
                    "stage": "qualification"
                },
                {
                    "persona": "general",
                    "category": "decision_making",
                    "question": "Who else would be involved in evaluating a solution like this?",
                    "priority": 2,
                    "stage": "qualification"
                }
            ]
            
            # Objection Responses
            objection_responses = [
                {
                    "objection_category": "existing_chatbot",
                    "objection_text": "We already use a chatbot like Drift/Intercom",
                    "response": "That's great! Unlike traditional chatbots, Willow AI doesn't just collect emails—it actually talks to leads, qualifies them like an SDR, and schedules meetings automatically. Have you seen gaps in your current chatbot where leads still fall through?",
                    "priority": 1
                },
                {
                    "objection_category": "prefer_human",
                    "objection_text": "We prefer human SDRs for qualification",
                    "response": "Willow AI isn't replacing SDRs—it's making them more efficient. Instead of spending time on repetitive qualification, your reps can focus on closing high-intent leads. Think of it as your best SDR working 24/7 to pre-qualify prospects.",
                    "priority": 1
                },
                {
                    "objection_category": "personal_touch",
                    "objection_text": "Our leads need a personal touch, AI won't work",
                    "response": "That's exactly why we designed Willow AI to sound human-like and handle objections dynamically. It's trained on thousands of sales conversations, so it engages naturally, just like your best SDR would. Most prospects don't even realize they're talking to AI initially.",
                    "priority": 1
                },
                {
                    "objection_category": "ai_mistakes",
                    "objection_text": "What if AI makes mistakes in qualification?",
                    "response": "You define the qualification criteria, and Willow AI follows those rules consistently. It can even flag leads for manual review if they need further evaluation. Plus, it never has a bad day or forgets to ask important questions like humans might.",
                    "priority": 1
                },
                {
                    "objection_category": "budget",
                    "objection_text": "This sounds interesting, but we don't have budget",
                    "response": "I understand! Many of our customers see a fast ROI because Willow AI increases inbound conversion rates and reduces SDR workload. Would it make sense to explore a pilot program to see the impact firsthand? Most clients see results within the first month.",
                    "priority": 1
                },
                {
                    "objection_category": "timing",
                    "objection_text": "Not the right time for us",
                    "response": "I get that timing is important. What would need to change to make this a priority? Often companies wait until they're losing too many leads, but implementing Willow AI early helps capture that missed revenue. What's driving your current lead generation efforts?",
                    "priority": 1
                },
                {
                    "objection_category": "technical_concerns",
                    "objection_text": "Implementation seems complex",
                    "response": "Actually, it's quite simple! Willow AI can be implemented in under 24 hours with just a small widget on your website. Our team handles all the configuration and training. Most clients are surprised how easy the setup process is.",
                    "priority": 1
                },
                {
                    "objection_category": "need_approval",
                    "objection_text": "I need to discuss this with my team",
                    "response": "Absolutely, that makes sense. What specific aspects would you want to discuss with them? I can provide materials that address common questions, or would it be helpful to set up a brief demo for the broader team to see Willow AI in action?",
                    "priority": 1
                }
            ]
            
            # Insert knowledge base entries
            for entry in knowledge_entries:
                self.conn.execute("""
                    INSERT INTO knowledge_base (category, topic, content, keywords, priority)
                    VALUES (?, ?, ?, ?, ?)
                """, (entry["category"], entry["topic"], entry["content"], entry["keywords"], entry.get("priority", 1)))
            
            # Insert qualification questions
            for question in qualification_questions:
                self.conn.execute("""
                    INSERT INTO qualification_questions (persona, category, question, priority, stage)
                    VALUES (?, ?, ?, ?, ?)
                """, (question["persona"], question["category"], question["question"], question["priority"], question["stage"]))
            
            # Insert objection responses
            for objection in objection_responses:
                self.conn.execute("""
                    INSERT INTO objection_responses (objection_category, objection_text, response, priority)
                    VALUES (?, ?, ?, ?)
                """, (objection["objection_category"], objection["objection_text"], objection["response"], objection["priority"]))
            
            self.conn.commit()
            self.conn.sync()
            
            logger.info("Default knowledge base populated successfully")
            
        except Exception as e:
            logger.error(f"Error populating default knowledge: {e}")
    
    def search_knowledge_base(self, query: str, category: str = None, limit: int = 5) -> List[Dict]:
        """Search the knowledge base for relevant information."""
        try:
            query_lower = query.lower()
            
            if category:
                result = self.conn.execute("""
                    SELECT id, category, topic, content, keywords, priority
                    FROM knowledge_base 
                    WHERE category = ? AND (
                        LOWER(content) LIKE ? OR 
                        LOWER(keywords) LIKE ? OR 
                        LOWER(topic) LIKE ?
                    )
                    ORDER BY priority DESC, id ASC
                    LIMIT ?
                """, (category, f"%{query_lower}%", f"%{query_lower}%", f"%{query_lower}%", limit))
            else:
                result = self.conn.execute("""
                    SELECT id, category, topic, content, keywords, priority
                    FROM knowledge_base 
                    WHERE LOWER(content) LIKE ? OR 
                          LOWER(keywords) LIKE ? OR 
                          LOWER(topic) LIKE ?
                    ORDER BY priority DESC, id ASC
                    LIMIT ?
                """, (f"%{query_lower}%", f"%{query_lower}%", f"%{query_lower}%", limit))
            
            rows = result.fetchall()
            return [
                {
                    "id": row[0],
                    "category": row[1],
                    "topic": row[2],
                    "content": row[3],
                    "keywords": row[4],
                    "priority": row[5]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []
    
    def get_qualification_questions(self, persona: str = None, category: str = None) -> List[Dict]:
        """Get qualification questions for a specific persona or category."""
        try:
            if persona and category:
                result = self.conn.execute("""
                    SELECT id, persona, category, question, priority, stage
                    FROM qualification_questions
                    WHERE persona = ? AND category = ?
                    ORDER BY priority DESC, id ASC
                """, (persona, category))
            elif persona:
                result = self.conn.execute("""
                    SELECT id, persona, category, question, priority, stage
                    FROM qualification_questions
                    WHERE persona = ? OR persona = 'general'
                    ORDER BY priority DESC, id ASC
                """, (persona,))
            elif category:
                result = self.conn.execute("""
                    SELECT id, persona, category, question, priority, stage
                    FROM qualification_questions
                    WHERE category = ?
                    ORDER BY priority DESC, id ASC
                """, (category,))
            else:
                result = self.conn.execute("""
                    SELECT id, persona, category, question, priority, stage
                    FROM qualification_questions
                    ORDER BY priority DESC, id ASC
                """)
            
            rows = result.fetchall()
            return [
                {
                    "id": row[0],
                    "persona": row[1],
                    "category": row[2],
                    "question": row[3],
                    "priority": row[4],
                    "stage": row[5]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error getting qualification questions: {e}")
            return []
    
    def get_objection_response(self, objection_text: str) -> Dict:
        """Get response for a specific objection."""
        try:
            objection_lower = objection_text.lower()
            
            result = self.conn.execute("""
                SELECT id, objection_category, objection_text, response, priority
                FROM objection_responses
                WHERE LOWER(objection_text) LIKE ? OR LOWER(objection_category) LIKE ?
                ORDER BY priority DESC, id ASC
                LIMIT 1
            """, (f"%{objection_lower}%", f"%{objection_lower}%"))
            
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "objection_category": row[1],
                    "objection_text": row[2],
                    "response": row[3],
                    "priority": row[4]
                }
            return {}
            
        except Exception as e:
            logger.error(f"Error getting objection response: {e}")
            return {}
    
    def add_knowledge_entry(self, category: str, topic: str, content: str, keywords: str = "", priority: int = 1) -> bool:
        """Add a new knowledge base entry."""
        try:
            self.conn.execute("""
                INSERT INTO knowledge_base (category, topic, content, keywords, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (category, topic, content, keywords, priority))
            
            self.conn.commit()
            self.conn.sync()
            
            logger.info(f"Added knowledge entry: {category}/{topic}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding knowledge entry: {e}")
            return False
    
    def update_lead_qualification_stage(self, session_id: str, stage: str) -> bool:
        """Update the qualification stage for a session."""
        return self.update_session(session_id, current_stage=stage)