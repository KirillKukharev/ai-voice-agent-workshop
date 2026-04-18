import asyncio
import json
import logging

import aiohttp
from pydantic import ValidationError

from ari_handler.models.event import Event

logger = logging.getLogger(__name__)


class AriClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str = "ariuser",
        password: str = "changeme",
        app: str = "voicebot",
    ):
        self._base_url = f"http://{host}:{port}/ari"
        self._ws_url = f"ws://{host}:{port}/ari/events?app={app}&subscribeAll=true"
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._ws = None
        self._ws_task = None
        self._running = False
        self._event_queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(auth=aiohttp.BasicAuth(self._username, self._password))
        await self._open_ws_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_ws_connection()
        if self._session:
            await self._session.close()

    def __aiter__(self):
        return self

    async def __anext__(self) -> Event:
        event = await self._event_queue.get()
        if event is None:
            raise StopAsyncIteration
        return event

    async def create_external_media(self, channel_id: str, app: str, external_host: str, format: str = "ulaw") -> None:
        """Create external media channel"""
        params = {
            "channelId": channel_id,
            "app": app,
            "external_host": external_host,
            "format": format,
            "encapsulation": "rtp",
            "transport": "udp",
            "connection_type": "client",
            "direction": "both",
        }
        response = await self._post("channels/externalMedia", params)
        if not response:
            raise ValueError("Post response is None")
        if response.status == 200:
            logger.info("✅ ExternalMedia created successfully")
        else:
            error_text = await response.text()
            raise Exception(f"Failed to create external media: {response.status} - {error_text}")

    async def start_recording(
        self,
        bridge_id: str,
        name: str,
        format: str = "wav",
        max_duration_seconds: int = 0,
        max_silence_seconds: int = 0,
        if_exists: str = "fail",
        beep: bool = True,
    ) -> None:
        """Start recording a bridge"""
        params = {
            "name": name,
            "format": format,
            "maxDurationSeconds": max_duration_seconds,
            "maxSilenceSeconds": max_silence_seconds,
            "ifExists": if_exists,
            "beep": str(beep).lower(),
        }
        response = await self._post(f"bridges/{bridge_id}/record", params)
        if not response:
            raise ValueError("Post response is None")
        if response.status == 201:
            logger.info(f"✅ Bridge recording started: {name}")
        else:
            error_text = await response.text()
            raise Exception(f"Failed to start recording on bridge {bridge_id}: {response.status} - {error_text}")

    async def start_channel_recording(
        self,
        channel_id: str,
        name: str,
        format: str = "wav",
        max_duration_seconds: int = 0,
        max_silence_seconds: int = 0,
        if_exists: str = "fail",
        beep: bool = True,
    ) -> dict:
        """Start recording a channel"""
        params = {
            "name": name,
            "format": format,
            "maxDurationSeconds": max_duration_seconds,
            "maxSilenceSeconds": max_silence_seconds,
            "ifExists": if_exists,
            "beep": str(beep).lower(),
        }
        response = await self._post(f"channels/{channel_id}/record", params)
        if not response:
            raise ValueError("Post response is None")
        if response.status == 201:
            recording_data = await response.json()
            logger.info(f"✅ Channel recording started: {name}")
            return recording_data
        else:
            error_text = await response.text()
            raise Exception(f"Failed to start recording on channel {channel_id}: {response.status} - {error_text}")

    async def stop_channel_recording(
        self,
        channel_id: str,
        recording_name: str,
    ) -> None:
        """Stop recording a channel"""
        url = f"{self._base_url}/channels/{channel_id}/record/{recording_name}"
        if not self._session:
            raise ValueError("Session is not initialized")
        async with self._session.delete(url) as response:
            if response.status != 204:
                error_text = await response.text()
                raise Exception(f"Failed to stop recording on channel {channel_id}: {response.status} - {error_text}")
            logger.info(f"✅ Channel recording stopped: {recording_name}")

    async def play_media(self, channel_id: str, media: str) -> None:
        """Play media to a channel"""
        url = f"{self._base_url}/channels/{channel_id}/play"
        data = {"media": media}
        if not self._session:
            raise ValueError("Session is not initialized")
        async with self._session.post(url, json=data) as response:
            if response.status not in [200, 201]:
                error_text = await response.text()
                raise Exception(f"Failed to play media to channel {channel_id}: {response.status} - {error_text}")
            playback_data = await response.json()
            logger.info(f"🎵 Started playback on channel {channel_id}: {playback_data.get('id')}")
            return playback_data

    async def create_bridge(self, bridge_type: str = "mixing") -> str:
        """Create a bridge"""
        params = {"type": bridge_type}
        response = await self._post("bridges", params)
        if not response:
            raise ValueError("Post response is None")
        if response.status == 200:
            bridge = await response.json()
            bridge_id = bridge.get("id")
            if not bridge_id:
                raise Exception("Bridge created but no ID returned")
            logger.info(f"✅ Bridge created successfully: {bridge_id}")
            return bridge_id
        else:
            error_text = await response.text()
            raise Exception(f"Failed to create bridge: {response.status} - {error_text}")

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        """Add a channel to a bridge"""
        params = {"channel": channel_id}
        response = await self._post(f"bridges/{bridge_id}/addChannel", params)
        if not response:
            raise ValueError("Post response error")
        if response.status == 204:
            logger.info(f"✅ Channel {channel_id} added to bridge {bridge_id} successfully")
        else:
            error_text = await response.text()
            raise Exception(
                f"Failed to add channel {channel_id} to bridge {bridge_id}: {response.status} - {error_text}"
            )

    async def answer_channel(self, channel_id: str) -> None:
        """Answer a channel"""
        url = f"{self._base_url}/channels/{channel_id}/answer"
        if not self._session:
            raise ValueError("Session is not initialized")
        async with self._session.post(url) as response:
            if response.status != 204:
                error_text = await response.text()
                raise Exception(f"Failed to answer channel {channel_id}: {response.status} - {error_text}")
            logger.info(f"✅ Answered channel: {channel_id}")
        return None

    async def set_channel_variable(self, channel_id: str, variable: str, value: str) -> None:
        """Set a channel variable"""
        params = {
            "variable": variable,
            "value": value,
        }
        response = await self._post(f"channels/{channel_id}/variable", params)
        if not response:
            raise ValueError("Post response is None")
        if response.status == 204:
            logger.info(f"✅ Set channel variable {variable}={value} for channel {channel_id}")
        else:
            error_text = await response.text()
            logger.warning(
                f"Failed to set channel variable {variable} for channel {channel_id}: {response.status} - {error_text}"
            )

    async def _post(self, endpoint: str, params: dict) -> aiohttp.ClientResponse | None:
        url = f"{self._base_url}/{endpoint}"
        logger.info("POST URL: %s | Params: %s", url, params)

        max_retries = 5
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                if not self._session:
                    raise ValueError("Session is None")
                async with self._session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    text = await response.text()
                    logger.debug("Response [%s]: %s", response.status, text)
                    return response
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ ARI request failed (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Более мягкий exponential backoff: 2s, 3s, 4.5s, 6.75s
                else:
                    logger.error(f"❌ ARI request failed after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"❌ Unexpected error in ARI request: {e}")
                raise
        return None

    async def _ws_connection_worker(self):
        max_reconnect_attempts = 8
        reconnect_delay = 3.0

        for attempt in range(max_reconnect_attempts):
            try:
                async with self._session.ws_connect(self._ws_url, timeout=aiohttp.ClientTimeout(total=60)) as websocket:
                    self._ws = websocket
                    logger.info(f"✅ WebSocket connected to {self._ws_url}")

                    while self._running:
                        try:
                            msg = await websocket.receive()

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.info("WebSocket closed by server.")
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"WebSocket error: {msg}")
                                break

                        except Exception as e:
                            logger.error(f"Error in WebSocket connection: {e}")
                            break

                    # Если соединение закрылось нормально, выходим из цикла
                    if not self._running:
                        break

            except Exception as e:
                if attempt < max_reconnect_attempts - 1:
                    logger.warning(
                        f"⚠️ WebSocket connection failed (attempt {attempt + 1}/{max_reconnect_attempts}): {e}"
                    )
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay *= 1.5
                else:
                    logger.error(f"❌ WebSocket connection failed after {max_reconnect_attempts} attempts: {e}")
                    raise

    async def _handle_message(self, message: str):
        try:
            event = Event.model_validate_json(message)
            logger.debug(f"Received event: {event.type}")
            await self._event_queue.put(event)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message: {e}")
            logger.debug(f"Raw message: {message}")
        except ValidationError as e:
            logger.error(f"Validation error for event: {e}")
            logger.debug(f"Raw message: {message}")
        except Exception as e:
            logger.error(f"Unexpected error handling message: {e}")
            logger.debug(f"Raw message: {message}")

    async def _open_ws_connection(self):
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_connection_worker())
        logger.info("WebSocket connection established.")

    async def _close_ws_connection(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._ws_task:
            await self._ws_task
        logger.info("WebSocket connection closed.")

    async def hangup_channel(self, channel_id: str):
        """Hangup a channel"""
        url = f"{self._base_url}/channels/{channel_id}"
        if not self._session:
            raise ValueError("Session is None")
        async with self._session.delete(url) as response:
            if response.status not in [
                204,
                404,
            ]:  # 404 is OK if channel already hung up
                error_text = await response.text()
                raise Exception(f"Failed to hangup channel {channel_id}: {response.status} - {error_text}")
            logger.info(f"📞 Hung up channel: {channel_id}")

    async def destroy_bridge(self, bridge_id: str):
        """Destroy a bridge"""
        url = f"{self._base_url}/bridges/{bridge_id}"
        if not self._session:
            raise ValueError("Session is None")
        async with self._session.delete(url) as response:
            if response.status not in [
                204,
                404,
            ]:  # 404 is OK if bridge already destroyed
                error_text = await response.text()
                raise Exception(f"Failed to destroy bridge {bridge_id}: {response.status} - {error_text}")
            logger.info(f"🗑️  Destroyed bridge: {bridge_id}")

    async def destroy_channel(self, channel_id: str):
        """Destroy a channel"""
        url = f"{self._base_url}/channels/{channel_id}"
        if not self._session:
            raise ValueError("Session is None")
        async with self._session.delete(url) as response:
            if response.status not in [
                204,
                404,
            ]:  # 404 is OK if channel already destroyed
                error_text = await response.text()
                raise Exception(f"Failed to destroy channel {channel_id}: {response.status} - {error_text}")
            logger.info(f"🗑️ Destroyed channel: {channel_id}")

    async def get_channel_info(self, channel_id: str) -> dict:
        """Get channel information (keep-alive ping)"""
        url = f"{self._base_url}/channels/{channel_id}"
        if not self._session:
            raise ValueError("Session is None")
        async with self._session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"📊 Channel info retrieved: {channel_id}")
                return data
            else:
                error_text = await response.text()
                raise Exception(f"Failed to get channel info {channel_id}: {response.status} - {error_text}")

    async def get_bridge_info(self, bridge_id: str) -> dict:
        """Get bridge information (keep-alive ping)"""
        url = f"{self._base_url}/bridges/{bridge_id}"
        if not self._session:
            raise ValueError("Session is None")
        async with self._session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"📊 Bridge info retrieved: {bridge_id}")
                return data
            else:
                error_text = await response.text()
                raise Exception(f"Failed to get bridge info {bridge_id}: {response.status} - {error_text}")
