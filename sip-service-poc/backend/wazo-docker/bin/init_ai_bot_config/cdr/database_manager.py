"""
Database Manager
Unified interface for all database operations
"""

import asyncio
import logging

import asyncpg

from cdr.cdr_manager import CDRManager
from cdr.transcription_manager import TranscriptionManager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Unified database operations manager"""

    def __init__(self) -> None:
        """
        Initialize Database Manager
        """
        self.tenant_uuid: str | None = None
        self.db_pool: asyncpg.Pool | None = None

        # Initialize sub-managers
        self.cdr_manager = CDRManager(None, None)
        self.transcription_manager = TranscriptionManager()

    async def initialize_pool(self) -> bool:
        """
        Initialize asyncpg connection pool

        Returns:
            True if successful, False otherwise
        """
        try:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.db_pool = await asyncpg.create_pool(
                        host="postgres",
                        port=5432,
                        user="asterisk",
                        password="changeme",
                        database="wazo",
                        min_size=2,
                        max_size=10,
                        max_queries=50000,
                        max_inactive_connection_lifetime=300.0,  # 5 минут
                        command_timeout=30,
                    )

                    # Update sub-managers with the pool
                    self.cdr_manager.db_pool = self.db_pool
                    self.transcription_manager.db_pool = self.db_pool

                    logger.info("✅ Database connection pool initialized successfully")
                    return True

                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"❌ Failed to initialize database pool after {max_retries} attempts: {e}")
                        self.db_pool = None
                        return False
                    logger.warning(f"⚠️ Database pool initialization attempt {attempt + 1} failed, retrying in 1s: {e}")
                    await asyncio.sleep(1)

        except ImportError as e:
            logger.warning(f"⚠️ asyncpg not available, skipping pool initialization: {e}")
            self.db_pool = None
        except Exception as e:
            logger.error(f"❌ Unexpected error during database pool initialization: {e}")
            self.db_pool = None
        return False

    async def close_pool(self):
        """Close database connection pool"""
        if self.db_pool:
            await self.db_pool.close()
            self.db_pool = None
            logger.info("✅ Database connection pool closed")

    async def insert_cdr_record(self, channel_id: str, caller_info: dict, start_time: str) -> int | None:
        """Insert CDR record"""
        return await self.cdr_manager.insert_record(channel_id, caller_info, start_time)

    async def update_cdr_answer_time(self, record_id: int | None, answer_time: str) -> bool:
        """Update CDR record with answer time"""
        return await self.cdr_manager.update_answer_time(record_id, answer_time)

    async def update_cdr_record(
        self,
        record_id: int | None,
        end_time: str,
        duration_seconds: int | None = None,
    ) -> bool:
        """Update CDR record with end time and duration"""
        return await self.cdr_manager.update_record(record_id, end_time, duration_seconds)

    async def find_cdr_record_id(self, channel_id: str) -> int | None:
        """Find CDR record ID for a channel"""
        return await self.cdr_manager.find_record_id(channel_id)

    async def get_or_create_tenant_uuid(self) -> str:
        """Get or create tenant UUID"""
        if not self.tenant_uuid:
            self.tenant_uuid = await self.cdr_manager.get_or_create_tenant_uuid()
            # Update cdr_manager with the resolved tenant_uuid
            self.cdr_manager.tenant_uuid = self.tenant_uuid
        return self.tenant_uuid

    # Transcription Operations
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
    ) -> None:
        """Cache transcription data"""
        self.transcription_manager.cache_transcription(
            role=role,
            content=content,
            channel_id=channel_id,
            call_id=call_id,
            stt_engine=stt_engine,
            llm_model=llm_model,
            token_count=token_count,
            tenant_uuid=self.tenant_uuid,
        )

    async def save_cached_transcriptions(self, channel_id: str) -> bool:
        """Save cached transcriptions to database"""
        return await self.transcription_manager.save_cached_transcriptions(channel_id)

    def clear_transcription_cache(self, channel_id: str) -> None:
        """Clear transcription cache for a channel"""
        self.transcription_manager.clear_cache(channel_id)
