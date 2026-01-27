"""
Clock utility for time operations.
Uses Europe/Helsinki timezone for user-facing operations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _HAS_ZONEINFO = True
except ImportError:
    # Fallback for systems without zoneinfo/tzdata
    try:
        from backports.zoneinfo import ZoneInfo
        _HAS_ZONEINFO = True
    except ImportError:
        _HAS_ZONEINFO = False


class SystemClock:
    """System clock for time operations"""
    
    _USER_TZ = None
    _UTC_TZ = None
    
    @classmethod
    def _get_user_tz(cls):
        """Get user timezone (Europe/Helsinki), with fallback"""
        if cls._USER_TZ is None:
            if _HAS_ZONEINFO:
                try:
                    cls._USER_TZ = ZoneInfo("Europe/Helsinki")
                except Exception:
                    # Fallback to UTC+2 (Helsinki is UTC+2 in winter, UTC+3 in summer)
                    # For simplicity, use UTC+2 as fallback
                    cls._USER_TZ = timezone(timedelta(hours=2))
            else:
                # No zoneinfo available, use UTC+2 as fallback
                cls._USER_TZ = timezone(timedelta(hours=2))
        return cls._USER_TZ
    
    @classmethod
    def _get_utc_tz(cls):
        """Get UTC timezone"""
        if cls._UTC_TZ is None:
            if _HAS_ZONEINFO:
                try:
                    cls._UTC_TZ = ZoneInfo("UTC")
                except Exception:
                    cls._UTC_TZ = timezone.utc
            else:
                cls._UTC_TZ = timezone.utc
        return cls._UTC_TZ
    
    @staticmethod
    def now_utc() -> datetime:
        """Get current time in UTC"""
        return datetime.now(SystemClock._get_utc_tz())
    
    @staticmethod
    def now_helsinki() -> datetime:
        """Get current time in Europe/Helsinki timezone (legacy, use now_user_tz with timezone)"""
        return datetime.now(SystemClock._get_user_tz())
    
    @staticmethod
    def now_user_tz(timezone: str = "Europe/Helsinki") -> datetime:
        """
        Get current time in user's timezone.
        
        Args:
            timezone: Timezone string (e.g., 'Europe/Helsinki', 'UTC', 'America/New_York')
        
        Returns:
            Current datetime in specified timezone
        """
        if _HAS_ZONEINFO:
            try:
                tz = ZoneInfo(timezone)
                return datetime.now(tz)
            except Exception:
                # Fallback to UTC if timezone invalid
                return datetime.now(SystemClock._get_utc_tz())
        else:
            # No zoneinfo available, use UTC as fallback
            return datetime.now(SystemClock._get_utc_tz())
    
    @staticmethod
    def now_helsinki_iso() -> str:
        """Get current time in Europe/Helsinki as ISO string (UTC) (legacy)"""
        # Convert Helsinki time to UTC for storage
        helsinki_now = SystemClock.now_helsinki()
        utc_now = helsinki_now.astimezone(SystemClock._get_utc_tz())
        return utc_now.isoformat()
    
    @staticmethod
    def now_user_tz_iso(timezone: str = "Europe/Helsinki") -> str:
        """
        Get current time in user's timezone as ISO string (UTC).
        
        Args:
            timezone: Timezone string (e.g., 'Europe/Helsinki', 'UTC', 'America/New_York')
        
        Returns:
            Current time in UTC as ISO string (for storage)
        """
        user_now = SystemClock.now_user_tz(timezone)
        utc_now = user_now.astimezone(SystemClock._get_utc_tz())
        return utc_now.isoformat()
    
    @staticmethod
    def add_hours_helsinki(hours: int) -> str:
        """Add hours to current Helsinki time, return as UTC ISO string (legacy)"""
        helsinki_now = SystemClock.now_helsinki()
        future = helsinki_now + timedelta(hours=hours)
        utc_future = future.astimezone(SystemClock._get_utc_tz())
        return utc_future.isoformat()
    
    @staticmethod
    def add_hours_user_tz(hours: int, timezone: str = "Europe/Helsinki") -> str:
        """
        Add hours to current user timezone time, return as UTC ISO string.
        
        Args:
            hours: Number of hours to add
            timezone: Timezone string (e.g., 'Europe/Helsinki', 'UTC', 'America/New_York')
        
        Returns:
            Future time in UTC as ISO string
        """
        user_now = SystemClock.now_user_tz(timezone)
        future = user_now + timedelta(hours=hours)
        utc_future = future.astimezone(SystemClock._get_utc_tz())
        return utc_future.isoformat()