"""
Wazo AI Bot Service
Main service that integrates AI Bot with Wazo platform
"""

import asyncio
import contextlib
import logging
import random
import re
import time
import traceback
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

import aiohttp
from ari_handler import (
    AriClient,
    CallManager,
    LLMService,
    YandexCredentialsProvider,
    YandexSpeechSynthesizer,
)
from ari_handler.airtable_loader import load_airtable_data_for_user_async
from ari_handler.tool_call_handler import handle_tool_call
from ari_handler.websocket_server import start_websocket_server
from audio.audio_manager import AudioFileManager
from audio.converter import AudioConverter, CPUPoolManager
from audio.vad_detector import VADDetector
from cdr.database_manager import DatabaseManager
from config.constants import (
    BARGE_IN_GRACE_SECONDS,
    BARGE_IN_VAD_THRESHOLD,
    BYTES_PER_FRAME_16K,
    CHANNELS,
    DEFAULT_BARGE_IN_FRAMES,
    DEFAULT_COMMIT_GAP_SECONDS,
    FALLBACK_AI_BOT_TEXT,
    FIRST_PROMPT_AFTER_S,
    FRAME_MS,
    GREETING_AI_BOT_TEXT,
    HANGUP_AFTER_S,
    MAX_SILENCE_DURATION,
    MAX_UTTERANCE_SECONDS,
    MIN_UTTERANCE_SECONDS,
    PAYLOAD_TYPE_G722,
    POST_ROLL_MS,
    PRE_ROLL_MS,
    QUESTION_ABOUT_QUESTION_AI_BOT_TEXT,
    QUESTION_AI_BOT_TEXT,
    REPROMPT_AFTER_S,
    SAMPLE_RATE,
    SILENCE_FRAMES_THRESHOLD,
    SPEECH_FRAMES_THRESHOLD,
    START_VAD_THRESHOLD,
    TTS_SYNTH_TIMEOUT_MS,
)
from config.models import CodecType, ConversationRole, StasisEventType
from config.settings import app_settings

logger = logging.getLogger(__name__)


async def _load_airtable_after_greeting(phone_number: str, session_id: str) -> None:
    """Load Airtable data for caller after a short delay (non-blocking)."""
    await asyncio.sleep(2.0)
    try:
        await load_airtable_data_for_user_async(phone_number=phone_number, session_id=session_id)
    except Exception as e:
        logger.error("Error loading Airtable data after greeting: %s", e, exc_info=True)


class AIBotService:
    """Wazo AI Bot Service - integrates with Wazo platform"""

    SENTENCE_RE = re.compile(r"(.+?[\.!?…])(?:\s+|$)", re.S)
    MAX_PRE_ROLL_BYTES = (PRE_ROLL_MS // FRAME_MS) * BYTES_PER_FRAME_16K
    POST_BYTES = b"\xff" * ((POST_ROLL_MS // FRAME_MS) * BYTES_PER_FRAME_16K)

    def __init__(self) -> None:
        self.ari_client = AriClient(
            host=app_settings.ARI_HOST,
            port=app_settings.ARI_PORT,
            username=app_settings.ARI_USER,
            password=app_settings.ARI_PASSWORD,
            app=app_settings.ARI_APP_NAME,
        )

        self.database_manager = DatabaseManager()
        self.audio_manager = AudioFileManager()

        self.audio_converter = AudioConverter()

        CPUPoolManager.get_pool()

        self.llm_service = LLMService(tool_call_handler=handle_tool_call)

        # Store resources for cleanup
        self.call_resources: dict[str, dict[str, Any]] = {}

        # Keep-alive mechanism to prevent timeouts
        self.keep_alive_tasks: dict[str, asyncio.Task] = {}

        # Dialog context storage for each session
        self.dialog_contexts: defaultdict[str, deque[Any]] = defaultdict(
            lambda: deque(maxlen=app_settings.MAX_DIALOG_CONTEXT)
        )

        # Concurrency limiter (active conversations throttling)
        self.connection_semaphore = asyncio.Semaphore(app_settings.MAX_AVAILABLE_CALLS)

    async def _save_transcription_async(
        self,
        role: str,
        content: str,
        channel_id: str,
        call_id: str,
        stt_engine: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        """Save transcription asynchronously in background (fire-and-forget)"""
        try:
            self.database_manager.cache_transcription(
                role=role,
                content=content,
                channel_id=channel_id,
                call_id=call_id,
                stt_engine=stt_engine,
                llm_model=llm_model,
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to save transcription in background: {e}")

    async def initialize(self):
        """Initialize the AI Bot service"""

        try:
            # Initialize database manager
            await self.database_manager.initialize_pool()

            # Ensure tenant exists in database
            await self.database_manager.get_or_create_tenant_uuid()

            # Initialize other components
            await self._initialize_speech_recognition()
            await self._initialize_speech_synthesis()

            logger.info("✅ Wazo AI Bot Service initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize AI Bot service: {e}")
            raise

    async def _initialize_speech_recognition(self):
        """Initialize speech recognition service"""

        try:

            class _ExternalSTTClient:
                def __init__(self, base_url: str, token: str | None, default_model: str):
                    self._base_url = base_url.rstrip("/")
                    self._token = token
                    self._model = default_model
                    self._stt_session = None

                def _get_stt_session(self):
                    """Get or create STT session with connection pooling."""
                    if self._stt_session is None or self._stt_session.closed:
                        timeout = aiohttp.ClientTimeout(total=30, sock_connect=3, sock_read=20)
                        connector = aiohttp.TCPConnector(
                            limit=100,
                            limit_per_host=20,
                            keepalive_timeout=120,
                            enable_cleanup_closed=True,
                            use_dns_cache=True,
                            ttl_dns_cache=600,
                        )
                        self._stt_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
                    return self._stt_session

                async def recognize(
                    self,
                    audio_bytes: bytes,
                    payload_type: int = 9,
                ) -> str:
                    """Call STT non-stream endpoint to reduce client/server deadlocks and simplify flow."""

                    headers = {"Content-Type": "application/octet-stream"}
                    if self._token:
                        headers["Authorization"] = f"Bearer {self._token}"

                    session = self._get_stt_session()
                    url = f"{self._base_url}/recognize?model={self._model}&payload_type={payload_type}"

                    try:
                        async with session.post(url, data=audio_bytes, headers=headers) as resp:
                            if resp.status != 200:
                                txt = await resp.text()
                                logger.warning(f"STT recognize non-200 from {url}: {resp.status} {txt}")
                                return ""
                            data = await resp.json(content_type=None)
                            text = (data.get("text") or "").strip()
                            return text
                    except Exception as err:
                        logger.warning(f"STT recognize error for {url}: {err}")
                    return ""

                async def close(self):
                    """Close the STT session if it exists."""
                    if self._stt_session and not self._stt_session.closed:
                        await self._stt_session.close()
                        self._stt_session = None

            self.speech_recognizer = _ExternalSTTClient(
                base_url=app_settings.STT_BASE_URL,
                token=app_settings.STT_TOKEN,
                default_model=app_settings.STT_MODEL,
            )

            logger.info(f"✅ Speech recognition initialized: {app_settings.STT_MODEL}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize speech recognition: {e}")
            raise

    async def _initialize_speech_synthesis(self):
        """Initialize speech synthesis service"""

        try:
            credentials_provider = YandexCredentialsProvider()
            self.speech_synthesizer = YandexSpeechSynthesizer(credentials_provider)

            logger.info(f"✅ Speech synthesis initialized with model: {app_settings.TTS_MODEL}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize speech synthesis: {e}")
            raise

    async def start(self):
        """Start the AI Bot service"""

        try:
            await self.initialize()

            ws_port = int(__import__("os").environ.get("WEBSOCKET_PORT", "8000"))
            ws_task = asyncio.create_task(start_websocket_server(host="0.0.0.0", port=ws_port))
            logger.info("WebSocket server task created for port %s", ws_port)

            try:
                await self._process_ari_events()
            finally:
                if not ws_task.done():
                    ws_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await ws_task

        except Exception as e:
            logger.error(f"❌ Failed to start AI Bot service: {e}")
            raise

    async def _process_ari_events(self):
        """Process ARI events directly from Asterisk"""

        try:
            # Connect to Asterisk ARI and start processing events
            async with self.ari_client:
                logger.info("✅ Connected to Asterisk ARI")

                # Process events from the ARI client
                async for event in self.ari_client:
                    await self._handle_ari_event(event)

        except Exception as e:
            logger.error(f"❌ Error processing ARI events: {e}")
            raise

    async def _handle_ari_event(self, event):
        """Handle ARI events from Asterisk"""
        try:
            event_type = event.type
            if event_type in [StasisEventType.STASIS_START, StasisEventType.STASIS_END]:
                logger.info(f"📞 ARI Event: {event_type}")

            if event_type == StasisEventType.STASIS_START:
                await self._handle_ari_stasis_start(event)
            elif event_type == StasisEventType.STASIS_END:
                await self._handle_ari_stasis_end(event)

        except Exception as e:
            logger.error(f"❌ Error handling ARI event: {e}, traceback: {traceback.format_exc()}")

    async def _handle_ari_stasis_start(self, event):
        """Handle ARI StasisStart events"""
        try:
            channel_id = event.channel.id
            channel_name = event.channel.name
            exten = event.channel.dialplan.exten if event.channel.dialplan else None

            logger.info(f"📞 ARI StasisStart: channel={channel_id}, name={channel_name}, exten={exten}")

            if exten != "1000":
                return None

            logger.info(f"🤖 AI Bot call detected: {channel_id}")

            try:
                tenant_uuid = await self.database_manager.get_or_create_tenant_uuid()
                await self.ari_client.set_channel_variable(channel_id, "WAZO_TENANT_UUID", tenant_uuid)

                await asyncio.sleep(0.1)

                # Set CDR information for AI Bot calls
                await self._set_cdr_info(channel_id, "AI Bot")

                # Insert CDR record directly into database
                caller_info = {
                    "name": event.channel.caller.name,
                    "number": event.channel.caller.number,
                }
                logger.info(f"🔍 About to insert CDR record for channel: {channel_id}, caller: {caller_info}")

                # Initialize call resources for this channel
                if channel_id not in self.call_resources:
                    self.call_resources[channel_id] = {}
                    logger.info(f"🔍 Initialized call_resources for channel: {channel_id}")

                self.call_resources[channel_id]["caller_info"] = caller_info

                # Store start time immediately for duration calculation
                self.call_resources[channel_id]["start_time"] = event.timestamp

                logger.info(f"🔍 call_resources before CDR insert: {self.call_resources[channel_id]}")

                # Insert CDR record and store the ID
                cdr_record_id = await self.database_manager.insert_cdr_record(channel_id, caller_info, event.timestamp)

                if cdr_record_id:
                    # Preserve existing per-call resources and attach cdr id
                    if channel_id not in self.call_resources:
                        self.call_resources[channel_id] = {}
                    self.call_resources[channel_id]["cdr_record_id"] = cdr_record_id
                    logger.info(f"✅ CDR record ID {cdr_record_id} stored for channel: {channel_id}")
                else:
                    logger.warning(
                        f"Failed to get CDR record ID for channel: {channel_id},"
                        f" call_resources state: {self.call_resources[channel_id]}"
                    )

                # Now answer the channel after early media
                await self.ari_client.answer_channel(channel_id)

                if cdr_record_id:
                    await self.database_manager.update_cdr_answer_time(cdr_record_id, event.timestamp)
                    logger.info(f"Updated CDR answer time for record: {cdr_record_id}")

                await self._send_cel_event(
                    channel_id,
                    "ANSWER",
                    {"userfield": "AI Bot", "disposition": "ANSWERED"},
                )
                await self._start_ai_bot_conversation(channel_id, event.timestamp)

            except Exception as e:
                logger.error(f"❌ Error handling AI Bot call: {e}, traceback {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"❌ Error handling ARI StasisStart: {e}")

    async def _handle_ari_stasis_end(self, event):
        """Handle ARI StasisEnd events"""
        try:
            channel_id = event.channel.id
            active_connections = app_settings.MAX_AVAILABLE_CALLS - self.connection_semaphore._value
            active_users = f"{active_connections}/{app_settings.MAX_AVAILABLE_CALLS}"
            logger.info(f"📞 ARI StasisEnd: channel={channel_id}, active users: {active_users}")

            if channel_id.startswith("external_"):
                logger.info(f"🔄 Skipping StasisEnd for external channel: {channel_id}")
                return

            logger.info(f"🔍 call_resources keys: {list(self.call_resources.keys())}")

            # Calculate call duration if we have start time
            duration_seconds = None
            start_time = None

            if channel_id in self.call_resources and "start_time" in self.call_resources[channel_id]:
                start_time = self.call_resources[channel_id]["start_time"]
                try:
                    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
                    duration_seconds = int((end_dt - start_dt).total_seconds())
                    logger.info(f"⏱️ Call duration: {duration_seconds} seconds (start: {start_dt}, end: {end_dt})")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to calculate duration: {e}")
            else:
                logger.warning(f"⚠️ No start_time found for channel {channel_id} or related channels")

            # Update CDR with final disposition if this was an AI Bot call
            try:
                try:
                    await self._set_cdr_info(channel_id, "AI Bot - Completed")
                    logger.info(f"✅ Updated CDR for completed AI Bot call: {channel_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not set CDR info for channel {channel_id}: {e}")

                cdr_record_id = await self.database_manager.find_cdr_record_id(channel_id)

                if cdr_record_id:
                    end_time = datetime.now(UTC).isoformat()
                    success = await self.database_manager.update_cdr_record(cdr_record_id, end_time, duration_seconds)
                    if not success:
                        cdr_record_id = None
                else:
                    logger.warning(f"⚠️ No CDR record found for channel {channel_id}")
                was_ai_bot_call = cdr_record_id is not None

                if was_ai_bot_call:
                    try:
                        await self._send_cel_event(
                            channel_id,
                            "CHAN_END",
                            {
                                "userfield": "AI Bot - Completed",
                                "disposition": "ANSWERED",
                            },
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ Could not send CEL event for channel {channel_id}: {e}")

            except Exception:
                logger.warning(f"⚠️ Failed to update CDR for channel {channel_id}, traceback {traceback.format_exc()}")

            # Clean up resources AFTER updating CDR
            logger.info(f"🔍 Cleaning up resources for channel: {channel_id}")
            await self._cleanup_channel_resources(channel_id)

        except Exception as e:
            logger.error(f"❌ Error handling ARI StasisEnd: {e}")

    async def _send_cel_event(self, channel_id: str, event_type: str, event_data: dict | None = None):
        """Send CEL event for AI bot calls"""
        try:
            # Send CEL event using ARI
            cel_data = {
                "eventName": event_type,
                "channelId": channel_id,
                "timestamp": int(time.time()),
                "userfield": "AI Bot",
            }

            if event_data:
                cel_data.update(event_data)

            await self.ari_client._post("events/user/ai_bot_cel", cel_data)
            logger.info(f"✅ Sent CEL event {event_type} for channel {channel_id}")

        except Exception as e:
            logger.warning(f"⚠️ Failed to send CEL event for channel {channel_id}: {e}")

    async def _set_cdr_info(self, channel_id: str, userfield: str):
        """Set CDR userfield using ARI"""
        try:
            # Set CDR userfield using ARI
            await self.ari_client._post(
                f"channels/{channel_id}/variable",
                {"variable": "CDR(userfield)", "value": userfield},
            )

            # Send CEL event for CDR
            await self._send_cel_event(
                channel_id,
                "CHAN_START",
                {"userfield": userfield},
            )

            logger.info(f"✅ Set CDR info for channel {channel_id}: userfield={userfield}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to set CDR info for channel {channel_id}: {e}")

    async def _start_ai_bot_conversation(self, channel_id: str, start_time: str | None = None):
        """Start AI Bot conversation for a channel"""
        logger.info(f"💬 Starting AI Bot conversation for channel: {channel_id}")

        # Create unique caller ID for conversation history based on caller info
        caller_info = self.call_resources.get(channel_id, {}).get("caller_info", {})
        caller_name = caller_info.get("name", "unknown")
        caller_number = caller_info.get("number", "unknown")
        caller_start_time = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        unique_caller_id = f"{caller_name}_{caller_number}_{caller_start_time}"
        logger.info(f"🆔 Created unique caller ID: {unique_caller_id} for {caller_name}:{caller_number}")

        # Limit concurrent conversations (active connections)
        async with self.connection_semaphore:
            try:
                # Create external media channel for RTP audio input
                active_connections = app_settings.MAX_AVAILABLE_CALLS - self.connection_semaphore._value
                active_users = f"{active_connections}/{app_settings.MAX_AVAILABLE_CALLS}"
                (
                    bridge_id,
                    external_channel_id,
                    rtp_port,
                ) = await self._create_external_media(channel_id)
                logger.info(f"✅ External media created on port {rtp_port}, active users: {active_users}")

                if channel_id in self.call_resources and "start_time" in self.call_resources[channel_id]:
                    if external_channel_id not in self.call_resources:
                        self.call_resources[external_channel_id] = {}
                    self.call_resources[external_channel_id]["start_time"] = self.call_resources[channel_id][
                        "start_time"
                    ]
                    logger.info(f"✅ Copied start_time to external channel {external_channel_id}")

                # Start RTP listener for voice recognition
                logger.info("🎯 Starting RTP listener for voice recognition...")
                rtp_task = asyncio.create_task(self._rtp_voice_processor(rtp_port, channel_id))

                # Use provided start_time or current time
                if start_time is None:
                    start_time = datetime.now(UTC).isoformat()

                # Start keep-alive task to prevent timeouts
                keep_alive_task = asyncio.create_task(self._keep_alive_loop(channel_id))

                # Store resources for cleanup (merge to preserve existing fields like cdr_record_id)
                existing_resources = self.call_resources.get(channel_id, {})
                existing_resources.update(
                    {
                        "bridge_id": bridge_id,
                        "external_channel_id": external_channel_id,
                        "rtp_port": rtp_port,
                        "rtp_task": rtp_task,
                        "start_time": start_time,  # Store start time for duration calculation
                        "unique_caller_id": unique_caller_id,  # Store unique caller ID for conversation history
                    }
                )
                # Ensure tasks set exists for per-call cancellation
                if "tasks" not in existing_resources:
                    existing_resources["tasks"] = set()
                self.call_resources[channel_id] = existing_resources

                # Store keep-alive task
                self.keep_alive_tasks[channel_id] = keep_alive_task

                try:
                    await self.ari_client.play_media(channel_id, "sound:silence/1")
                except Exception as e:
                    logger.warning(f"Failed to play hello sound: {e}")

                logger.info(f"✅ AI Bot conversation started for channel: {channel_id}")

            except Exception as e:
                logger.error(f"❌ Error starting AI Bot conversation: {e}, traceback: {traceback.format_exc()}")

                # Cleanup any partially created resources
                if channel_id in self.call_resources:
                    try:
                        await self._cleanup_channel_resources(channel_id)
                    except Exception as cleanup_error:
                        logger.error(f"❌ Error during cleanup: {cleanup_error}")

    async def _keep_alive_loop(self, channel_id: str):
        """Keep-alive loop to prevent Asterisk timeouts"""
        try:
            logger.info(f"💓 Starting keep-alive loop for channel: {channel_id}")

            while channel_id in self.call_resources:
                try:
                    # Send a ping to keep the channel alive
                    if self.ari_client:
                        try:
                            # Get channel info to keep it active
                            await self.ari_client.get_channel_info(channel_id)
                            logger.debug(f"💓 Keep-alive ping sent for channel: {channel_id}")

                            # Also send a bridge info request to keep bridge active
                            if channel_id in self.call_resources:
                                bridge_id = self.call_resources[channel_id].get("bridge_id")
                                if bridge_id:
                                    try:
                                        # This will keep the bridge active
                                        await self.ari_client.get_bridge_info(bridge_id)
                                        logger.debug(f"💓 Bridge keep-alive sent for bridge: {bridge_id}")
                                    except Exception as bridge_error:
                                        logger.warning(f"⚠️ Bridge keep-alive failed for {bridge_id}: {bridge_error}")
                                        # Bridge might be gone, remove it from resources
                                        if channel_id in self.call_resources:
                                            self.call_resources[channel_id].pop("bridge_id", None)

                        except Exception as ping_error:
                            error_str = str(ping_error).lower()
                            if "not found" in error_str or "404" in error_str:
                                logger.info(f"💓 Channel {channel_id} has ended, stopping keep-alive")
                                # Remove from call_resources to stop the loop
                                self.call_resources.pop(channel_id, None)
                                break
                            else:
                                logger.warning(f"⚠️ Keep-alive ping failed: {ping_error}")

                except Exception as e:
                    logger.warning(f"⚠️ Keep-alive ping failed for channel {channel_id}: {e}")

                await asyncio.sleep(3)

        except asyncio.CancelledError:
            logger.info(f"💓 Keep-alive loop cancelled for channel: {channel_id}")
        except Exception as e:
            logger.error(f"❌ Keep-alive loop error for channel {channel_id}: {e}")
        finally:
            logger.info(f"💓 Keep-alive loop ended for channel: {channel_id}")

    async def _create_external_media(self, channel_id: str) -> tuple[str, str, int]:
        """Create external media channel for RTP input"""

        # Get dynamic RTP port
        rtp_port = random.randint(20001, 20050)
        external_channel_id = f"external_{channel_id}_{random.randint(1000, 9999)}"

        logger.info(f"🔧 Creating external media: {external_channel_id} on port {rtp_port}")

        bridge_id = None
        external_created = False

        try:
            # Create external media channel
            await self.ari_client.create_external_media(
                channel_id=external_channel_id,
                app="voice-bot",
                external_host=f"wazo-ai-bot:{rtp_port}",
                format=CodecType.G722,
            )
            external_created = True
            logger.info(f"✅ External media channel created: {external_channel_id}")

            await asyncio.sleep(0.2)  # 200ms delay for external channel stabilization
            bridge_id = await self.ari_client.create_bridge(bridge_type="mixing")

            # Add channels to bridge
            await self.ari_client.add_channel_to_bridge(bridge_id, channel_id)
            await self.ari_client.add_channel_to_bridge(bridge_id, external_channel_id)

            # Set tenant UUID after channel is in Stasis
            tenant_uuid = await self.database_manager.get_or_create_tenant_uuid()
            await self.ari_client.set_channel_variable(external_channel_id, "WAZO_TENANT_UUID", tenant_uuid)

            return bridge_id, external_channel_id, rtp_port

        except Exception as e:
            logger.error(f"❌ Error creating external media: {e}")

            # Cleanup on error
            if bridge_id:
                try:
                    await self.ari_client.destroy_bridge(bridge_id)
                    logger.info(f"✅ Cleaned up bridge: {bridge_id}")
                except Exception as cleanup_error:
                    logger.error(f"❌ Error cleaning up bridge: {cleanup_error}")

            if external_created:
                try:
                    await self.ari_client.destroy_channel(external_channel_id)
                    logger.info(f"✅ Cleaned up external channel: {external_channel_id}")
                except Exception as cleanup_error:
                    logger.error(f"❌ Error cleaning up external channel: {cleanup_error}")

            raise

    async def _rtp_voice_processor(self, rtp_port: int, channel_id: str):
        """Process RTP audio for voice recognition"""
        logger.info(f"🎧 Starting RTP voice processor on port {rtp_port}")
        try:
            # Per-utterance sequence for timing logs
            utterance_seq: int = 0

            buffer = bytearray()
            silence_frames = 0
            speech_frames = 0
            consecutive_silence_time = 0.0
            playback_suppress_until = 0.0  # gate while TTS plays and a short tail
            in_utterance = False
            utterance_start_time = 0.0
            last_speech_time = 0.0
            barge_in_frames = 0
            prev_is_playing = False
            tts_started_at = -1.0

            # Pre-barge-in buffer: accumulate audio before barge-in to prevent loss of speech start
            pre_barge_in_buffer = bytearray()
            pre_barge_in_frames = 0
            max_pre_barge_in_frames = 50  # Maximum 1 second (50 * 20ms frame)

            last_pkt_wallclock: float | None = None

            # Idle-disconnect state
            user_has_spoken: bool = False
            asked_anything_prompted: bool = False
            anything_prompt_time: float = 0.0
            call_should_end: bool = False  # Flag to indicate call should be ended
            last_user_speech_time: float = 0.0  # Последний момент, когда пользователь говорил (по нашей детекции)

            pre_roll_frames = bytearray()

            rtp_addr = None
            packet_count = 0

            frame_size_bytes = 640

            async with CallManager("0.0.0.0", rtp_port) as call_manager:
                current_task = asyncio.current_task()  # type: ignore
                current_task._call_manager = call_manager  # type: ignore
                logger.info(f"🎧 RTP listener started on port {rtp_port}")
                loop = asyncio.get_event_loop()  # Cache event loop
                start_time = loop.time()
                vad = VADDetector(threshold=0.3)

                async for (
                    audio_data,
                    addr,
                    payload_type,
                ) in call_manager.audio_channel_with_pt(packet_size=2048):
                    packet_count += 1

                    # Store the RTP address for playback
                    if rtp_addr is None:
                        rtp_addr = addr
                        logger.info(f"🎧 RTP address captured: {rtp_addr}")

                        self.call_resources[channel_id]["rtp_addr"] = rtp_addr
                        try:
                            logger.info("Playing Greeting Audio")
                            greeting_audio = self.audio_manager.get_audio("greeting_initial")
                            if greeting_audio is None:
                                raise ValueError("Greeting audio is None")

                            asyncio.create_task(
                                self._save_transcription_async(
                                    role=ConversationRole.ASSISTANT,
                                    content=GREETING_AI_BOT_TEXT,
                                    channel_id=channel_id,
                                    call_id=channel_id,
                                )
                            )

                            await call_manager.play_next(
                                greeting_audio,
                                rtp_addr,
                                frame_duration_ms=20,
                                sample_rate=SAMPLE_RATE,
                                payload_type=9,
                            )
                            caller_info = self.call_resources.get(channel_id, {}).get("caller_info", {})
                            caller_number = caller_info.get("number", "")
                            if caller_number:
                                asyncio.create_task(_load_airtable_after_greeting(caller_number, channel_id))
                        except Exception as e:
                            logger.error(f"❌ Failed to play Russian greeting: {e}")

                    # Minimal jitter buffer: detect short gaps by wallclock and pad with silence frames (20–40ms)
                    now_wc = loop.time()
                    if last_pkt_wallclock is not None:
                        delta = now_wc - last_pkt_wallclock
                        if delta > 0.03:  # gap > 30ms suggests 1–2 lost 20ms frames
                            missing = min(max(int(delta / 0.02) - 1, 0), 2)
                            if missing > 0:
                                missing_silence = b"\xff" * (missing * BYTES_PER_FRAME_16K)
                                # If already inside utterance, accumulate silence to buffer and timers
                                if in_utterance:
                                    buffer.extend(missing_silence)
                                    silence_frames += missing
                                    speech_frames = 0
                                    consecutive_silence_time += 0.02 * missing
                                else:
                                    silence_frames += missing
                    last_pkt_wallclock = now_wc

                    # Half-duplex + barge-in: allow detecting speech while TTS plays
                    current_time = loop.time() - start_time

                    # Idle/disconnect timers
                    try:
                        # Use method for idle disconnect mechanism
                        (
                            user_has_spoken,
                            asked_anything_prompted,
                            anything_prompt_time,
                            call_should_end,
                            last_user_speech_time,
                        ) = await self._handle_idle_disconnect_mechanism(
                            channel_id,
                            call_manager,
                            rtp_addr,
                            user_has_spoken,
                            asked_anything_prompted,
                            anything_prompt_time,
                            current_time,
                            last_user_speech_time,
                            in_utterance,
                        )

                        # Check if call should be ended
                        if call_should_end:
                            # This indicates the call was hung up, so we should exit the loop
                            logger.info(f"🔄 Выход из цикла обработки RTP для канала: {channel_id}")
                            break
                    except Exception as _timer_e:
                        logger.warning(f"Таймер ожидания речи для канала {channel_id}: {_timer_e}")
                    is_playing_now = call_manager.is_playing()
                    # Track TTS start/stop to enforce grace period
                    if is_playing_now and not prev_is_playing:
                        tts_started_at = current_time
                    elif not is_playing_now and prev_is_playing:
                        # TTS finished naturally - clear pre-barge-in buffer
                        pre_barge_in_buffer.clear()
                        pre_barge_in_frames = 0
                    prev_is_playing = is_playing_now

                    pcm_audio = await self.audio_converter.to_pcm_async(audio_data, payload_type)

                    pre_roll_frames.extend(audio_data)
                    if len(pre_roll_frames) > self.MAX_PRE_ROLL_BYTES:
                        excess = len(pre_roll_frames) - self.MAX_PRE_ROLL_BYTES
                        del pre_roll_frames[:excess]
                    try:
                        speech_votes = 0
                        total_vad_frames = 0

                        for i in range(0, len(pcm_audio), frame_size_bytes):
                            frame = pcm_audio[i : i + frame_size_bytes]
                            if len(frame) == frame_size_bytes:
                                try:
                                    if await vad.is_speech_async(frame):
                                        speech_votes += 1
                                except Exception as e:
                                    logger.warning(f"VAD analysis failed for frame {i}: {e}")
                                total_vad_frames += 1

                        frame_speech_ratio = speech_votes / max(1, total_vad_frames)
                        is_silent_frame = frame_speech_ratio < 0.7  # Порог тишины
                    except Exception:
                        frame_speech_ratio = 0.0
                        is_silent_frame = True

                    if is_playing_now:
                        # Apply grace period to avoid cancelling TTS immediately on tiny noises
                        if (tts_started_at >= 0) and (current_time - tts_started_at < BARGE_IN_GRACE_SECONDS):
                            barge_in_frames = 0
                            # In grace period we don't accumulate in pre-barge-in buffer
                            pre_barge_in_buffer.clear()
                            pre_barge_in_frames = 0
                        elif frame_speech_ratio >= BARGE_IN_VAD_THRESHOLD:
                            barge_in_frames += 1
                            # Accumulate in pre-barge-in buffer on speech detection
                            pre_barge_in_buffer.extend(audio_data)
                            pre_barge_in_frames += 1

                            # Limit buffer size
                            if pre_barge_in_frames > max_pre_barge_in_frames:
                                bytes_per_frame = len(audio_data)
                                bytes_to_remove = (pre_barge_in_frames - max_pre_barge_in_frames) * bytes_per_frame
                                pre_barge_in_buffer = pre_barge_in_buffer[bytes_to_remove:]
                                pre_barge_in_frames = max_pre_barge_in_frames
                        else:
                            barge_in_frames = 0
                            # Silence - clear pre-barge-in if too many frames
                            if pre_barge_in_frames > 10:
                                pre_barge_in_buffer.clear()
                                pre_barge_in_frames = 0

                        if barge_in_frames >= DEFAULT_BARGE_IN_FRAMES:
                            logger.info("🎤 Barge-in detected, stopping playback.")
                            call_manager.cancel_play()
                            playback_suppress_until = current_time + 0.15
                            # Reset idle disconnect mechanism state
                            (
                                user_has_spoken,
                                asked_anything_prompted,
                                anything_prompt_time,
                                call_should_end,
                            ) = self._reset_idle_disconnect_state()
                            in_utterance = True

                            # Move audio from pre-barge-in buffer to main buffer
                            if len(pre_barge_in_buffer) > 0:
                                buffer = bytearray(pre_barge_in_buffer)
                                logger.info(
                                    f"Restored {len(pre_barge_in_buffer)} bytes "
                                    f"({pre_barge_in_frames} frames) from pre-barge-in buffer"
                                )
                                # Calculate number of frames for time correction
                                estimated_frames = pre_barge_in_frames
                                # Correct utterance_start_time with accumulated frames
                                utterance_start_time = current_time - (estimated_frames * FRAME_MS / 1000.0)
                                # Set speech_frames for correct processing
                                speech_frames = min(estimated_frames, SPEECH_FRAMES_THRESHOLD)
                            else:
                                buffer.clear()
                                utterance_start_time = current_time
                                speech_frames = 0

                            last_speech_time = current_time
                            last_user_speech_time = current_time
                            silence_frames = 0
                            consecutive_silence_time = 0.0
                            barge_in_frames = 0

                            # Clear pre-barge-in buffer
                            pre_barge_in_buffer.clear()
                            pre_barge_in_frames = 0

                            # Skip this frame to avoid including TTS tail; start buffering from next frame
                            continue

                        # Still playing TTS: ignore input and reset counters
                        buffer.clear()
                        silence_frames = 0
                        speech_frames = 0
                        consecutive_silence_time = 0.0
                        continue
                    # Flag to track if frame was already added in suppress period
                    frame_added_in_suppress = False

                    if current_time < playback_suppress_until:
                        # After barge-in: don't clear buffer if it already contains data (restored from pre-barge-in)
                        # Continue accumulating audio during suppress period
                        if in_utterance and len(buffer) > 0:
                            # Buffer already restored from pre-barge-in - continue accumulating
                            buffer.extend(audio_data)
                            frame_added_in_suppress = True
                            # Обновить счетчики для корректной обработки
                            if is_silent_frame:
                                silence_frames += 1
                                speech_frames = 0
                                consecutive_silence_time += 0.02
                            else:
                                speech_frames += 1
                                silence_frames = 0
                                consecutive_silence_time = 0.0
                                last_speech_time = current_time
                            # Continue processing in "In utterance" block (not continue)
                        else:
                            # Normal suppress period - clear buffer
                            buffer.clear()
                            silence_frames = 0
                            speech_frames = 0
                            consecutive_silence_time = 0.0
                            continue

                    # Utterance state machine
                    if not in_utterance:
                        # Wait for confirmed speech start
                        if (not is_silent_frame) and (
                            frame_speech_ratio >= START_VAD_THRESHOLD  # Еще более высокий порог для начала речи
                        ):
                            speech_frames += 1
                            silence_frames = 0
                            if speech_frames >= SPEECH_FRAMES_THRESHOLD:
                                in_utterance = True
                                utterance_start_time = current_time
                                last_speech_time = current_time
                                last_user_speech_time = current_time
                                buffer.clear()  # start fresh buffer from speech start
                                # Stop any TTS immediately (barge-in)
                                if call_manager.is_playing():
                                    call_manager.cancel_play()
                                playback_suppress_until = current_time + 0.2
                                # Add current frame to buffer
                                buffer.extend(audio_data)
                                # reset counters for in-utterance tracking
                                speech_frames = 0
                                silence_frames = 0
                                consecutive_silence_time = 0.0
                                # Reset idle disconnect mechanism state
                                (
                                    user_has_spoken,
                                    asked_anything_prompted,
                                    anything_prompt_time,
                                    call_should_end,
                                ) = self._reset_idle_disconnect_state()
                        else:
                            # still waiting for speech
                            silence_frames += 1
                            speech_frames = 0
                        # Until utterance starts we do not accumulate buffer further
                        continue

                    # In utterance: accumulate and track gap
                    # Skip adding if already added in suppress period
                    if not frame_added_in_suppress:
                        buffer.extend(audio_data)
                    if is_silent_frame:
                        silence_frames += 1
                        speech_frames = 0
                        consecutive_silence_time += 0.02
                    else:
                        speech_frames += 1
                        silence_frames = 0
                        consecutive_silence_time = 0.0
                        last_speech_time = current_time

                    # If enough immediate speech frames during TTS, ensure barge-in behavior
                    if speech_frames == SPEECH_FRAMES_THRESHOLD and call_manager.is_playing():
                        logger.info("🎤 Speech detected, stopping playback.")
                        call_manager.cancel_play()
                        playback_suppress_until = current_time + 0.1

                    # Safety: if line is silent too long, reset buffer to prevent growth
                    if consecutive_silence_time > MAX_SILENCE_DURATION:
                        logger.info("MAX_SILENCE_DURATION: %s", MAX_SILENCE_DURATION)
                        logger.info(
                            f"🔇 Max silence duration reached ({consecutive_silence_time:.1f}s), resetting buffer"
                        )
                        buffer.clear()
                        silence_frames = 0
                        speech_frames = 0
                        consecutive_silence_time = 0.0
                        continue

                    # Decide to commit only when BOTH gap and silence are satisfied, or by max length
                    time_since_last = current_time - last_speech_time
                    utterance_len = current_time - utterance_start_time
                    commit_by_gap = time_since_last >= DEFAULT_COMMIT_GAP_SECONDS
                    commit_by_silence = silence_frames >= SILENCE_FRAMES_THRESHOLD
                    commit_by_length = utterance_len >= MAX_UTTERANCE_SECONDS
                    commit_ready = (commit_by_gap and commit_by_silence) or commit_by_length
                    if commit_ready:
                        # Guard against committing too-short utterances
                        if utterance_len < MIN_UTTERANCE_SECONDS and not commit_by_length:
                            # keep listening until either long enough or explicit max hits
                            continue
                        # Trim the buffer to remove trailing silence frames
                        # Use time_since_last for more accurate determination of real silence
                        # after last speech, not only silence_frames (which may include quiet speech)
                        max_silence_to_trim_ms = 300  # Maximum 300ms silence for trimming
                        min_silence_to_trim_ms = 200  # Minimum 200ms for trimming (protection from quiet speech)

                        # Use time_since_last as a more accurate indicator of real silence
                        # silence_frames may accumulate even with quiet speech at the end of the phrase
                        time_since_last_ms = time_since_last * 1000

                        if time_since_last_ms >= min_silence_to_trim_ms:
                            # Calculate the number of frames to trim based on time_since_last
                            # But limit the maximum to avoid trimming too much
                            frames_to_trim_by_time = int(time_since_last_ms / FRAME_MS)
                            frames_to_trim = min(
                                frames_to_trim_by_time,
                                int(max_silence_to_trim_ms / FRAME_MS),
                            )

                            bytes_to_trim = frames_to_trim * BYTES_PER_FRAME_16K
                            if len(buffer) >= bytes_to_trim:
                                del buffer[-bytes_to_trim:]
                                logger.info(
                                    f"Trimmed {frames_to_trim} frames ({time_since_last_ms:.0f}ms silence) "
                                    f"from buffer end (silence_frames={silence_frames})"
                                )
                            elif len(buffer) > 0:
                                # If the buffer is less than what needs to be trimmed, trim only available
                                # But only if it is really silence (not quiet speech)
                                if time_since_last_ms >= 300:  # Only if silence >= 300ms
                                    del buffer[:]  # Clear the entire buffer only if it is exactly silence
                                    logger.info(
                                        f"Cleared entire buffer: time_since_last={time_since_last_ms:.0f}ms "
                                        f"(likely real silence, not quiet speech)"
                                    )
                        else:
                            # Silence too short - possibly quiet speech, do not trim
                            logger.info(
                                f"Skipping trim: time_since_last too short "
                                f"({time_since_last_ms:.0f}ms < {min_silence_to_trim_ms}ms), "
                                f"may be quiet speech at end of phrase"
                            )

                        # If the buffer is empty, reset it and continue
                        if len(buffer) == 0:
                            buffer.clear()
                            silence_frames = 0
                            speech_frames = 0
                            continue

                        # Validate buffer has enough audio data
                        buffer_duration = len(buffer) / (16000 * CHANNELS)
                        if buffer_duration < 0.1:  # lower min duration for faster STT start
                            logger.info(f"🎤 Buffer too short ({buffer_duration:.2f}s), skipping")
                            buffer.clear()
                            silence_frames = 0
                            speech_frames = 0
                            in_utterance = False
                            utterance_start_time = 0.0
                            last_speech_time = 0.0
                            continue

                        logger.info(f"🎤 Processing audio buffer: {len(buffer)} bytes, {buffer_duration:.2f} seconds")

                        # Recognize text from the buffer
                        try:
                            stt_payload = bytearray(pre_roll_frames)
                            stt_payload.extend(buffer)
                            stt_payload.extend(self.POST_BYTES)
                            stt_payload = bytes(stt_payload)  # type: ignore
                            # Soft level normalization (gentle gain + soft clip) before STT
                            stt_payload_pcm = None
                            stt_payload_type = payload_type
                            try:
                                # Convert to PCM based on payload type for normalization
                                pcm16 = await self.audio_converter.to_pcm_async(stt_payload, payload_type)

                                # async normalization
                                pcm16_norm = await self.audio_converter.normalize_audio(pcm16, target_rms=4000.0)

                                # Use normalized PCM16 directly to avoid double conversion
                                stt_payload_pcm = pcm16_norm
                                stt_payload_type = -1  # PCM16 16kHz

                            except Exception as e:  # best-effort
                                logger.warning(f"Normalization failed: {e}, using original format")
                                # Fallback to original format if normalization fails
                                stt_payload_pcm = stt_payload
                                stt_payload_type = payload_type

                            # Use detected payload type for speech recognition
                            utterance_seq += 1
                            _t0_stt = loop.time()
                            text = await self.speech_recognizer.recognize(
                                stt_payload_pcm, payload_type=stt_payload_type
                            )

                            _stt_ms = int((loop.time() - _t0_stt) * 1000)
                            logger.info(f"⏱️ STT обработка: {_stt_ms} мс (канал={channel_id}, реплика={utterance_seq})")

                            processing_time = (buffer_duration * 1000 + _stt_ms) / 1000

                            if processing_time > 3.0 and current_time >= playback_suppress_until:
                                # Play a random filler phrase to reduce perceived wait time
                                await self._play_filler_phrase(channel_id, call_manager)

                            if text and text.strip():
                                logger.info(f"🎯 Recognized: '{text}'")
                                # Обновляем время последней речи пользователя
                                last_user_speech_time = current_time

                                asyncio.create_task(
                                    self._save_transcription_async(
                                        role=ConversationRole.USER,
                                        content=text,
                                        channel_id=channel_id,
                                        call_id=channel_id,
                                        stt_engine=app_settings.STT_MODEL,
                                    )
                                )
                                user_query = text

                                # Try streaming LLM → sentence-level TTS
                                logger.info(f"🧠 Запуск LLM streaming (канал={channel_id}, реплика={utterance_seq})")
                                full_response_parts: list[str] = []
                                pending_text: str = ""
                                _tts_synth_ms_total = 0
                                _tts_chunks = 0

                                try:
                                    # Get unique caller ID for conversation history
                                    unique_caller_id = self.call_resources.get(channel_id, {}).get("unique_caller_id")

                                    if not unique_caller_id:
                                        unique_caller_id = "unknown"

                                    # Generate LLM response
                                    stream_iter = self.llm_service.stream_generate_with_context(
                                        user_query, meta_user=unique_caller_id
                                    )
                                    async for seg in stream_iter:
                                        if not seg:
                                            continue
                                        full_response_parts.append(seg)
                                        pending_text += seg
                                        # Extract complete sentences from pending_text
                                        pos = 0
                                        sentences: list[str] = []
                                        while True:
                                            m = self.SENTENCE_RE.match(pending_text, pos)
                                            if not m:
                                                break
                                            s = m.group(1).strip()
                                            pos = m.end()
                                            if s:
                                                sentences.append(s)
                                        # Keep remainder in pending_text
                                        pending_text = pending_text[pos:].strip()
                                        # Synthesize only complete sentences to avoid mid-phrase TTS
                                        for sent in sentences:
                                            try:
                                                _tts_chunks += 1
                                                # Synthesize TTS with timeout
                                                _t0_tts_syn = loop.time()
                                                _pause_ms = random.randint(150, 200)
                                                audio_data = await asyncio.wait_for(
                                                    self.speech_synthesizer.synthesize(
                                                        f"{sent} sil <[{_pause_ms}]>",
                                                        output_format=CodecType.G722,
                                                    ),
                                                    timeout=TTS_SYNTH_TIMEOUT_MS / 1000,
                                                )
                                                _tts_synth_ms_total += int((loop.time() - _t0_tts_syn) * 1000)
                                                if audio_data and rtp_addr:
                                                    await call_manager.play_next(
                                                        audio_data,
                                                        rtp_addr,
                                                        frame_duration_ms=FRAME_MS,
                                                        sample_rate=SAMPLE_RATE,
                                                        payload_type=PAYLOAD_TYPE_G722,
                                                    )
                                                elif not rtp_addr:
                                                    logger.warning("⚠️ No RTP address available for playback")
                                            except Exception as synth_err:
                                                logger.warning(
                                                    f"⚠️ TTS synth/playback error for streamed sentence: {synth_err}"
                                                )
                                except Exception as stream_err:
                                    logger.warning(f"⚠️ LLM streaming failed, fallback to non-streaming: {stream_err}")

                                # Finalize dialog context with the full response
                                # Emit any remaining tail as a final sentence
                                tail = pending_text.strip()
                                if tail:
                                    try:
                                        _tts_chunks += 1
                                        _t0_tts_syn = loop.time()
                                        _pause_ms = random.randint(150, 200)
                                        audio_data = await asyncio.wait_for(
                                            self.speech_synthesizer.synthesize(
                                                f"{tail} sil <[{_pause_ms}]>",
                                                output_format=CodecType.G722,
                                            ),
                                            timeout=TTS_SYNTH_TIMEOUT_MS / 1000,
                                        )
                                        _tts_synth_ms_total += int((loop.time() - _t0_tts_syn) * 1000)
                                        if audio_data and rtp_addr:
                                            await call_manager.play_next(
                                                audio_data,
                                                rtp_addr,
                                                frame_duration_ms=FRAME_MS,
                                                sample_rate=SAMPLE_RATE,
                                                payload_type=PAYLOAD_TYPE_G722,
                                            )
                                    except Exception as synth_err:
                                        logger.warning(f"⚠️ TTS synth/playback error for tail: {synth_err}")
                                llm_response = "".join(full_response_parts).strip()
                                if llm_response:
                                    logger.info(f"🧠 LLM (stream) response: '{llm_response}'")
                                    asyncio.create_task(
                                        self._save_transcription_async(
                                            role=ConversationRole.ASSISTANT,
                                            content=llm_response,
                                            channel_id=channel_id,
                                            call_id=channel_id,
                                            llm_model="DiFy",
                                        )
                                    )
                                logger.info(
                                    f"⏱️ TTS синтез: {_tts_synth_ms_total} мс "
                                    f"(канал={channel_id}, реплика={utterance_seq}, фрагментов={_tts_chunks})"
                                )

                            else:
                                logger.warning("🔇 No speech recognized from audio")
                                try:
                                    _t0_tts_syn_fb = loop.time()
                                    audio_data = self.audio_manager.get_audio(  # type: ignore
                                        "fallback_not_understood"
                                    )
                                    _tts_synth_ms_fb = int((loop.time() - _t0_tts_syn_fb) * 1000)
                                    if audio_data:
                                        if rtp_addr:
                                            await call_manager.play_next(
                                                audio_data,
                                                rtp_addr,
                                                frame_duration_ms=FRAME_MS,
                                                sample_rate=SAMPLE_RATE,
                                                payload_type=PAYLOAD_TYPE_G722,
                                            )
                                            logger.info(
                                                f"TTS (fallback) синтез: {_tts_synth_ms_fb} "
                                                f"мс (канал={channel_id}, реплика={utterance_seq})"
                                            )
                                        else:
                                            logger.warning("⚠️ No RTP address available for playback (fallback)")
                                except Exception as synth_err:
                                    logger.warning(f"⚠️ TTS synth/playback error for fallback: {synth_err}")
                                asyncio.create_task(
                                    self._save_transcription_async(
                                        role=ConversationRole.ASSISTANT,
                                        content=FALLBACK_AI_BOT_TEXT,
                                        channel_id=channel_id,
                                        call_id=channel_id,
                                        llm_model="DiFy",
                                    )
                                )
                        except Exception as e:
                            logger.error(f"❌ Error processing speech: {e}, traceback {traceback.format_exc()}")

                        # Reset buffer and counters
                        buffer.clear()
                        silence_frames = 0
                        speech_frames = 0
                        in_utterance = False
                        utterance_start_time = 0.0
                        last_speech_time = 0.0
                        pre_roll_frames.clear()

        except Exception as e:
            logger.error(f"❌ Error in RTP voice processor: {e}, traceback {traceback.format_exc()}")

    async def _handle_idle_disconnect_mechanism(
        self,
        channel_id: str,
        call_manager,
        rtp_addr,
        user_has_spoken: bool,
        asked_anything_prompted: bool,
        anything_prompt_time: float,
        current_time: float,
        last_user_speech_time: float,
        in_utterance: bool,
    ) -> tuple[bool, bool, float, bool, float]:
        """
        Handle idle disconnect mechanism with interrupt capability

        Args:
            channel_id: The channel ID
            call_manager: The call manager instance
            rtp_addr: RTP address for audio playback
            user_has_spoken: Whether user has spoken
            asked_anything_prompted: Whether the follow-up question was asked
            anything_prompt_time: When the follow-up question was asked
            current_time: Current time in the call

        Returns:
            tuple: (
            user_has_spoken,
            asked_anything_prompted,
            anything_prompt_time,
            call_should_end,
            last_user_speech_time
            )
        """
        try:
            # Время с момента последней речи пользователя
            time_since_user_spoke = (current_time - last_user_speech_time) if last_user_speech_time else None

            # Случай 1: пользователь ещё не говорил вообще — спросить через 5с с начала разговора
            if (
                (not user_has_spoken)
                and (not asked_anything_prompted)
                and current_time >= FIRST_PROMPT_AFTER_S
                and rtp_addr
            ):
                try:
                    question_audio = self.audio_manager.get_audio("question_initial")
                    if question_audio:
                        await call_manager.play_next(
                            question_audio,
                            rtp_addr,
                            frame_duration_ms=FRAME_MS,
                            sample_rate=SAMPLE_RATE,
                            payload_type=PAYLOAD_TYPE_G722,
                        )
                        asyncio.create_task(
                            self._save_transcription_async(
                                role=ConversationRole.ASSISTANT,
                                content=QUESTION_AI_BOT_TEXT,
                                channel_id=channel_id,
                                call_id=channel_id,
                            )
                        )
                        asked_anything_prompted = True
                        anything_prompt_time = current_time
                        logger.info(f"🎤 Задан вопрос ожидания для канала: {channel_id}")
                except Exception as _e:
                    logger.warning(f"⚠️ Не удалось воспроизвести вопрос ожидания: {_e}")
                    asked_anything_prompted = True
                    anything_prompt_time = current_time

            # Случай 2: пользователь уже говорил, но после этого тишина REPROMPT_AFTER_S — задать повторный вопрос
            if (
                (
                    user_has_spoken
                    and (not asked_anything_prompted)
                    and time_since_user_spoke is not None
                    and time_since_user_spoke >= REPROMPT_AFTER_S
                    and not in_utterance
                )
                and rtp_addr
                and not call_manager.is_playing()
            ):
                await asyncio.sleep(5)  # небольшая задержка перед проигрыванием
                try:
                    question_audio = self.audio_manager.get_audio("re_prompt_questions")
                    if question_audio:
                        await call_manager.play_next(
                            question_audio,
                            rtp_addr,
                            frame_duration_ms=FRAME_MS,
                            sample_rate=SAMPLE_RATE,
                            payload_type=PAYLOAD_TYPE_G722,
                        )
                        asyncio.create_task(
                            self._save_transcription_async(
                                role=ConversationRole.ASSISTANT,
                                content=QUESTION_ABOUT_QUESTION_AI_BOT_TEXT,
                                channel_id=channel_id,
                                call_id=channel_id,
                            )
                        )
                        asked_anything_prompted = True
                        anything_prompt_time = current_time
                        logger.info(f"🎤 Повторный вопрос ожидания для канала: {channel_id}")
                except Exception as _e:
                    logger.warning(f"⚠️ Не удалось воспроизвести повторный вопрос: {_e}")
                    asked_anything_prompted = True
                    anything_prompt_time = current_time
            if asked_anything_prompted and (current_time - anything_prompt_time) >= HANGUP_AFTER_S:
                logger.info(
                    f"📵 Нет ответа от пользователя после напоминания — завершаем звонок для канала: {channel_id}"
                )
                try:
                    # Остановим любое воспроизведение перед разрывом
                    if call_manager.is_playing():
                        call_manager.cancel_play()
                finally:
                    try:
                        if channel_id in self.call_resources:
                            rtp_task = self.call_resources[channel_id].get("rtp_task")
                            if rtp_task and not rtp_task.done():
                                rtp_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await rtp_task

                        await self.ari_client.hangup_channel(channel_id)

                        if channel_id in self.call_resources:
                            del self.call_resources[channel_id]
                        if channel_id in self.keep_alive_tasks:
                            del self.keep_alive_tasks[channel_id]

                        logger.info(f"📞 Звонок завершен для канала: {channel_id}")
                    except Exception as _e:
                        logger.warning(f"⚠️ Ошибка при завершении вызова для канала {channel_id}: {_e}")

                # Return special values to indicate call should end
                return True, True, anything_prompt_time, True, last_user_speech_time

        except Exception as _timer_e:
            logger.warning(f"Таймер ожидания речи для канала {channel_id}: {_timer_e}")

        return (
            user_has_spoken,
            asked_anything_prompted,
            anything_prompt_time,
            False,
            last_user_speech_time,
        )

    def _reset_idle_disconnect_state(self) -> tuple[bool, bool, float, bool]:
        """
        Reset idle disconnect mechanism state when user starts speaking

        Args:
            user_has_spoken: Current state
            asked_anything_prompted: Current state
            anything_prompt_time: Current state

        Returns:
            tuple: Reset state
            (
            user_has_spoken=True,
            asked_anything_prompted=False,
            anything_prompt_time=0.0,
            call_should_end=False,
            )
        """
        logger.info("🔄 Сброс состояния механизма отключения - пользователь начал говорить")
        return True, False, 0.0, False

    async def _play_filler_phrase(self, channel_id: str, call_manager):
        """Play a random filler phrase to reduce perceived LLM latency"""
        try:
            if channel_id not in self.call_resources:
                logger.warning(f"🗣️ Channel {channel_id} not found in call_resources")
                return

            filler_keys = [
                "filler_thinking",
                "filler_checking",
                "filler_wait",
                "filler_moment",
                "filler_searching",
                "filler_answering",
                "filler_verifying",
                "filler_preparing",
            ]

            filler_key = random.choice(filler_keys)

            audio_data = self.audio_manager.get_audio(filler_key)
            if not audio_data:
                logger.warning(f"🗣️ Filler audio not loaded: {filler_key}")
                return

            # Check RTP address
            rtp_addr = self.call_resources[channel_id].get("rtp_addr")
            if not rtp_addr:
                logger.warning(
                    f"🗣️ No RTP address available for channel {channel_id}. "
                    f"Call resources keys: {
                        list(self.call_resources[channel_id].keys())
                        if channel_id in self.call_resources
                        else 'NO_CHANNEL'
                    }"
                )
                return

            logger.info(f"🗣️ Playing filler: '{filler_key}' via RTP {rtp_addr}")

            # Play the filler (this will be interrupted if user speaks)
            await call_manager.play_next(
                audio_data,
                rtp_addr,
                frame_duration_ms=FRAME_MS,
                sample_rate=SAMPLE_RATE,
                payload_type=PAYLOAD_TYPE_G722,
            )

        except Exception as e:
            logger.error(f"🗣️ Failed to play filler: {e}, traceback: {traceback.format_exc()}")

    async def _cleanup_channel_resources(self, channel_id: str):
        """Clean up resources for a channel"""
        try:
            resources = self.call_resources.get(channel_id)
            if resources:
                # Safely get resource values with defaults
                bridge_id = resources.get("bridge_id")
                external_channel_id = resources.get("external_channel_id")
                rtp_task = resources.get("rtp_task")

                # Stop keep-alive task
                if channel_id in self.keep_alive_tasks:
                    keep_alive_task = self.keep_alive_tasks[channel_id]
                    if keep_alive_task and not keep_alive_task.done():
                        keep_alive_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await keep_alive_task
                    del self.keep_alive_tasks[channel_id]

                # Stop RTP listener task
                if rtp_task and not rtp_task.done():
                    rtp_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await rtp_task

                # Destroy external media channel
                if external_channel_id and self.ari_client:
                    try:
                        await self.ari_client.destroy_channel(external_channel_id)
                    except Exception as e:
                        logger.warning(f"⚠️ Error destroying external channel {external_channel_id}: {e}")

                # Destroy bridge
                if bridge_id and self.ari_client:
                    try:
                        await self.ari_client.destroy_bridge(bridge_id)
                    except Exception as e:
                        logger.warning(f"⚠️ Error destroying bridge {bridge_id}: {e}")

                # Save all cached transcriptions before cleanup
                try:
                    await self.database_manager.save_cached_transcriptions(channel_id)
                except Exception as e:
                    logger.error(f"❌ Error saving transcriptions for channel {channel_id}: {e}")

                # Clear transcription cache to prevent memory leaks
                self.database_manager.clear_transcription_cache(channel_id)

                # Clean up resources from the dictionary
                del self.call_resources[channel_id]
                logger.info(f"🧹 Cleaned up resources for channel: {channel_id}")

        except Exception as e:
            logger.warning(f"⚠️ Error during cleanup: {e}, traceback {traceback.format_exc()}")

    async def stop(self):
        """Stop the AI Bot service"""
        logger.info("🛑 Stopping Wazo AI Bot Service...")

        # Close database manager
        await self.database_manager.close_pool()

        # Close ARI client
        if self.ari_client:
            try:
                await self.ari_client.__aexit__(None, None, None)
                logger.info("✅ ARI client closed")
            except Exception as e:
                logger.error(f"❌ Error closing ARI client: {e}")

        # Cancel all RTP listener tasks
        for _, resources in self.call_resources.items():
            rtp_task = resources["rtp_task"]
            if rtp_task.done():
                rtp_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await rtp_task

        # Close STT session
        if self.speech_recognizer:
            try:
                await self.speech_recognizer.close()
                logger.info("✅ STT session closed")
            except Exception as e:
                logger.error(f"❌ Error closing STT session: {e}")

        # Close LLM session
        if self.llm_service:
            try:
                await self.llm_service.cleanup()
                logger.info("✅ LLM session closed")
            except Exception as e:
                logger.error(f"❌ Error closing LLM session: {e}")

        logger.info("✅ Wazo AI Bot Service stopped")
