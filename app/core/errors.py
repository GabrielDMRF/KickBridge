from __future__ import annotations


class AppError(Exception):
    """Error de negocio con código estable y mensaje seguro para el cliente."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        retry_after: int | None = None,
        kick_status: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
        self.kick_status = kick_status

    def body(self) -> dict:
        error: dict = {"code": self.code, "message": self.message}
        if self.retry_after is not None:
            error["retry_after"] = self.retry_after
        if self.kick_status is not None:
            error["kick_status"] = self.kick_status
        return {"error": error}
