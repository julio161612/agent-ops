from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["widget"])

_WIDGET_JS_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "widget.js"


@router.get("/widget.js")
async def get_widget_script() -> FileResponse:
    """Serves the standalone embeddable chat widget — see app/static/widget.js
    for the installation snippet and how it talks to /public/v1/messages.
    """
    return FileResponse(_WIDGET_JS_PATH, media_type="application/javascript")
