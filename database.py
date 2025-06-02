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
            
            # Create indexes for better performance
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)")
            
            self.conn.commit()
            self.conn.sync()  # Sync after database initialization
            
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
                    "message_count": row[5]
                }
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