"""
MemoryManager — 슬라이딩 윈도우 대화 기록.

순수 Python 구현 (LangChain 의존성 없음).
SQLite로 전체 대화 영속 저장.
파일 I/O는 asyncio.to_thread()로 비동기 처리.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

from src.models.adapter import Message
from src.config import settings


class MemoryManager:
    def __init__(
        self,
        db_path: str | None = None,
        max_tokens: int = 1500,
        window_turns: int | None = None,
    ) -> None:
        self._db_path = Path(db_path or settings.MEMORY_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_tokens = max_tokens
        self._window_turns = window_turns or settings.MEMORY_WINDOW_TURNS
        self._buffer: list[Message] = []
        self._init_db()

    # ------------------------------------------------------------------
    # DB 초기화
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    session   TEXT    NOT NULL DEFAULT 'default',
                    role      TEXT    NOT NULL,
                    content   TEXT    NOT NULL,
                    ts        REAL    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session, id)")

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    async def get_compressed(self, max_tokens: int | None = None) -> list[Message]:
        """토큰 예산 내 최신 메시지 우선 반환."""
        budget = max_tokens or self._max_tokens
        result: list[Message] = []
        token_count = 0
        for msg in reversed(self._buffer):
            tokens = len(msg.content.split())
            if token_count + tokens > budget:
                break
            result.insert(0, msg)
            token_count += tokens
        return result

    async def update(
        self,
        user_input: str,
        assistant_response: str,
        session: str = "default",
    ) -> None:
        """대화 추가 + 슬라이딩 윈도우 유지 + SQLite 비동기 저장."""
        new_msgs = [
            Message(role="user", content=user_input),
            Message(role="assistant", content=assistant_response),
        ]
        self._buffer.extend(new_msgs)

        # 윈도우 초과 시 오래된 턴 제거
        max_msgs = self._window_turns * 2
        if len(self._buffer) > max_msgs:
            self._buffer = self._buffer[-max_msgs:]

        await asyncio.to_thread(self._save_to_db, new_msgs, session)

    def clear(self) -> None:
        self._buffer.clear()

    def load_session(self, session: str = "default", last_n: int = 20) -> None:
        """재시작 후 DB에서 최근 세션 복원."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session=? ORDER BY id DESC LIMIT ?",
                (session, last_n),
            ).fetchall()
        self._buffer = [Message(role=r, content=c) for r, c in reversed(rows)]

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _save_to_db(self, messages: list[Message], session: str) -> None:
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(
                "INSERT INTO messages (session, role, content, ts) VALUES (?, ?, ?, ?)",
                [(session, m.role, m.content, now) for m in messages],
            )
