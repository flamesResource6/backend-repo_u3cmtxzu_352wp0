import os
import uuid
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists and mount it as static
UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db  # type: ignore

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:  # pragma: no cover - best-effort check
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# --------- Simple Template Catalog ---------
class Template(BaseModel):
    id: str
    name: str
    aspect_ratio: str
    description: str
    preset: dict


TEMPLATES: List[Template] = [
    Template(
        id="reel-916-bold",
        name="Reel 9:16 • Bold",
        aspect_ratio="9:16",
        description="Vertical format with bold headline and punchy cuts.",
        preset={"font": "Inter ExtraBold", "color": "#3b82f6", "lower_third": True},
    ),
    Template(
        id="corporate-169-clean",
        name="Corporate 16:9 • Clean",
        aspect_ratio="16:9",
        description="Clean lower-thirds, logo bug, subtle transitions.",
        preset={"font": "Inter Medium", "color": "#22d3ee", "lower_third": True},
    ),
    Template(
        id="event-11-pop",
        name="Event Montage 1:1 • Pop",
        aspect_ratio="1:1",
        description="Square montage with beat-matched cuts and stickers.",
        preset={"font": "Inter Black", "color": "#f59e0b", "stickers": True},
    ),
]


@app.get("/api/templates", response_model=List[Template])
def list_templates():
    return TEMPLATES


# --------- Upload Endpoint ---------
@app.post("/api/upload")
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    saved = []
    base = str(request.base_url).rstrip("/")

    for f in files:
        _, ext = os.path.splitext(f.filename or "")
        ext = ext.lower() if ext else ""
        safe_ext = ext if ext in [
            ".mp4", ".mov", ".mkv", ".webm",
            ".jpg", ".jpeg", ".png", ".gif",
            ".pdf", ".zip", ".wav", ".mp3", ".aac", ".m4a"
        ] else ext
        fname = f"{uuid.uuid4().hex}{safe_ext}"
        path = os.path.join(UPLOAD_DIR, fname)
        with open(path, "wb") as out:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        url = f"{base}/uploads/{fname}"
        saved.append({
            "original": f.filename,
            "stored_as": fname,
            "url": url,
            "mime": f.content_type,
        })

    return {"count": len(saved), "files": saved}


# --------- Instant Edit (Mock Processor) ---------
class InstantEditRequest(BaseModel):
    template_id: str
    assets: List[str]
    title: Optional[str] = None
    subtitle: Optional[str] = None
    brand_color: Optional[str] = None
    logo_url: Optional[str] = None


class InstantEditResponse(BaseModel):
    template: Template
    preview_type: str
    preview_url: str
    used_assets: List[str]
    notes: str


@app.post("/api/instant-edit", response_model=InstantEditResponse)
async def instant_edit(req: InstantEditRequest):
    # Validate template
    tpl = next((t for t in TEMPLATES if t.id == req.template_id), None)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    if not req.assets:
        raise HTTPException(status_code=400, detail="No assets provided")

    # Heuristic: if any video asset, return first video as preview; else first image
    video_exts = (".mp4", ".mov", ".mkv", ".webm")
    image_exts = (".jpg", ".jpeg", ".png", ".gif")

    preview_url = ""
    preview_type = "unknown"

    for url in req.assets:
        l = url.lower()
        if any(l.endswith(e) for e in video_exts):
            preview_url = url
            preview_type = "video"
            break
    if not preview_url:
        for url in req.assets:
            l = url.lower()
            if any(l.endswith(e) for e in image_exts):
                preview_url = url
                preview_type = "image"
                break

    if not preview_url:
        preview_type = "placeholder"
        preview_url = "https://placehold.co/1280x720?text=Instant+Preview"

    notes = (
        "Instant edit applied. This preview uses your first uploaded media. "
        "In a full pipeline, we would trim, add lower-thirds, color grade, "
        "and export in the template's aspect ratio."
    )

    return InstantEditResponse(
        template=tpl,
        preview_type=preview_type,
        preview_url=preview_url,
        used_assets=req.assets,
        notes=notes,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
