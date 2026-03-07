"""Callback implementations for pipeline progress reporting."""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WebhookCallback:
    """Posts pipeline progress as JSON to a webhook URL."""

    def __init__(self, url: str, timeout: float = 10.0, headers: Optional[dict] = None):
        self.url = url
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}

    def _post(self, payload: dict) -> None:
        """POST JSON payload to the webhook URL. Failures are logged, not raised."""
        try:
            import urllib.request

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.url, data=data, headers=self.headers, method="POST")
            urllib.request.urlopen(req, timeout=self.timeout)
        except Exception as e:
            logger.warning(f"Webhook POST failed: {e}")

    def on_step_start(self, step: str, index: int, total: int) -> None:
        self._post(
            {
                "event": "step_start",
                "step": step,
                "index": index,
                "total": total,
            }
        )

    def on_step_complete(self, step: str, index: int, total: int) -> None:
        self._post(
            {
                "event": "step_complete",
                "step": step,
                "index": index,
                "total": total,
            }
        )

    def on_progress(self, step: str, percent: float, message: str = "") -> None:
        self._post(
            {
                "event": "progress",
                "step": step,
                "percent": percent,
                "message": message,
            }
        )
