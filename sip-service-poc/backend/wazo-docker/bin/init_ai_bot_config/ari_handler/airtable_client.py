from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pyairtable import Api

_airtable_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Airtable-Worker")


def get_airtable_executor() -> ThreadPoolExecutor:
    return _airtable_executor


logger = logging.getLogger("ari_handler.airtable")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TICKETS_TABLE = os.getenv("AIRTABLE_TICKETS_TABLE", "")
AIRTABLE_BOOKINGS_TABLE = os.getenv("AIRTABLE_BOOKINGS_TABLE", "")

_airtable_api: Api | None = None


def get_airtable_api() -> Api:
    """Get or create Airtable API client."""
    global _airtable_api
    if _airtable_api is None:
        if not AIRTABLE_API_KEY:
            raise ValueError("AIRTABLE_API_KEY environment variable is not set")
        if not AIRTABLE_BASE_ID:
            raise ValueError("AIRTABLE_BASE_ID environment variable is not set")
        _airtable_api = Api(AIRTABLE_API_KEY)
    return _airtable_api


def read_tickets(
    limit: int = 100,
) -> dict[str, Any]:
    """
    Read all tickets from Airtable (read-only, no filtering on Airtable side).

    Args:
        limit: Maximum number of records to return from Airtable

    Returns:
        Dictionary with tickets list (all records, filtering done client-side)
    """

    try:
        api = get_airtable_api()

        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TICKETS_TABLE)

        try:
            records = table.all(max_records=limit)

        except Exception as e:
            logger.error(f"Error reading tickets: {e}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}", exc_info=True)
            records = []

        return {
            "tickets": records,
            "count": len(records),
        }
    except Exception as e:
        logger.error("Failed to read tickets from Airtable: %s", e, exc_info=True)
        raise


def read_bookings(limit: int = 100) -> dict[str, Any]:
    """
    Read all bookings from Airtable (read-only, no filtering on Airtable side).

    Args:
        limit: Maximum number of records to return from Airtable

    Returns:
        Dictionary with bookings list (all records, filtering done client-side)
    """

    try:
        api = get_airtable_api()
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_BOOKINGS_TABLE)

        try:
            records = table.all(max_records=limit)

        except Exception as e:
            logger.error(f"Error reading bookings: {e}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}", exc_info=True)
            records = []

        return {
            "bookings": records,
            "count": len(records),
        }
    except Exception as e:
        logger.error("Failed to read bookings from Airtable: %s", e, exc_info=True)
        raise


def check_booking_availability(
    service: str,
    date: str,
    time: str,
) -> dict[str, Any]:
    """
    Check if a booking slot is available.

    Args:
        service: Service type (restaurant or spa)
        date: Booking date in YYYY-MM-DD format
        time: Booking time in HH:MM format

    Returns:
        Dictionary with available status and alternative times if conflict
    """
    try:
        api = get_airtable_api()
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_BOOKINGS_TABLE)

        formula = f"AND({{date}} = '{date}', {{time}} = '{time}')"

        logger.info(
            "Checking booking availability in Airtable: service=%s, date=%s, time=%s",
            service,
            date,
            time,
        )
        logger.debug("   Formula: %s", formula)

        existing = table.all(formula=formula)

        if existing:
            logger.info(
                "Booking conflict found: %d existing bookings at %s %s",
                len(existing),
                date,
                time,
            )
            date_formula = f"{{date}} = '{date}'"
            all_bookings = table.all(formula=date_formula)
            logger.debug("📅 All bookings for date %s: %d records", date, len(all_bookings))

            return {
                "available": False,
                "conflict": True,
                "alternatives": ["18:30", "20:00"],
            }

        return {
            "available": True,
            "conflict": False,
        }
    except Exception as e:
        logger.error("Failed to check booking availability: %s", e, exc_info=True)
        return {
            "available": True,
            "conflict": False,
        }
