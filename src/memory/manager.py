"""
MemoryManager — 슬라이딩 윈도우 대화 기록.

순수 Python 구현 (LangChain 의존성 없음).
SQLite로 전체 대화 영속 저장.
파일 I/O는 asyncio.to_thread()로 비동기 처리.

선택적 LLM 요약 압축:
  summarizer가 주입되면, 버퍼가 window_turns를 초과할 때
  오래된 절반 턴을 LLM 요약으로 압축해 한 줄로 보존.
  summarizer가 없으면(기본) 오래된 턴 단순 폐기.

트레이드오프:
  요약 ON  → 장기 컨텍스트 보존, 추가 LLM 호출 비용 (M1 ~1-2초)
  요약 OFF → 빠름, 최근 N턴만 유지 (기본값)
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.models.adapter import Message
from src.config import settings

if TYPE_CHECKING:
    from src.models.adapter import ModelAdapterBase

_SUMMARY_PROMPT = """\
Summarize the following conversation turns into 1-2 sentences. \
Be concise. Preserve key facts, decisions, and code context.

Conversation:
{turns}

Summary:"""


class MemoryManager:
    def __init__(
        self,
        db_path: str | None = None,
        max_tokens: int = 1500,
        window_turns: int | None = None,
        summarizer: "ModelAdapterBase | None" = None,
    ) -> None:
        self._db_path = Path(db_path or settings.MEMORY_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_tokens = max_tokens
        self._window_turns = window_turns or settings.MEMORY_WINDOW_TURNS
        self._summarizer = summarizer          # None이면 요약 비활성화
        self._summary: str = ""               # 압축된 이전 대화 요약
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
        """
        토큰 예산 내 메시지 반환.
        요약본이 있으면 가장 앞에 system 메시지로 포함.
        """
        budget = max_tokens or self._max_tokens
        result: list[Message] = []
        token_count = 0

        # 최신 메시지 우선 역순 수집
        for msg in reversed(self._buffer):
            tokens = len(msg.content.split())
            if token_count + tokens > budget:
                break
            result.insert(0, msg)
            token_count += tokens

        # 요약본 prepend
        if self._summary:
            summary_msg = Message(
                role="system",
                content=f"[Previous conversation summary]\n{self._summary}",
            )
            result.insert(0, summary_msg)

        return result

    async def update(
        self,
        user_input: str,
        assistant_response: str,
        session: str = "default",
    ) -> None:
        """대화 추가 + 윈도우 유지 + SQLite 비동기 저장."""
        new_msgs = [
            Message(role="user", content=user_input),
            Message(role="assistant", content=assistant_response),
        ]
        self._buffer.extend(new_msgs)

        max_msgs = self._window_turns * 2
        if len(self._buffer) > max_msgs:
            if self._summarizer is not None:
                await self._summarize_oldest()
            else:
                # 요약 없이 단순 폐기
                self._buffer = self._buffer[-max_msgs:]

        await asyncio.to_thread(self._save_to_db, new_msgs, session)

    def clear(self) -> None:
        self._buffer.clear()
        self._summary = ""

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

    async def _summarize_oldest(self) -> None:
        """
        버퍼 앞쪽 절반을 LLM으로 요약 후 _summary에 누적.
        요약 실패 시 조용히 단순 폐기로 폴백.
        """
        half = len(self._buffer) // 2
        to_summarize = self._buffer[:half]
        self._buffer = self._buffer[half:]

        turns_text = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in to_summarize
        )
        prompt = _SUMMARY_PROMPT.format(turns=turns_text[:2000])

        try:
            result = await self._summarizer.chat(  # type: ignore[union-attr]
                [Message(role="user", content=prompt)],
                stream=False,
            )
            new_summary = result.content.strip()
            # 기존 요약과 합산 (너무 길면 앞 300자만 유지)
            if self._summary:
                combined = f"{self._summary} | {new_summary}"
                self._summary = combined[:600]
            else:
                self._summary = new_summary
        except Exception:
            pass  # 요약 실패 → 이미 버퍼에서 제거됐으므로 폐기

    def _save_to_db(self, messages: list[Message], session: str) -> None:
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(
                "INSERT INTO messages (session, role, content, ts) VALUES (?, ?, ?, ?)",
                [(session, m.role, m.content, now) for m in messages],
            )
