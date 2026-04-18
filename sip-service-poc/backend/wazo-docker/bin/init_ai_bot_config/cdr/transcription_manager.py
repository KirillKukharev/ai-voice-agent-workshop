"""
Transcription Manager
Manages AI Bot transcription operations
"""

import json
import logging
from datetime import datetime
from typing import Any

from config.models import ConversationRole

logger = logging.getLogger(__name__)


class TranscriptionManager:
    """Manages transcription caching and persistence"""

    def __init__(self) -> None:
        """
        Initialize Transcription Manager

        Args:
            db_pool: asyncpg connection pool (optional)
        """
        self.db_pool = None
        self._memory_cache: dict[str, list[dict[str, Any]]] = {}

    def _get_connection(self):
        """
        Get database connection (async context manager)

        Returns:
            Connection context manager
        """
        if self.db_pool:
            return self.db_pool.acquire()
        else:

            class ConnectionContext:
                def __init__(self):
                    self.conn = None

                async def __aenter__(self):
                    import asyncpg

                    self.conn = await asyncpg.connect(
                        host="postgres",
                        port=5432,
                        user="asterisk",
                        password="changeme",
                        database="wazo",
                    )
                    return self.conn

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    if self.conn:
                        await self.conn.close()

            return ConnectionContext()

    def cache_transcription(
        self,
        *,
        role: str,
        content: str,
        channel_id: str,
        call_id: str,
        stt_engine: str | None = None,
        llm_model: str | None = None,
        token_count: int | None = None,
        tenant_uuid: str | None = None,
    ) -> None:
        """
        Cache transcription data in memory

        Args:
            role: Conversation role (USER/ASSISTANT)
            content: Transcription content
            channel_id: Channel ID
            call_id: Call ID
            stt_engine: STT engine name
            llm_model: LLM model name
            token_count: Token count for LLM responses
            tenant_uuid: Tenant UUID
        """
        # Create JSON content with all data
        now = datetime.now()
        transcription_data = {
            "question": content if role == ConversationRole.USER else None,
            "answer": content if role == ConversationRole.ASSISTANT else None,
            "channel_id": channel_id,
            "call_id": call_id or f"ai_bot_{channel_id}_{int(now.timestamp())}",
            "user_uuid": "ai_bot_user",
            "tenant_uuid": str(tenant_uuid) if tenant_uuid else None,
            "stt_engine": stt_engine,
            "llm_model": llm_model,
            "token_count": token_count,
            "role": role,
            "timestamp": now.isoformat(),
        }

        if channel_id not in self._memory_cache:
            self._memory_cache[channel_id] = []
        self._memory_cache[channel_id].append(transcription_data)

        logger.debug(f"Cached transcription role={role} for channel={channel_id}")

    async def save_cached_transcriptions(self, channel_id: str) -> bool:
        """
        Save all cached transcriptions for a channel to database

        Args:
            channel_id: Channel ID

        Returns:
            True if successful, False otherwise
        """
        if not self.db_pool:
            logger.info("DB pool is not initialized; cannot save transcriptions to DB")
            return False

        if channel_id not in self._memory_cache:
            logger.info(f"No cached transcriptions for channel_id={channel_id}")
            return True

        cached_transcriptions = self._memory_cache[channel_id]
        if not cached_transcriptions:
            logger.info(f"Empty transcription cache for channel_id={channel_id}")
            return True

        try:
            async with self._get_connection() as conn:
                values = []
                for transcription in cached_transcriptions:
                    values.append((transcription.get("call_id"), json.dumps(transcription)))

                await conn.executemany(
                    """
                    INSERT INTO ai_bot_transcriptions (call_id, content)
                    VALUES ($1, $2::jsonb)
                """,
                    values,
                )

                logger.info(f"✅ Batch saved {len(values)} transcriptions for {channel_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to save cached transcriptions for channel_id={channel_id}: {e}")
            return False

    def clear_cache(self, channel_id: str) -> None:
        """
        Clear transcription cache for a channel

        Args:
            channel_id: Channel ID
        """
        if channel_id in self._memory_cache:
            del self._memory_cache[channel_id]
            logger.info(f"🗑️ Cleared transcription cache for channel: {channel_id}")
