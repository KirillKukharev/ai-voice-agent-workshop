import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

import aiohttp
from config.settings import app_settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(
        self,
        tool_call_handler: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        self.nocode_base = app_settings.NOCODE_BASE_URL
        self.nocode_api_key = app_settings.NOCODE_API_KEY

        if not self.nocode_api_key:
            raise ValueError("NOCODE_API_KEY is required in environment.")

        self._conversation_by_user: dict[str, str] = {}
        self._session = None
        self.tool_call_handler = tool_call_handler

        logger.info("🧠 LLM Service initialized with Dify integration")

    def _get_session(self):
        """Get or create HTTP session with connection pooling."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                keepalive_timeout=300,
                enable_cleanup_closed=True,
                use_dns_cache=True,
                ttl_dns_cache=600,
            )
            timeout = aiohttp.ClientTimeout(total=60, sock_connect=5, sock_read=55)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            logger.info("LLM HTTP session created with connection pooling")
        return self._session

    async def cleanup(self):
        """Clean up HTTP session resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("🔌 LLM HTTP session closed")

    async def stream_generate_with_context(
        self,
        query_text: str,
        meta_user: str,
    ) -> AsyncIterator[str]:
        """Stream via nocode SSE endpoint; emit raw 'answer' chunks immediately"""

        url = f"{self.nocode_base}/v1/chat-messages"
        headers = {
            "Authorization": f"Bearer {self.nocode_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        conversation_id = self._conversation_by_user.get(meta_user)

        payload = {
            "inputs": {},
            "query": query_text,
            "response_mode": "streaming",
            "conversation_id": conversation_id or "",
            "user": "unknown",
        }
        loop = asyncio.get_event_loop()
        start_total = loop.time()
        first_token_ms: int | None = None
        session = self._get_session()
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                txt = await resp.text()
                logger.error(f"nocode stream HTTP {resp.status}: {txt}")
                return

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="ignore").strip()

                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                ev = json.loads(data_str)

                ev_type = ev.get("event")
                if ev_type == "message":
                    conv_id = ev.get("conversation_id")
                    if conv_id and meta_user and not self._conversation_by_user.get(meta_user):
                        self._conversation_by_user[meta_user] = conv_id
                        logger.info(f"DiFy: conversation_id set for user '{meta_user}': {conv_id}")
                    ans = ev.get("answer")
                    if ans:
                        if first_token_ms is None:
                            first_token_ms = int((loop.time() - start_total) * 1000)
                            logger.info(f"⏱️ DiFy stream TTFB: {first_token_ms} ms")
                        yield ans
                elif ev_type == "message_end":
                    total_ms = int((loop.time() - start_total) * 1000)
                    time_to_first_token = ev.get("time_to_first_token")
                    logger.info(f"⏱️ DiFy total time, time to first token: {total_ms} ms, {time_to_first_token} ms")
                    return
                elif ev_type in ("tool_call", "function_call", "agent_thought"):
                    try:
                        tool_name = ev.get("tool_name") or ev.get("function_name") or ev.get("name")
                        tool_inputs = (
                            ev.get("tool_inputs")
                            or ev.get("function_inputs")
                            or ev.get("inputs")
                            or ev.get("tool_parameters")
                            or {}
                        )
                        if not tool_name and "tool_calls" in ev:
                            for tc in ev.get("tool_calls", []):
                                tn = tc.get("tool_name") or tc.get("function_name") or tc.get("name")
                                ti = tc.get("tool_inputs") or tc.get("function_inputs") or tc.get("inputs") or {}
                                if tn and self.tool_call_handler:
                                    asyncio.create_task(
                                        self.tool_call_handler(
                                            tool_name=tn,
                                            tool_inputs=ti,
                                            conversation_id=ev.get("conversation_id"),
                                            user=meta_user,
                                        )
                                    )
                        elif tool_name and self.tool_call_handler:
                            logger.info(
                                "Dify tool call (stream): %s, inputs: %s",
                                tool_name,
                                tool_inputs,
                            )
                            asyncio.create_task(
                                self.tool_call_handler(
                                    tool_name=tool_name,
                                    tool_inputs=tool_inputs,
                                    conversation_id=ev.get("conversation_id"),
                                    user=meta_user,
                                )
                            )
                    except Exception as e:
                        logger.error("Failed to handle tool call: %s", e, exc_info=True)
