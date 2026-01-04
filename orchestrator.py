"""
Session orchestrator with AI-powered smart routing.

Manages multiple Claude Code sessions and automatically routes messages
to the appropriate project based on content analysis.
"""
import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import ANTHROPIC_API_KEY, DB_PATH

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A Claude Code session."""
    id: int
    name: str
    session_id: str  # Claude Code session ID
    description: str
    keywords: str  # Comma-separated keywords
    working_dir: str
    last_used: datetime
    created_at: datetime
    message_count: int


class SessionManager:
    """Manages Claude Code sessions in SQLite."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    session_id TEXT,
                    description TEXT DEFAULT '',
                    keywords TEXT DEFAULT '',
                    working_dir TEXT DEFAULT '',
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS message_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            conn.commit()

    def create_session(
        self,
        name: str,
        description: str = "",
        keywords: str = "",
        working_dir: str = ""
    ) -> Session:
        """Create a new session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (name, description, keywords, working_dir)
                VALUES (?, ?, ?, ?)
                """,
                (name, description, keywords, working_dir)
            )
            session_id = cursor.lastrowid
            conn.commit()

        return self.get_session_by_id(session_id)

    def get_session_by_id(self, session_id: int) -> Optional[Session]:
        """Get session by database ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()

        if row:
            return self._row_to_session(row)
        return None

    def get_session_by_name(self, name: str) -> Optional[Session]:
        """Get session by name."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sessions WHERE name = ?",
                (name,)
            ).fetchone()

        if row:
            return self._row_to_session(row)
        return None

    def get_all_sessions(self) -> list[Session]:
        """Get all sessions, ordered by last used."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY last_used DESC"
            ).fetchall()

        return [self._row_to_session(row) for row in rows]

    def get_recent_session(self) -> Optional[Session]:
        """Get the most recently used session."""
        sessions = self.get_all_sessions()
        return sessions[0] if sessions else None

    def update_session_id(self, db_id: int, claude_session_id: str):
        """Update the Claude Code session ID for a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET session_id = ?, last_used = ? WHERE id = ?",
                (claude_session_id, datetime.now(), db_id)
            )
            conn.commit()

    def update_last_used(self, db_id: int):
        """Update last used timestamp and increment message count."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE sessions
                SET last_used = ?, message_count = message_count + 1
                WHERE id = ?
                """,
                (datetime.now(), db_id)
            )
            conn.commit()

    def update_keywords(self, db_id: int, keywords: str):
        """Update keywords for a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET keywords = ? WHERE id = ?",
                (keywords, db_id)
            )
            conn.commit()

    def add_message_to_history(self, db_id: int, message: str):
        """Add message to history for context."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO message_history (session_id, message) VALUES (?, ?)",
                (db_id, message[:500])  # Truncate for storage
            )
            conn.commit()

    def get_recent_messages(self, db_id: int, limit: int = 5) -> list[str]:
        """Get recent messages for a session."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT message FROM message_history
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (db_id, limit)
            ).fetchall()
        return [row[0] for row in rows]

    def delete_session(self, db_id: int):
        """Delete a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM message_history WHERE session_id = ?", (db_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (db_id,))
            conn.commit()

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        """Convert database row to Session object."""
        return Session(
            id=row["id"],
            name=row["name"],
            session_id=row["session_id"] or "",
            description=row["description"] or "",
            keywords=row["keywords"] or "",
            working_dir=row["working_dir"] or "",
            last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else datetime.now(),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            message_count=row["message_count"] or 0,
        )


class SmartRouter:
    """AI-powered routing to determine which session a message belongs to."""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self._anthropic_client = None

    def _get_anthropic_client(self):
        """Lazy-load Anthropic client."""
        if self._anthropic_client is None and ANTHROPIC_API_KEY:
            try:
                import anthropic
                self._anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except ImportError:
                logger.warning("anthropic package not installed")
        return self._anthropic_client

    async def classify_message(self, message: str) -> Optional[Session]:
        """
        Determine which session a message belongs to.

        Uses AI to analyze the message content and match it to existing sessions.

        Args:
            message: The user's message

        Returns:
            Matched Session or None if should create new
        """
        sessions = self.session_manager.get_all_sessions()

        if not sessions:
            return None

        # Check for explicit project mentions first
        message_lower = message.lower()
        for session in sessions:
            # Check name match
            if session.name.lower() in message_lower:
                logger.info(f"Explicit name match: {session.name}")
                return session

            # Check keyword match
            if session.keywords:
                keywords = [k.strip().lower() for k in session.keywords.split(",")]
                for keyword in keywords:
                    if keyword and keyword in message_lower:
                        logger.info(f"Keyword match '{keyword}': {session.name}")
                        return session

        # If only one session, use it
        if len(sessions) == 1:
            return sessions[0]

        # Try AI classification if available
        client = self._get_anthropic_client()
        if client:
            return await self._ai_classify(message, sessions)

        # Fall back to most recent
        logger.info("No match found, using most recent session")
        return sessions[0]

    async def _ai_classify(self, message: str, sessions: list[Session]) -> Optional[Session]:
        """Use Claude API to classify which session a message belongs to."""
        try:
            # Build session descriptions
            session_info = []
            for s in sessions[:10]:  # Limit to 10 most recent
                recent_msgs = self.session_manager.get_recent_messages(s.id, 3)
                info = f"- {s.id}: {s.name}"
                if s.description:
                    info += f" - {s.description}"
                if s.keywords:
                    info += f" (keywords: {s.keywords})"
                if recent_msgs:
                    info += f" (recent: {recent_msgs[0][:50]}...)"
                session_info.append(info)

            prompt = f"""Analyze this message and determine which project session it most likely belongs to.

Message: "{message}"

Available sessions:
{chr(10).join(session_info)}

Respond with ONLY the session ID number, or "new" if this seems unrelated to any existing session.
Just the number or "new", nothing else."""

            # Run in thread pool to not block
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._anthropic_client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=10,
                    messages=[{"role": "user", "content": prompt}]
                )
            )

            result = response.content[0].text.strip().lower()
            logger.info(f"AI classification result: {result}")

            if result == "new":
                return None

            try:
                session_id = int(result)
                return self.session_manager.get_session_by_id(session_id)
            except ValueError:
                # Couldn't parse, fall back to recent
                return sessions[0]

        except Exception as e:
            logger.exception(f"AI classification error: {e}")
            return sessions[0]  # Fall back to most recent

    def extract_keywords(self, message: str, response: str) -> list[str]:
        """Extract potential keywords from message and response for future matching."""
        # Simple keyword extraction - could be enhanced with NLP
        keywords = set()

        # Look for project-like names (capitalized words)
        import re
        for word in re.findall(r'\b[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*\b', message + " " + response):
            if len(word) > 2:
                keywords.add(word.lower())

        # Look for file paths
        for path in re.findall(r'[\w/]+\.(py|js|ts|tsx|kt|swift|go|rs)\b', message + " " + response):
            parts = path.split("/")
            if parts:
                keywords.add(parts[-1].split(".")[0].lower())

        return list(keywords)[:5]  # Limit to 5 keywords


# Global instances
_session_manager: Optional[SessionManager] = None
_router: Optional[SmartRouter] = None


def get_session_manager() -> SessionManager:
    """Get or create the session manager singleton."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def get_router() -> SmartRouter:
    """Get or create the router singleton."""
    global _router
    if _router is None:
        _router = SmartRouter(get_session_manager())
    return _router


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    sm = SessionManager()

    # Create test sessions
    s1 = sm.create_session("MiniNews", description="News app", keywords="minews,podcast,audio")
    s2 = sm.create_session("ElderCare", description="Voice companion", keywords="elderly,voice,aosp")

    print("Sessions:")
    for s in sm.get_all_sessions():
        print(f"  {s.id}: {s.name} - {s.description}")

    # Test routing
    router = SmartRouter(sm)

    async def test():
        result = await router.classify_message("Fix the bug in MiniNews audio player")
        print(f"Routed to: {result.name if result else 'new session'}")

    asyncio.run(test())
