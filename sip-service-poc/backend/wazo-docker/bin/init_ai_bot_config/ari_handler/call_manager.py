import asyncio
import contextlib
import logging
import random
import socket
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class CallManager:
    _queue_worker_task: asyncio.Task | None = None
    _current_playback_task: asyncio.Task | None = None
    _response_playback_task_queue: asyncio.Queue | None = None

    def __init__(self, ip: str, port: int):
        """
        Initializes the Manager with the given IP address and port.

        :param ip: The IP address to bind the socket to.
        :param port: The port number to bind the socket to.
        """
        self._ip = ip
        self._port = port

    async def __aenter__(self) -> "CallManager":
        """
        Initializes the context manager by creating a UDP socket and binding it to the specified IP and port.
        This method is called when entering the context manager.

        :return: The instance of the Manager class.
        """
        # Create a UDP socket
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set SO_REUSEADDR to allow port reuse
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Try to bind to the specified port, if it fails, use a dynamic port
        try:
            self._sock.bind((self._ip, self._port))
            logger.info(f"Successfully bound to port: {self._port}")
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning(f"Port {self._port} already in use, using dynamic port")
                self._sock.bind((self._ip, 0))  # Let system choose port
                self._port = self._sock.getsockname()[1]  # Update port
                logger.info(f"Using dynamic port: {self._port}")
            else:
                raise
        self._sock.setblocking(False)

        # Initialize the playback task queue
        self._response_playback_task_queue = asyncio.Queue()

        # Create a task to process the playback task queue
        self._queue_worker_task = asyncio.create_task(self._process_playback_task_queue())

        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        """
        Handles cleanup when exiting the context manager.
        Closes the socket and logs any exceptions that occurred.

        :param exc_type: The type of the exception raised, if any.
        :param exc_value: The value of the exception raised, if any.
        :param traceback: The traceback object, if any.
        :return: True to suppress the exception, False to propagate it.
        """
        # Log any exception that occurred (except CancelledError which is normal during cleanup)
        if exc_type is not None and exc_type != asyncio.CancelledError:
            logger.error("An error occurred: %s %s", type(exc_value), exc_value)
        elif exc_type == asyncio.CancelledError:
            logger.debug("CallManager cleanup: CancelledError (normal during cleanup)")

        self.cancel_play()

        # Cancel the queue worker task if it's running
        if self._queue_worker_task and not self._queue_worker_task.done():
            self._queue_worker_task.cancel()
            logger.info("Cancelled queue worker task.")

        if self._sock:
            self._sock.close()
            self._sock = None  # type: ignore
            logger.info("Socket closed.")

        return exc_type == asyncio.CancelledError

    async def audio_channel(self, packet_size: int = 2048) -> AsyncGenerator[tuple[bytes, tuple[str, int]], None]:
        """
        Asynchronous generator for receiving audio data from an RTP stream.

        :param packet_size: The size of the packet to receive, default is 2048 bytes.
        :rtype: AsyncGenerator[tuple[bytes, tuple[str, int]], None]
        :return: An asynchronous generator that yields tuples of audio data and the sender's address.
        """
        if not self._sock:
            raise RuntimeError("Socket is not initialized.")
        if packet_size < 12:
            raise ValueError("Packet size must be at least 12 bytes to accommodate RTP header.")
        loop = asyncio.get_running_loop()
        while True:
            data, addr = await loop.sock_recvfrom(self._sock, packet_size)
            if not data:  # TODO if call muted data can be empty
                break

            # Validate RTP packet (minimum 12 bytes for header)
            if len(data) < 12:
                logger.warning(f"Received packet too small: {len(data)} bytes")
                continue

            # Check RTP version (should be 2)
            rtp_version = (data[0] >> 6) & 0x03
            if rtp_version != 2:
                logger.warning(f"Invalid RTP version: {rtp_version}")
                continue

            # Check payload type (should be 0 for PCMU/ulaw or 8 for PCMA)
            payload_type = data[1] & 0x7F
            if payload_type not in [0, 8, 9]:
                logger.warning(f"Unexpected payload type: {payload_type}, expected 0 (PCMU), 8 (PCMA), or 9 (G.722)")
                continue

            # Extract payload (skip 12-byte RTP header)
            payload = data[12:]
            if payload:
                yield payload, addr

    async def audio_channel_with_pt(
        self, packet_size: int = 2048
    ) -> AsyncGenerator[tuple[bytes, tuple[str, int], int], None]:
        """
        Asynchronous generator for receiving audio data from an RTP stream, including payload type.

        :param packet_size: The size of the packet to receive, default is 2048 bytes.
        :rtype: AsyncGenerator[tuple[bytes, tuple[str, int], int], None]
        :return: Yields (payload_bytes, sender_addr, payload_type). payload_type: 0=PCMU, 8=PCMA, 9=G.722.
        """
        if not self._sock:
            raise RuntimeError("Socket is not initialized.")
        if packet_size < 12:
            raise ValueError("Packet size must be at least 12 bytes to accommodate RTP header.")
        loop = asyncio.get_running_loop()
        while True:
            data, addr = await loop.sock_recvfrom(self._sock, packet_size)
            if not data:
                break

            if len(data) < 12:
                logger.warning(f"Received packet too small: {len(data)} bytes")
                continue

            rtp_version = (data[0] >> 6) & 0x03
            if rtp_version != 2:
                logger.warning(f"Invalid RTP version: {rtp_version}")
                continue

            payload_type = data[1] & 0x7F
            if payload_type not in [0, 8, 9]:
                logger.warning(f"Unexpected payload type: {payload_type}, expected 0 (PCMU), 8 (PCMA), or 9 (G.722)")
                continue

            payload = data[12:]
            if payload:
                yield payload, addr, payload_type

    async def play_next(
        self,
        audio_data: bytes,
        addr: tuple[str, int],
        sample_rate: int = 8000,
        frame_duration_ms: int = 20,
        payload_type: int = 0,
    ) -> None:
        """
        Plays the given audio data to the specified address using RTP when the playback task queue is available.

        :param audio_data: The audio data to play.
        :param addr: The address (IP, port) to send the audio data to.
        :param sample_rate: The sample rate of the audio data, default is 8000 Hz.
        :param frame_duration_ms: The duration of each audio frame in milliseconds, default is 20 ms.
        :raises RuntimeError: If the playback task queue is not initialized.
        """
        if not self._response_playback_task_queue:
            raise RuntimeError("Playback task queue is not initialized.")

        await self._response_playback_task_queue.put(
            self._stream_bytes_to_socket(audio_data, addr, sample_rate, frame_duration_ms, payload_type)
        )
        logger.info(
            "Current tasks in playback queue: %s",
            self._response_playback_task_queue.qsize(),
        )

    def is_playing(self) -> bool:
        """
        Checks if there are any playback tasks currently in the queue.

        :return: True if there are playback tasks in the queue, False otherwise.
        """
        if self._current_playback_task and not self._current_playback_task.done():
            return True
        if not self._response_playback_task_queue:
            return False
        return not self._response_playback_task_queue.empty()

    def cancel_play(self) -> None:
        """
        Cancels the current playback task if it is running.
        This method will remove all tasks from the playback queue.
        """
        if not self._response_playback_task_queue:
            return

        # Cancel all tasks in the playback task queue
        self._empty_playback_task_queue()
        logger.info("Cancelled all playback tasks in the queue.")

        # Cancel the current playback task if it is running
        if self._current_playback_task and not self._current_playback_task.done():
            self._current_playback_task.cancel()
            logger.info("Cancelled current playback task.")

    async def _process_playback_task_queue(self) -> None:
        logger.info("Starting playback task queue worker...")
        while True:
            try:
                self._current_playback_task = None
                logger.info("Waiting for playback task in the queue...")
                playback_coroutine = (
                    await self._response_playback_task_queue.get() if self._response_playback_task_queue else None
                )

                logger.info("Playback task received, processing...")
                self._current_playback_task = asyncio.create_task(self._run_playback_task(playback_coroutine))
                try:
                    await self._current_playback_task
                except asyncio.CancelledError:
                    logger.info("Playback task was cancelled.")
                    raise  # Re-raise to properly handle cancellation
            except asyncio.CancelledError:
                logger.info("Playback task was cancelled.")

    async def _run_playback_task(self, playback_task) -> None:
        """
        Runs the given playback task and handles any exceptions that may occur.

        :param playback_task: The playback task to run.
        """
        try:
            await playback_task
        except Exception as e:
            logger.exception(f"Playback task raised an exception: {e}")
        finally:
            self._response_playback_task_queue.task_done() if self._response_playback_task_queue else None

    def _empty_playback_task_queue(self) -> None:
        """Empties the given asyncio queue by consuming all items without processing them."""
        if not self._response_playback_task_queue:
            return

        while not self._response_playback_task_queue.empty():
            item = self._response_playback_task_queue.get_nowait()
            # If we stored raw coroutine objects, close them to avoid 'never awaited' warnings
            if asyncio.iscoroutine(item):
                with contextlib.suppress(Exception):
                    item.close()
            # If we ever enqueue Tasks, cancel them
            elif isinstance(item, asyncio.Task):
                with contextlib.suppress(Exception):
                    item.cancel()
            self._response_playback_task_queue.task_done()

    async def _stream_bytes_to_socket(
        self,
        audio_data: bytes,
        addr: tuple[str, int],
        sample_rate: int = 8000,
        frame_duration_ms: int = 20,
        payload_type: int = 0,
    ) -> None:
        """
        Streams audio data as RTP packets to the specified address.

        :param audio_data: The audio data to stream.
        :param addr: The address (IP, port) to send the audio data to.
        :param sample_rate: The sample rate of the audio data, default is 8000 Hz.
        :param frame_duration_ms: The duration of each audio frame in milliseconds, default is 20 ms.
        """
        loop = asyncio.get_running_loop()

        # Calculate frame size based on payload type
        if payload_type == 9:  # G.722
            rtp_clock_rate = 8000
            frame_size = int((64000 // 8) * (frame_duration_ms / 1000))
        else:
            rtp_clock_rate = sample_rate
            frame_size = int(sample_rate / 1000 * frame_duration_ms)

        rtp_header = self._generate_initial_rtp_header(payload_type)

        timestamp = 0
        samples_per_frame = int(rtp_clock_rate / 1000 * frame_duration_ms)
        for i in range(0, len(audio_data), frame_size):
            payload = audio_data[i : i + frame_size]

            # Update RTP header with sequence number and timestamp
            rtp_header[2:4] = i.to_bytes(2, "big")
            rtp_header[4:8] = timestamp.to_bytes(4, "big")

            packet = rtp_header + payload
            await loop.sock_sendto(self._sock, packet, addr)

            timestamp += samples_per_frame

            await asyncio.sleep(frame_duration_ms / 1000)

    def _generate_initial_rtp_header(self, payload_type: int = 0):
        """
        Generates an initial RTP header with a random SSRC.

        :param payload_type: RTP payload type (0=PCMU, 8=PCMA, 9=G.722)
        :return: A bytearray representing the RTP header.
        """
        ssrc = random.randint(0, 0xFFFFFFFF)
        return bytearray(
            [
                0x80,  # Version 2, no padding, no extension
                payload_type & 0x7F,  # Payload type
                0x00,
                0x00,  # Sequence number
                0x00,
                0x00,
                0x00,
                0x00,  # Timestamp
                (ssrc >> 24) & 0xFF,
                (ssrc >> 16) & 0xFF,
                (ssrc >> 8) & 0xFF,
                ssrc & 0xFF,
            ]
        )
