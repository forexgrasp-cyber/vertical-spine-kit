"""Celery app for the voice agent compliance pipeline.

Beat schedule:
  - purge_expired_recordings: daily at 02:00 UTC (TCPA/GDPR 30-day retention)

Start worker:
  celery -A celery_app worker --loglevel=info
Start beat:
  celery -A celery_app beat --loglevel=info
Start both (dev):
  celery -A celery_app worker --beat --loglevel=info
"""

from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "voice_agent",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["shared.gdpr.retention"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "purge-expired-recordings": {
            "task": "shared.gdpr.retention.purge_expired_recordings",
            "schedule": 86400.0,  # every 24 hours
            "options": {"queue": "compliance"},
        },
    },
    beat_schedule_filename="celerybeat-schedule",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

__all__ = ["celery_app"]
