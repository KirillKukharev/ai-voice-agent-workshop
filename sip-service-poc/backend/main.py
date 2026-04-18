import logging
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from .airtable_client import create_booking, create_ticket
from .events import EventBus, EventBusConfig
from .schemas import (
    BookingRequest,
    BookingResponse,
    DashboardEvent,
    GenericStatusResponse,
    ServiceTicketRequest,
    ServiceTicketResponse,
    TextQueryRequest,
)
from .websocket_manager import ConnectionManager

logger = logging.getLogger("hbf.middleware")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="HBF Concierge Middleware",
    description="WebSocket backend for receiving events from Dify and forwarding them to frontend dashboard",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connection_manager = ConnectionManager()

event_bus = EventBus(connection_manager, EventBusConfig())


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def get_event_bus() -> EventBus:
    return event_bus


api_router = APIRouter(prefix="/api")


@app.get("/health", tags=["service"])
async def healthcheck() -> dict:
    return {"status": "ok", "timestamp": _utc_now().isoformat()}


@api_router.post(
    "/events",
    tags=["events"],
    response_model=GenericStatusResponse,
)
async def push_event(event: DashboardEvent, bus: EventBus = Depends(get_event_bus)) -> GenericStatusResponse:
    """Receive events from Dify via webhook and forward them to WebSocket clients."""
    await bus.publish(event)
    return GenericStatusResponse(status="queued")


@api_router.post(
    "/text-query",
    tags=["integration"],
    response_model=GenericStatusResponse,
)
async def submit_text_query(request: TextQueryRequest, bus: EventBus = Depends(get_event_bus)) -> GenericStatusResponse:
    """
    Fallback: Manual text query submission for testing.
    Primarily used for testing without Wazo ARI.
    In production, requests come from Dify via /api/events.
    """
    if not request.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    transcription_event = DashboardEvent(
        event="user_transcription",
        payload={
            "text": request.query,
            "timestamp": _utc_now().isoformat(),
            "modality": "text",
        },
        session_id=request.session_id,
    )
    await bus.publish(transcription_event)

    return GenericStatusResponse(status="accepted")


@api_router.post(
    "/tickets",
    tags=["tools"],
    response_model=ServiceTicketResponse,
)
async def create_service_ticket(
    request: ServiceTicketRequest,
    bus: EventBus = Depends(get_event_bus),
) -> ServiceTicketResponse:
    """
    Create a service ticket (called by Dify tool create_service_ticket).

    Creates a ticket in Airtable and broadcasts ticket_created event to WebSocket clients.
    """
    try:
        # Create ticket in Airtable
        result = create_ticket(
            room_number=request.room_number,
            category=request.category,
            description=request.description,
            phone_number=request.phone_number,
        )

        ticket_id = result["ticket_id"]
        created_at = _utc_now()

        # Map category to department
        department = request.category  # "maintenance" or "housekeeping"

        # Create event payload
        ticket_payload = {
            "ticket_id": ticket_id,
            "department": department,
            "summary": request.description,
            "created_at": created_at.isoformat(),
        }

        # Broadcast event to WebSocket clients
        ticket_event = DashboardEvent(
            event="ticket_created",
            payload=ticket_payload,
            session_id=request.session_id,
        )
        await bus.publish(ticket_event)

        logger.info(
            "Ticket created successfully: id=%s, room=%s, category=%s, phone=%s",
            ticket_id,
            request.room_number,
            request.category,
            request.phone_number or "не указан",
        )
        logger.debug(
            "Airtable response: %s",
            result.get("record", {}),
        )

        return ServiceTicketResponse(
            ticket_id=ticket_id,
            status="created",
            payload={
                "ticket_id": ticket_id,
                "department": department,
                "summary": request.description,
                "created_at": created_at,
            },
        )
    except HTTPException as e:
        logger.error("Failed to create ticket: %s", e, exc_info=True)
        return HTTPException(status_code=500, detail=f"Failed to create ticket: {str(e)}")


@api_router.post(
    "/bookings",
    tags=["tools"],
    response_model=BookingResponse,
)
async def create_booking_endpoint(
    request: BookingRequest,
    bus: EventBus = Depends(get_event_bus),
) -> BookingResponse:
    """
    Create a booking (called by Dify tool create_booking).

    Creates a booking in Airtable and broadcasts booking_created event to WebSocket clients.
    """
    try:
        # Create booking in Airtable
        result = create_booking(
            service=request.service,
            date=request.date,
            time=request.time,
            guests_count=request.guests_count,
            guest_name=request.guest_name,
            phone_number=request.phone_number,
        )

        booking_id = result["booking_id"]
        created_at = _utc_now()

        # Format details string
        details = (
            f"Гость: {request.guest_name}; "
            f"услуга: {request.service}; "
            f"дата: {request.date}; "
            f"время: {request.time}; "
            f"гостей: {request.guests_count}"
        )

        # Create event payload
        booking_payload = {
            "booking_id": booking_id,
            "service": request.service,
            "details": details,
            "status": "confirmed",
            "guest_name": request.guest_name,
            "created_at": created_at.isoformat(),
        }

        # Broadcast event to WebSocket clients
        booking_event = DashboardEvent(
            event="booking_created",
            payload=booking_payload,
            session_id=request.session_id,
        )
        await bus.publish(booking_event)

        logger.info(
            "Booking created successfully: id=%s, service=%s, guest=%s, date=%s, time=%s, phone=%s",
            booking_id,
            request.service,
            request.guest_name,
            request.date,
            request.time,
            request.phone_number or "не указан",
        )
        logger.debug(
            "Airtable response: %s",
            result.get("record", {}),
        )

        return BookingResponse(
            booking_id=booking_id,
            status="confirmed",
            payload={
                "booking_id": booking_id,
                "service": request.service,
                "details": details,
                "status": "confirmed",
                "guest_name": request.guest_name,
                "created_at": created_at,
            },
        )
    except HTTPException as e:
        logger.error("Failed to create booking: %s", e, exc_info=True)
        return HTTPException(
            status_code=500,
            detail=f"Failed to create booking: {str(e)}",
        )


app.include_router(api_router)


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket, bus: EventBus = Depends(get_event_bus)) -> None:
    session_id = websocket.query_params.get("session_id")
    await connection_manager.connect(websocket, session_id=session_id)

    recent_events = await bus.replay(session_id)
    for event in recent_events:
        await websocket.send_json(event.model_dump())

    heartbeat = DashboardEvent(
        event="heartbeat",
        payload={"timestamp": _utc_now().isoformat()},
        session_id=session_id,
    )
    await bus.publish(heartbeat)

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "pong":
                connection_manager.mark_pong_received(websocket)
                logger.debug("Received pong from client, session_id=%s", session_id)
            else:
                logger.debug("Inbound WebSocket message ignored: %s", data)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected, session_id=%s", session_id)
    finally:
        await connection_manager.disconnect(websocket)
