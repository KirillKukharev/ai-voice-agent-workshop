"""
Google Calendar tool for Asterisk AI Voice Agent.

Supports listing events, getting a single event, creating events, deleting events, and finding
free appointment slots: template mode (Open/busy prefixes) and hourly grid fallback (step e.g. 60 min)
within appointment_hours_local, overlapping real events except transparent / ignored / Open templates.

Datetime handling is DST-aware: when a datetime string has a TZ tail (e.g. Z or +00:00),
the tail is removed and the date/time is interpreted as local time in the calendar timezone
(GOOGLE_CALENDAR_TZ, or TZ env, or UTC)—same as when there is no tail. List/time-range APIs
receive RFC3339 with the correct offset for that zone.

Environment: GOOGLE_CALENDAR_CREDENTIALS (path to service account JSON);
GOOGLE_CALENDAR_TZ for timezone (fallback: TZ).
"""

import asyncio
import structlog
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from src.tools.base import Tool, ToolDefinition, ToolCategory
from src.tools.context import ToolExecutionContext

from src.tools.business.gcalendar import GCalendar, _get_timezone

logger = structlog.get_logger(__name__)

# Schema for Google Live / Vertex and OpenAI (input_schema is provider-agnostic)
_GOOGLE_CALENDAR_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["list_events", "get_event", "create_event", "delete_event", "get_free_slots"],
            "description": "Required. Which operation to run. Always set this field explicitly (e.g. get_free_slots for availability, list_events to read events, create_event to book)."
        },
        "time_min": {
            "type": "string",
            "description": "ISO 8601 start time. Required for list_events and get_free_slots."
        },
        "time_max": {
            "type": "string",
            "description": "ISO 8601 end time. Required for list_events and get_free_slots."
        },
        "free_prefix": {
            "type": "string",
            "description": "Prefix of calendar events that mark working hours templates (e.g. 'Open'). Required for get_free_slots when slot_strategy is auto or templates (or set in tool config)."
        },
        "busy_prefix": {
            "type": "string",
            "description": "Prefix of events that mark booked slots in template mode (e.g. 'FOG'). Required for auto/templates unless set in config. Ignored for slot_strategy hourly."
        },
        "duration": {
            "type": "integer",
            "description": "Appointment duration in minutes. Used by get_free_slots to return only start times where this many minutes fit. Slot start times are aligned to multiples of this duration (e.g. 15 min -> :00, :15, :30, :45; 30 min -> :00, :30)."
        },
        "slot_strategy": {
            "type": "string",
            "enum": ["auto", "templates", "hourly"],
            "description": "get_free_slots only: auto = template mode if free_prefix and busy_prefix are set (call or config), otherwise same as hourly; templates = only Open/FOG-style windows (prefixes required); hourly = grid by slot_step_minutes, overlap vs real events.",
        },
        "slot_step_minutes": {
            "type": "integer",
            "description": "get_free_slots hourly mode: grid step in minutes (default 60 = starts at :00 each hour).",
        },
        "event_id": {
            "type": "string",
            "description": "The exact ID of the event. Required for get_event and delete_event."
        },
        "summary": {
            "type": "string",
            "description": "Title of the event. Required for create_event."
        },
        "description": {
            "type": "string",
            "description": "Detailed description of the event. Optional for create_event."
        },
        "start_datetime": {
            "type": "string",
            "description": "ISO 8601 start time for the new event. Required for create_event."
        },
        "end_datetime": {
            "type": "string",
            "description": "ISO 8601 end time for the new event. Required for create_event."
        }
    },
    "required": ["action"]
}


class GCalendarTool(Tool):
    """
    Generic tool for interacting with Google Calendar, extended with
    a custom slot availability calculator.
    Compatible with Google Live/Vertex and OpenAI via Asterisk-AI-Voice-Agent.
    """

    def __init__(self):
        super().__init__()
        logger.debug("Initializing GCalendarTool instance")
        self._cal = None
        self._cal_config_key = None

    def _get_cal(self, config: Dict[str, Any]) -> GCalendar:
        """Return a GCalendar instance, (re)creating if config changed or service is None."""
        creds_path = config.get("credentials_path", "")
        cal_id = config.get("calendar_id", "")
        tz = config.get("timezone", "")
        config_key = (creds_path, cal_id, tz)
        if self._cal is None or self._cal.service is None or self._cal_config_key != config_key:
            self._cal = GCalendar(credentials_path=creds_path, calendar_id=cal_id, timezone=tz)
            self._cal_config_key = config_key
        return self._cal

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="google_calendar",
            description=(
                "Google Calendar: list_events, get_event, create_event, delete_event, get_free_slots. "
                "Every tool call MUST include the string field \"action\" set to one of those five values. "
                "create_event rejects the slot if another (non-transparent) event already overlaps that time. "
                "get_free_slots: default slot_strategy auto uses calendar 'Open'+busy template events if any; "
                "otherwise (or if that yields no slots) falls back to hourly grid (e.g. 08:00, 09:00…) "
                "within time_min/time_max and appointment_hours_local, testing each start for a free window of "
                "`duration` minutes against real events. Prefer slot_strategy hourly or auto when templates "
                "are missing. For phone booking, create_event needs summary (short title, include caller name + topic), "
                "description (details), start_datetime and end_datetime (ISO 8601; interpreted in the "
                "calendar timezone from config). Use list_events or get_free_slots to probe availability first."
            ),
            category=ToolCategory.BUSINESS,
            requires_channel=False,
            max_execution_time=30,
            input_schema=_GOOGLE_CALENDAR_INPUT_SCHEMA,
        )

    def _parse_iso(self, iso_str: str) -> datetime:
        """Helper to parse ISO strings, handling the 'Z' suffix if present."""
        if iso_str.endswith('Z'):
            iso_str = iso_str[:-1] + '+00:00'
        return datetime.fromisoformat(iso_str)

    def _get_calendar_tz_name(self, config: Dict[str, Any]) -> str:
        """Resolve calendar timezone: config timezone, then GOOGLE_CALENDAR_TZ, TZ, UTC."""
        return _get_timezone(config.get("timezone", ""))

    def _normalize_datetime_to_calendar_tz(
        self, dt_str: str, calendar_tz_name: str
    ) -> datetime:
        """
        Parse datetime string as local time in the calendar timezone (DST-aware).

        If dt_str has a TZ tail (Z or ±HH:MM): the tail is removed and the date/time
        is interpreted as local time in the calendar zone (same as when there is no tail).
        So "2025-03-15T19:00:00Z" is treated as 19:00 in the calendar zone, not as 19:00 UTC.

        Uses GOOGLE_CALENDAR_TZ / TZ for the calendar zone; falls back to UTC if invalid.
        """
        dt_str = (dt_str or "").strip()
        if not dt_str:
            raise ValueError("Empty datetime string")
        # Normalize Z for parsing, then parse
        if dt_str.upper().endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(dt_str)
        except ValueError as e:
            raise ValueError(f"Invalid datetime string: {dt_str}") from e

        try:
            cal_tz = ZoneInfo(calendar_tz_name)
        except Exception:
            cal_tz = ZoneInfo("UTC")

        # If there was a TZ tail, remove it: use only the wall-clock time (naive)
        # and interpret that as local time in the calendar zone (same as no tail).
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.replace(tzinfo=cal_tz)

    @staticmethod
    def _parse_hhmm_local(spec: str) -> int:
        """Minutes since midnight for '8', '8:30', '08:30' (calendar-local wall time)."""
        s = (spec or "").strip()
        if not s:
            raise ValueError("empty time")
        parts = s.replace(".", ":").split(":")
        h = int(parts[0].strip())
        m = int(parts[1].strip()) if len(parts) > 1 else 0
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"invalid clock time: {spec!r}")
        return h * 60 + m

    def _validate_appointment_hours_local(
        self,
        start_local: datetime,
        end_local: datetime,
        config: Dict[str, Any],
    ) -> Optional[str]:
        """Optional YAML ``appointment_hours_local`` guard for create_event."""
        spec = config.get("appointment_hours_local")
        if not spec or not isinstance(spec, dict):
            return None
        earliest = str(spec.get("earliest", "")).strip()
        latest_end = str(spec.get("latest_end", "")).strip()
        if not earliest and not latest_end:
            return None
        try:
            emin = self._parse_hhmm_local(earliest) if earliest else None
            lmax = self._parse_hhmm_local(latest_end) if latest_end else None
        except ValueError as e:
            logger.warning("Invalid appointment_hours_local in google_calendar config", error=str(e))
            return None

        if emin is not None:
            s_min = start_local.hour * 60 + start_local.minute
            if s_min < emin:
                return (
                    f"Ошибка: время начала вне графика приёма. "
                    f"Запись не раньше {earliest} (локальное время календаря). "
                    f"Предложи абоненту другое время и вызови create_event снова."
                )

        if lmax is not None:
            if end_local.date() != start_local.date():
                return (
                    "Ошибка: визит уходит за полночь; для этой линии запись только в пределах одного дня. "
                    "Выбери более раннее начало или короче длительность."
                )
            e_min = end_local.hour * 60 + end_local.minute
            if e_min > lmax:
                return (
                    f"Ошибка: приём заканчивается не позже {latest_end} (локальное время). "
                    f"Слот заканчивается слишком поздно — предложи более раннее начало или другую длительность."
                )
        return None

    def _parse_api_event_window(
        self,
        ev: Dict[str, Any],
        cal_tz: ZoneInfo,
    ) -> Optional[Tuple[datetime, datetime]]:
        """Return (start, end) for a Calendar API event item in cal_tz (end is wall-time end from API)."""
        start_obj = ev.get("start") or {}
        end_obj = ev.get("end") or {}
        dts = start_obj.get("dateTime")
        dte = end_obj.get("dateTime")
        if dts and dte:
            try:
                s = datetime.fromisoformat(str(dts).replace("Z", "+00:00"))
                e = datetime.fromisoformat(str(dte).replace("Z", "+00:00"))
                if s.tzinfo is None:
                    s = s.replace(tzinfo=cal_tz)
                else:
                    s = s.astimezone(cal_tz)
                if e.tzinfo is None:
                    e = e.replace(tzinfo=cal_tz)
                else:
                    e = e.astimezone(cal_tz)
                return s, e
            except ValueError:
                return None
        ds = start_obj.get("date")
        de = end_obj.get("date")
        if ds and de:
            try:
                from datetime import date as date_cls
                from datetime import time as time_cls

                d_start = date_cls.fromisoformat(str(ds))
                d_end_excl = date_cls.fromisoformat(str(de))
                s = datetime.combine(d_start, time_cls.min, tzinfo=cal_tz)
                e = datetime.combine(d_end_excl, time_cls.min, tzinfo=cal_tz)
                return s, e
            except ValueError:
                return None
        return None

    def _collect_create_event_conflicts(
        self,
        cal: GCalendar,
        slot_start: datetime,
        slot_end: datetime,
        calendar_tz_name: str,
        config: Dict[str, Any],
    ) -> List[str]:
        """Labels of calendar events overlapping [slot_start, slot_end)."""
        try:
            cal_tz = ZoneInfo(calendar_tz_name)
        except Exception:
            cal_tz = ZoneInfo("UTC")

        skip_transparent = bool(config.get("conflict_skip_transparent", True))
        ignore_prefixes: List[str] = []
        raw = config.get("conflict_ignore_summary_prefixes")
        if isinstance(raw, list):
            ignore_prefixes = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str) and raw.strip():
            ignore_prefixes = [raw.strip()]

        t_min = slot_start.isoformat()
        t_max = slot_end.isoformat()
        items = cal.list_events(t_min, t_max)
        out: List[str] = []
        for ev in items:
            if str(ev.get("status", "")).lower() == "cancelled":
                continue
            if skip_transparent and str(ev.get("transparency", "opaque") or "opaque") == "transparent":
                continue
            summ = (ev.get("summary") or "").strip()
            low = summ.lower()
            if any(summ.startswith(p) or low.startswith(p.lower()) for p in ignore_prefixes):
                continue
            w = self._parse_api_event_window(ev, cal_tz)
            if not w:
                continue
            es, ee = w
            if slot_start < ee and slot_end > es:
                out.append(summ[:220] if summ else "Событие без названия")
        return out

    @staticmethod
    def _align_up_to_step_minutes(dt: datetime, step_minutes: int) -> datetime:
        """Round dt up to the next clock time whose minutes-from-midnight is divisible by step."""
        step = max(1, int(step_minutes))
        mid = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        mins_total = int((dt - mid).total_seconds() // 60)
        q = (mins_total + step - 1) // step
        return mid + timedelta(minutes=q * step)

    def _hourly_grid_slot_blocked(
        self,
        slot_start: datetime,
        slot_end: datetime,
        events: List[Dict[str, Any]],
        cal_tz: ZoneInfo,
        config: Dict[str, Any],
        free_hours_prefix: str,
    ) -> bool:
        """True if an opaque event overlaps [slot_start, slot_end), excluding open-hours template events."""
        skip_transparent = bool(config.get("conflict_skip_transparent", True))
        ignore_prefixes: List[str] = []
        raw = config.get("conflict_ignore_summary_prefixes")
        if isinstance(raw, list):
            ignore_prefixes = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str) and raw.strip():
            ignore_prefixes = [raw.strip()]
        fp = (free_hours_prefix or "").strip()
        for ev in events:
            if str(ev.get("status", "")).lower() == "cancelled":
                continue
            if skip_transparent and str(ev.get("transparency", "opaque") or "opaque") == "transparent":
                continue
            summ = (ev.get("summary") or "").strip()
            low = summ.lower()
            if fp and summ.startswith(fp):
                continue
            if any(summ.startswith(p) or low.startswith(p.lower()) for p in ignore_prefixes):
                continue
            w = self._parse_api_event_window(ev, cal_tz)
            if not w:
                continue
            es, ee = w
            if slot_start < ee and slot_end > es:
                return True
        return False

    def _compute_hourly_free_slot_starts(
        self,
        time_min_dt: datetime,
        time_max_dt: datetime,
        events: List[Dict[str, Any]],
        duration_minutes: int,
        slot_step_minutes: int,
        calendar_tz_name: str,
        config: Dict[str, Any],
        free_hours_prefix: str,
    ) -> List[datetime]:
        """Hourly (or slot_step) grid: each candidate start must fit duration_minutes with no blocking overlap."""
        try:
            cal_tz = ZoneInfo(calendar_tz_name)
        except Exception:
            cal_tz = ZoneInfo("UTC")

        spec = config.get("appointment_hours_local") or {}
        emin: Optional[int] = None
        lmax: Optional[int] = None
        try:
            es = str(spec.get("earliest", "")).strip()
            if es:
                emin = self._parse_hhmm_local(es)
            le = str(spec.get("latest_end", "")).strip()
            if le:
                lmax = self._parse_hhmm_local(le)
        except ValueError:
            emin, lmax = None, None

        duration_td = timedelta(minutes=max(1, int(duration_minutes)))
        step = max(1, int(slot_step_minutes))
        step_td = timedelta(minutes=step)
        out: List[datetime] = []

        cur_d = time_min_dt.date()
        last_d = time_max_dt.date()
        while cur_d <= last_d:
            day_lo = datetime.combine(cur_d, time.min, tzinfo=cal_tz)
            day_hi_excl = day_lo + timedelta(days=1)

            win_lo = max(time_min_dt, day_lo)
            win_hi = min(time_max_dt, day_hi_excl)
            if win_lo >= win_hi:
                cur_d += timedelta(days=1)
                continue

            day_earliest = day_lo + timedelta(minutes=emin) if emin is not None else day_lo
            day_latest_end = day_lo + timedelta(minutes=lmax) if lmax is not None else day_hi_excl

            grid_lo = max(win_lo, day_earliest)
            last_end = min(win_hi, day_latest_end)

            if grid_lo >= last_end:
                cur_d += timedelta(days=1)
                continue

            slot_start = self._align_up_to_step_minutes(grid_lo, step)
            while slot_start < grid_lo:
                slot_start += step_td

            while True:
                slot_end = slot_start + duration_td
                if slot_end > last_end:
                    break
                if not self._hourly_grid_slot_blocked(
                    slot_start, slot_end, events, cal_tz, config, free_hours_prefix
                ):
                    out.append(slot_start)
                slot_start += step_td

            cur_d += timedelta(days=1)

        out.sort()
        return out

    async def _append_call_context_to_description(
        self,
        context: ToolExecutionContext,
        desc: str,
        call_id: str,
    ) -> str:
        """
        Append CallerID and recent user STT lines so calendar events stay useful when
        the LLM passes mojibake or placeholder Unicode in description fields.
        """
        base = (desc or "").strip()
        parts: List[str] = []
        try:
            if not context or not getattr(context, "session_store", None) or not getattr(context, "call_id", None):
                return base
            session = await context.get_session()
            num = getattr(session, "caller_number", None)
            if num:
                parts.append(f"CallerID (номер): {num}")
            cname = getattr(session, "caller_name", None)
            if cname and str(cname).strip():
                parts.append(f"Asterisk caller name: {cname}")
            hist = getattr(session, "conversation_history", None) or []
            user_lines: List[str] = []
            for msg in hist[-24:]:
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") != "user":
                    continue
                c = (msg.get("content") or "").strip()
                if c:
                    user_lines.append(c[:800])
            if user_lines:
                tail = user_lines[-6:]
                parts.append("Фразы абонента (STT, последние):\n" + "\n".join(f"- {x}" for x in tail))
        except Exception:
            logger.debug("append_call_context_to_description failed", call_id=call_id, exc_info=True)
        if not parts:
            return base
        block = "\n\n--- из звонка ---\n" + "\n".join(parts)
        return (base + block).strip() if base else block.strip()

    def _get_config(self, context: ToolExecutionContext) -> Dict[str, Any]:
        """
        Get google_calendar config: from context when available, else from ai-agent.yaml.
        """
        if context and getattr(context, "get_config_value", None):
            return context.get_config_value("tools.google_calendar", {}) or {}
        return self._load_config()

    @staticmethod
    def _flatten_google_calendar_arguments(p: Dict[str, Any]) -> Dict[str, Any]:
        """Merge nested provider payloads (some models wrap args under input/arguments/parameters)."""
        out = dict(p or {})
        for key in ("input", "arguments", "params", "parameters", "tool_input"):
            inner = out.pop(key, None)
            if isinstance(inner, dict):
                out = {**inner, **out}
        return out

    @staticmethod
    def _infer_google_calendar_action(p: Dict[str, Any]) -> Optional[str]:
        if p.get("summary") and p.get("start_datetime") and p.get("end_datetime"):
            return "create_event"
        if p.get("event_id") and not (p.get("time_min") and p.get("time_max")):
            return "get_event"
        if p.get("time_min") and p.get("time_max"):
            return "get_free_slots"
        return None

    def _coerce_google_calendar_parameters(self, parameters: Dict[str, Any], *, call_id: str) -> Dict[str, Any]:
        p = self._flatten_google_calendar_arguments(dict(parameters or {}))
        if not p.get("time_min"):
            for alt in ("timeMin", "start_time", "from", "range_start"):
                v = p.get(alt)
                if v:
                    p["time_min"] = v
                    break
        if not p.get("time_max"):
            for alt in ("timeMax", "end_time", "to", "range_end"):
                v = p.get(alt)
                if v:
                    p["time_max"] = v
                    break
        act = p.get("action")
        if isinstance(act, str) and act.strip():
            p["action"] = act.strip()
            return p
        for k in ("calendar_action", "operation", "tool", "method"):
            v = p.get(k)
            if isinstance(v, str) and v.strip():
                p["action"] = v.strip()
                logger.info(
                    "Mapped google_calendar action alias",
                    call_id=call_id,
                    alias_key=k,
                    action=p["action"],
                )
                return p
        inferred = self._infer_google_calendar_action(p)
        if inferred:
            p["action"] = inferred
            logger.info(
                "Inferred google_calendar action (model omitted action)",
                call_id=call_id,
                inferred=inferred,
                arg_keys=list(p.keys()),
            )
        return p

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ToolExecutionContext,
    ) -> Dict[str, Any]:
        """
        Routes the request to the underlying GCalendar module or executes custom logic based on the action.

        Args:
            parameters: Tool parameters from the AI; must include "action" and action-specific fields
                (e.g. event_id for get_event/delete_event, time_min/time_max for list_events).
            context: Tool execution context with call_id and config access.

        Returns:
            Dict with "status" ("success" | "error") and "message"; may include "events", "id",
            "link", or other action-specific keys. On error, message describes the failure.
        """
        call_id = getattr(context, "call_id", None) or ""
        logger.info("GCalendarTool execution triggered by LLM", call_id=call_id)
        parameters = self._coerce_google_calendar_parameters(parameters, call_id=call_id)
        safe_parameters = {
            "action": parameters.get("action"),
            "event_id": parameters.get("event_id"),
            "has_summary": bool(parameters.get("summary")),
            "has_description": bool(parameters.get("description")),
            "time_min": parameters.get("time_min"),
            "time_max": parameters.get("time_max"),
        }
        logger.debug("Raw arguments received from LLM", call_id=call_id, parameters=safe_parameters)

        config = self._get_config(context)
        if config.get("enabled") is False:
            logger.info("Google Calendar tool disabled by config", call_id=call_id)
            out = {"status": "error", "message": "Google Calendar is disabled."}
            return out

        action = parameters.get("action")
        if not action:
            error_msg = (
                "Error: 'action' parameter is missing and could not be inferred from other fields. "
                "Pass action (list_events | get_event | create_event | delete_event | get_free_slots) "
                f"and required fields. Received keys: {sorted(parameters.keys())}."
            )
            logger.warning("Missing action parameter", call_id=call_id, keys=list(parameters.keys()))
            out = {"status": "error", "message": error_msg}
            logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
            return out

        cal = self._get_cal(config)
        calendar_tz_name = self._get_calendar_tz_name(config)

        if not getattr(cal, "service", None):
            logger.error("Google Calendar service unavailable", call_id=call_id)
            return {"status": "error", "message": "Google Calendar is not configured or unavailable."}

        try:
            if action == "get_free_slots":
                time_min = parameters.get("time_min")
                time_max = parameters.get("time_max")
                if not time_min or not time_max:
                    error_msg = "Error: 'time_min' and 'time_max' are required for get_free_slots."
                    logger.warning("Missing time range for get_free_slots", call_id=call_id)
                    out = {"status": "error", "message": error_msg}
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out

                strategy_raw = parameters.get("slot_strategy") or config.get("get_free_slots_strategy") or "auto"
                strategy = str(strategy_raw).strip().lower()
                if strategy not in ("auto", "templates", "hourly"):
                    strategy = "auto"

                free_prefix = (parameters.get("free_prefix") or config.get("free_prefix") or "").strip()
                busy_prefix = (parameters.get("busy_prefix") or config.get("busy_prefix") or "").strip()
                if strategy == "templates":
                    if not free_prefix or not busy_prefix:
                        error_msg = (
                            "Error: slot_strategy templates requires 'free_prefix' and 'busy_prefix' "
                            "(tool arguments or tools.google_calendar in config)."
                        )
                        logger.warning("Missing prefixes for get_free_slots", call_id=call_id, strategy=strategy)
                        out = {"status": "error", "message": error_msg}
                        logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                        return out
                elif strategy == "auto" and (not free_prefix or not busy_prefix):
                    strategy = "hourly"
                    logger.info(
                        "get_free_slots: auto → hourly (no Open/FOG prefixes in call or config)",
                        call_id=call_id,
                    )

                # DST-aware: normalize to calendar TZ (strip TZ tail, use GOOGLE_CALENDAR_TZ/TZ)
                try:
                    time_min_dt = self._normalize_datetime_to_calendar_tz(time_min, calendar_tz_name)
                    time_max_dt = self._normalize_datetime_to_calendar_tz(time_max, calendar_tz_name)
                    time_min_rfc = time_min_dt.isoformat()
                    time_max_rfc = time_max_dt.isoformat()
                except ValueError as e:
                    out = {"status": "error", "message": str(e)}
                    logger.warning("Invalid datetime for get_free_slots", call_id=call_id, error=str(e))
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out

                logger.debug(
                    "Calculating free slots",
                    call_id=call_id,
                    strategy=strategy,
                    free_prefix=free_prefix or "(none)",
                    busy_prefix=busy_prefix or "(none)",
                )
                events = await asyncio.to_thread(cal.list_events, time_min_rfc, time_max_rfc)

                duration_minutes = parameters.get("duration") or config.get("min_slot_duration_minutes", 15)
                try:
                    duration_minutes = max(1, int(duration_minutes))
                except (TypeError, ValueError):
                    duration_minutes = 15

                slot_step_raw = parameters.get("slot_step_minutes") or config.get("get_free_slots_slot_step_minutes", 60)
                try:
                    slot_step_minutes = max(1, int(slot_step_raw))
                except (TypeError, ValueError):
                    slot_step_minutes = 60

                slot_starts: list[datetime] = []
                resolution = "none"

                if strategy in ("auto", "templates"):
                    free_blocks: List[Tuple[datetime, datetime]] = []
                    busy_blocks: List[Tuple[datetime, datetime]] = []

                    for e in events:
                        summary = (e.get("summary") or "").strip()
                        start_str = e.get("start", {}).get("dateTime")
                        end_str = e.get("end", {}).get("dateTime")

                        if not start_str or not end_str:
                            continue

                        start_dt = self._parse_iso(start_str)
                        end_dt = self._parse_iso(end_str)

                        if free_prefix and summary.startswith(free_prefix):
                            free_blocks.append((start_dt, end_dt))
                        elif busy_prefix and summary.startswith(busy_prefix):
                            busy_blocks.append((start_dt, end_dt))

                    free_blocks.sort(key=lambda x: x[0])
                    busy_blocks.sort(key=lambda x: x[0])

                    available_intervals: List[Tuple[datetime, datetime]] = []

                    for f_start, f_end in free_blocks:
                        current_start = f_start

                        for b_start, b_end in busy_blocks:
                            if b_end <= current_start or b_start >= f_end:
                                continue
                            if current_start < b_start:
                                available_intervals.append((current_start, b_start))
                            current_start = max(current_start, b_end)

                        if current_start < f_end:
                            available_intervals.append((current_start, f_end))

                    duration_td = timedelta(minutes=duration_minutes)

                    def round_up_to_next_slot(dt: datetime, step_minutes: int) -> datetime:
                        """Round dt up to next time that is a multiple of step_minutes from midnight (same tz)."""
                        total_minutes = dt.hour * 60 + dt.minute
                        if dt.second or dt.microsecond or total_minutes % step_minutes != 0:
                            q = (total_minutes + step_minutes - 1) // step_minutes
                            new_total = q * step_minutes
                            if new_total >= 24 * 60:
                                days_add = new_total // (24 * 60)
                                new_total = new_total % (24 * 60)
                                base = dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_add)
                                return base.replace(hour=new_total // 60, minute=new_total % 60)
                            return dt.replace(hour=new_total // 60, minute=new_total % 60, second=0, microsecond=0)
                        return dt

                    for s, end_t in available_intervals:
                        if end_t <= s:
                            continue
                        if s + duration_td <= end_t:
                            slot_starts.append(s)
                        start = round_up_to_next_slot(s, duration_minutes)
                        while start + duration_td <= end_t:
                            if start > s:
                                slot_starts.append(start)
                            start += timedelta(minutes=duration_minutes)

                    slot_starts.sort()
                    resolution = "templates"

                use_hourly = strategy == "hourly" or (strategy == "auto" and not slot_starts)
                if use_hourly:
                    slot_starts = self._compute_hourly_free_slot_starts(
                        time_min_dt,
                        time_max_dt,
                        events,
                        duration_minutes,
                        slot_step_minutes,
                        calendar_tz_name,
                        config,
                        free_prefix,
                    )
                    resolution = "hourly"

                results = [t.strftime("%Y-%m-%d %H:%M") for t in slot_starts]
                if not results:
                    msg = "No free slot starts in the requested range."
                else:
                    msg = "Free slot starts: " + ", ".join(results)
                out = {
                    "status": "success",
                    "message": msg,
                    "free_slot_starts": results,
                    "slot_resolution": resolution,
                    "slot_step_minutes": slot_step_minutes,
                    "duration_minutes": duration_minutes,
                }
                logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                return out

            if action == "list_events":
                time_min = parameters.get("time_min")
                time_max = parameters.get("time_max")
                if not time_min or not time_max:
                    error_msg = "Error: 'time_min' and 'time_max' parameters are required for list_events."
                    logger.warning("Missing time range for list_events", call_id=call_id)
                    out = {"status": "error", "message": error_msg}
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                # DST-aware: normalize to calendar TZ (strip TZ tail, use GOOGLE_CALENDAR_TZ/TZ)
                try:
                    time_min_dt = self._normalize_datetime_to_calendar_tz(time_min, calendar_tz_name)
                    time_max_dt = self._normalize_datetime_to_calendar_tz(time_max, calendar_tz_name)
                    time_min_rfc = time_min_dt.isoformat()
                    time_max_rfc = time_max_dt.isoformat()
                except ValueError as e:
                    out = {"status": "error", "message": str(e)}
                    logger.warning("Invalid datetime for list_events", call_id=call_id, error=str(e))
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                events = await asyncio.to_thread(cal.list_events, time_min_rfc, time_max_rfc)
                simplified_events = [
                    {
                        "id": e.get("id"),
                        "summary": e.get("summary", "No Title"),
                        "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                        "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                    }
                    for e in events
                ]
                out = {"status": "success", "message": "Events listed.", "events": simplified_events}
                logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                return out

            if action == "get_event":
                event_id = parameters.get("event_id")
                if not event_id:
                    error_msg = "Error: 'event_id' parameter is required for get_event."
                    logger.warning("Missing event_id for get_event", call_id=call_id)
                    out = {"status": "error", "message": error_msg}
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                event = await asyncio.to_thread(cal.get_event, event_id)
                if not event:
                    out = {"status": "error", "message": "Event not found."}
                    logger.warning("Event not found", call_id=call_id, event_id=event_id)
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                out = {
                    "status": "success",
                    "message": "Event retrieved.",
                    "id": event.get("id"),
                    "summary": event.get("summary"),
                    "description": event.get("description", ""),
                    "start": event.get("start", {}).get("dateTime") or event.get("start", {}).get("date"),
                    "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
                }
                logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                return out

            if action == "create_event":
                summary = parameters.get("summary")
                desc = parameters.get("description", "")
                start_dt = parameters.get("start_datetime")
                end_dt = parameters.get("end_datetime")
                if not summary or not start_dt or not end_dt:
                    error_msg = (
                        "Error: 'summary', 'start_datetime', and 'end_datetime' are required for create_event."
                    )
                    logger.warning("Missing required parameters for create_event", call_id=call_id)
                    out = {"status": "error", "message": error_msg}
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                # DST-aware: if input has TZ tail, convert to calendar TZ and send local time (no tail)
                try:
                    start_dt_local = self._normalize_datetime_to_calendar_tz(start_dt, calendar_tz_name)
                    end_dt_local = self._normalize_datetime_to_calendar_tz(end_dt, calendar_tz_name)
                    start_dt_str = start_dt_local.strftime("%Y-%m-%dT%H:%M:%S")
                    end_dt_str = end_dt_local.strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError as e:
                    out = {"status": "error", "message": str(e)}
                    logger.warning("Invalid datetime for create_event", call_id=call_id, error=str(e))
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                appt_err = self._validate_appointment_hours_local(
                    start_dt_local, end_dt_local, config
                )
                if appt_err:
                    out = {"status": "error", "message": appt_err}
                    logger.info(
                        "create_event rejected (appointment_hours_local)",
                        call_id=call_id,
                        start=str(start_dt_local),
                        end=str(end_dt_local),
                    )
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                if bool(config.get("create_event_check_conflicts", True)):
                    conflicts = await asyncio.to_thread(
                        self._collect_create_event_conflicts,
                        cal,
                        start_dt_local,
                        end_dt_local,
                        calendar_tz_name,
                        config,
                    )
                    if conflicts:
                        preview = "; ".join(conflicts[:4])
                        if len(conflicts) > 4:
                            preview += f" (+ещё {len(conflicts) - 4})"
                        msg = (
                            "Ошибка: на это время в календаре уже есть занятость: "
                            f"{preview}. Предложи абоненту другое время; при необходимости вызови list_events "
                            "или get_free_slots на этот день, затем снова create_event."
                        )
                        out = {
                            "status": "error",
                            "message": msg,
                            "conflicts": conflicts[:12],
                        }
                        logger.info(
                            "create_event rejected (slot conflict)",
                            call_id=call_id,
                            count=len(conflicts),
                        )
                        logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                        return out
                if "\ufffd" in str(summary or "") or "\ufffd" in str(desc or ""):
                    logger.warning(
                        "Calendar summary/description contain U+FFFD (encoding or model placeholder)",
                        call_id=call_id,
                    )
                desc = await self._append_call_context_to_description(context, str(desc or ""), call_id)
                event = await asyncio.to_thread(cal.create_event, summary, desc, start_dt_str, end_dt_str)
                if not event:
                    out = {"status": "error", "message": "Failed to create event."}
                    logger.error("Failed to create event", call_id=call_id)
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                out = {
                    "status": "success",
                    "message": "Event created.",
                    "id": event.get("id"),
                    "link": event.get("htmlLink"),
                }
                logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                return out

            if action == "delete_event":
                event_id = parameters.get("event_id")
                if not event_id:
                    error_msg = "Error: 'event_id' parameter is required for delete_event."
                    logger.warning("Missing event_id for delete_event", call_id=call_id)
                    out = {"status": "error", "message": error_msg}
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                success = await asyncio.to_thread(cal.delete_event, event_id)
                if not success:
                    out = {"status": "error", "message": "Failed to delete event (not found or calendar error)."}
                    logger.warning("Failed to delete event", call_id=call_id, event_id=event_id)
                    logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                    return out
                out = {"status": "success", "message": "Event deleted.", "id": event_id}
                logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
                return out

            error_msg = f"Error: Unknown action '{action}'."
            logger.warning("Unknown action", call_id=call_id, action=action)
            out = {"status": "error", "message": error_msg}
            logger.info("Tool response to AI", call_id=call_id, action=action, status=out.get("status"))
            return out

        except Exception as e:
            logger.error(
                "GCalendarTool failed",
                call_id=call_id,
                action=action,
                error=str(e),
                exc_info=True,
            )
            out = {"status": "error", "message": "An unexpected calendar error occurred."}
            logger.info("Tool response to AI", call_id=call_id, action=action or "?", status=out.get("status"))
            return out

