"""
Periodic jobs. There is no worker process on the free host, so an external
cron calls POST /tasks/run/ every few minutes (see docs/adr/0004). Every job
must be idempotent: running it twice in a row changes nothing the second time.
"""

import logging

from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

PERIODIC_TASKS = [
    "apps.requests.services.expire_overdue",
    "apps.requests.services.auto_confirm",
    "apps.requests.services.send_reminders",
    "apps.reviews.services.publish_due",
    "apps.reviews.services.send_review_reminders",
    "apps.core.demo.reset_daily",
]


def run_periodic_tasks():
    """Run every job; one failing job must not stop the others."""
    results = {}
    for path in PERIODIC_TASKS:
        name = path.rsplit(".", 1)[-1]
        try:
            results[name] = import_string(path)()
        except Exception:
            logger.exception("Periodic task %s failed", path)
            results[name] = "error"
    return results
