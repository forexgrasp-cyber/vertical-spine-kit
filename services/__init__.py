"""Shared service wrappers for vertical-spine-kit.

Re-exports the shared canonical booking / staff / calendar facades
alongside any vertical-specific domain services.
"""

from .booking_service import BookingService
from .staff_service import StaffService
from .calendar_service import CalendarService
from .meeting_service import MeetingService

__all__ = [
    "BookingService",
    "StaffService",
    "CalendarService",
    "MeetingService",
]
