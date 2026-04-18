"""
CDR Manager
Manages Call Detail Records (CDR) operations
"""

import logging
import traceback
from datetime import datetime, timedelta

import asyncpg
from config.settings import app_settings

logger = logging.getLogger(__name__)


class CDRManager:
    """Manages CDR records for AI Bot calls"""

    def __init__(self, db_pool, tenant_uuid: str | None = None):
        """
        Initialize CDR Manager

        Args:
            db_pool: asyncpg connection pool (optional)
            tenant_uuid: Wazo tenant UUID as string (optional, will be fetched if not provided)
        """
        self.db_pool = db_pool
        self.tenant_uuid = tenant_uuid

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

    async def get_or_create_tenant_uuid(self) -> str:
        """
        Get existing tenant UUID or create default one

        Returns:
            Tenant UUID as string
        """
        try:
            async with self._get_connection() as conn:
                # First try to get existing tenant
                tenant_record = await conn.fetchrow("SELECT uuid FROM call_logd_tenant LIMIT 1")
                if tenant_record:
                    tenant_uuid = str(tenant_record["uuid"])
                    logger.info(f"✅ Using existing tenant UUID: {tenant_uuid}")
                    return tenant_uuid

                default_uuid = str(app_settings.WAZO_TENANT_UUID)
                await conn.execute(
                    """
                    INSERT INTO call_logd_tenant (uuid)
                    VALUES ($1)
                    ON CONFLICT (uuid) DO NOTHING
                    """,
                    default_uuid,
                )
                logger.info(f"✅ Created default tenant UUID: {default_uuid}")
                return default_uuid

        except Exception as e:
            logger.error(f"❌ Error getting/creating tenant UUID: {e}")
            raise RuntimeError(f"Failed to get or create tenant UUID: {e}") from None

    async def find_record_id(self, channel_id: str) -> int | None:
        """
        Find CDR record ID for a channel

        Args:
            channel_id: Channel ID

        Returns:
            Record ID or None if not found
        """
        try:
            async with self._get_connection() as conn:
                record = await conn.fetchrow(
                    """
                    SELECT id FROM call_logd_call_log
                    WHERE user_field LIKE $1 OR user_field LIKE $2
                    ORDER BY date_answer DESC
                    LIMIT 1
                    """,
                    f"%{channel_id}%",
                    "AI Bot%",
                )

                if record:
                    cdr_record_id = record["id"]
                    logger.info(f"🔍 Found CDR record ID {cdr_record_id} for channel {channel_id}")
                    return cdr_record_id
                else:
                    logger.warning(f"⚠️ No CDR record found for channel {channel_id}")
                    return None

        except Exception as e:
            logger.error(f"❌ Error finding CDR record ID for channel {channel_id}: {e}")
            return None

    async def insert_record(self, channel_id: str, caller_info: dict, start_time: str) -> int | None:
        """
        Insert CDR record for a call

        Args:
            channel_id: Channel ID
            caller_info: Dict with 'name' and 'number' keys
            start_time: ISO format start time string

        Returns:
            Record ID or None on failure
        """
        logger.info(f"Starting CDR insert for channel: {channel_id}")
        try:
            async with self._get_connection() as conn:
                if not self.tenant_uuid:
                    self.tenant_uuid = await self.get_or_create_tenant_uuid()

                # Prepare data
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                answer_dt = start_dt + timedelta(
                    seconds=2
                )  # TODO: Replace to the actual answer time, for now fixed 2 seconds
                end_dt = None

                logger.info(
                    f"Inserting CDR record: start={start_dt},answer={answer_dt},end={end_dt},tenant={self.tenant_uuid}",
                )

                # Insert CDR record
                record_id = await conn.fetchval(
                    """
                    INSERT INTO call_logd_call_log
                    (date, date_answer, date_end, tenant_uuid, source_name,
                     source_exten, destination_name, destination_exten,
                     user_field, direction)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id
                    """,
                    start_dt,
                    answer_dt,
                    end_dt,
                    self.tenant_uuid,
                    caller_info.get("name", "User1000"),
                    caller_info.get("number", "1000"),
                    "AI Bot",
                    "1000",
                    "AI Bot Call",
                    "inbound",
                )

                logger.info(f"Inserted CDR record for AI Bot call: {channel_id} (ID: {record_id})")

                return record_id

        except ImportError as e:
            logger.warning(f"⚠️ asyncpg not available, skipping CDR insert for channel {channel_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Failed to insert CDR record for channel {channel_id}: {e}")
            logger.error(f"❌ CDR insert error details: {traceback.format_exc()}")
            return None

    async def update_answer_time(self, record_id: int | None, answer_time: str) -> bool:
        """
        Update CDR record with answer time (when channel is actually answered)

        Args:
            record_id: CDR record ID (can be None)
            answer_time: ISO format answer time string

        Returns:
            True if successful, False otherwise
        """
        if record_id is None:
            logger.warning("⚠️ Cannot update CDR answer time: record_id is None")
            return False

        try:
            async with self._get_connection() as conn:
                answer_dt = datetime.fromisoformat(answer_time.replace("Z", "+00:00"))

                # Update CDR record with answer time
                updated_record = await conn.fetchrow(
                    """
                    UPDATE call_logd_call_log
                    SET date_answer = $1
                    WHERE id = $2
                    RETURNING id, date_answer
                    """,
                    answer_dt,
                    record_id,
                )

                if updated_record:
                    logger.info(
                        f"CDR answer time updated - record ID: {updated_record['id']}, "
                        f"answer time: {updated_record['date_answer']}"
                    )
                    return True
                else:
                    logger.warning(f"⚠️ CDR record not found for answer time update (ID: {record_id})")
                    return False

        except ImportError as e:
            logger.warning(f"⚠️ asyncpg not available, skipping CDR answer time update: {e}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Failed to update CDR answer time for record {record_id}: {e}")
            logger.error(f"❌ CDR answer time update error details: {traceback.format_exc()}")
            return False

    async def update_record(
        self,
        record_id: int | None,
        end_time: str,
        duration_seconds: int | None = None,
    ) -> bool:
        """
        Update CDR record with end time and duration

        Args:
            record_id: CDR record ID (can be None)
            end_time: ISO format end time string
            duration_seconds: Optional duration in seconds

        Returns:
            True if successful, False otherwise
        """
        if record_id is None:
            logger.warning("⚠️ Cannot update CDR: record_id is None")
            return False

        try:
            async with self._get_connection() as conn:
                # Update CDR record
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

                # Calculate actual duration from database if not provided
                if duration_seconds is None:
                    record = await conn.fetchrow(
                        """
                        SELECT date_answer, date_end
                        FROM call_logd_call_log
                        WHERE id = $1
                        """,
                        record_id,
                    )

                    if record and record["date_answer"] and record["date_end"]:
                        duration_seconds = int((record["date_end"] - record["date_answer"]).total_seconds())

                # Update CDR record with end time and duration
                user_field_value = (
                    f"AI Bot - Duration: {duration_seconds}s" if duration_seconds else "AI Bot - Completed"
                )

                # Use RETURNING to get updated data in one query
                updated_record = await conn.fetchrow(
                    """
                    UPDATE call_logd_call_log
                    SET date_end = $1, user_field = $2
                    WHERE id = $3
                    RETURNING date_end, user_field
                    """,
                    end_dt,
                    user_field_value,
                    record_id,
                )

                if updated_record:
                    logger.info(
                        f"CDR record updated and verified - date_end: "
                        f"{updated_record['date_end']}, user_field: "
                        f"{updated_record['user_field']}"
                    )
                else:
                    logger.warning(f"⚠️ CDR record not found for update (ID: {record_id})")

                logger.info(f"Updated CDR record {record_id} with duration: {duration_seconds}s")
                return True

        except ImportError as e:
            logger.warning(f"⚠️ asyncpg not available, skipping CDR update for record {record_id}: {e}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Failed to update CDR record {record_id}: {e}")
            return False
