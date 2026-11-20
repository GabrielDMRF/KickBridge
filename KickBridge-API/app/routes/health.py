from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    factory = request.app.state.session_factory
    db = factory()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    finally:
        db.close()
    return JSONResponse(content={"status": "ok"})
