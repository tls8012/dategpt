from __future__ import annotations


class ProtocolError(RuntimeError):
    """Stable frontend-facing protocol error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool = True,
    ) -> None:
        self.code = code
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)

    def event(self, request_id=None) -> dict:
        event = {
            "type": "error",
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }
        if request_id is not None:
            event["request_id"] = request_id
        return event
