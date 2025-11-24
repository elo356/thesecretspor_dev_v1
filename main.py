# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import uuid4
import cloudinary
import cloudinary.uploader
import os
import json
import threading
from pathlib import Path

# ============ CONFIG CLOUDINARY ============
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUDNAME"),
    api_key=os.environ.get("CLOUDINARY_APIKEY"),
    api_secret=os.environ.get("CLOUDINARY_APISECRET"),
    secure=True
)

# Decide whether to use Cloudinary or fall back to local file storage
USE_CLOUDINARY = bool(
    os.environ.get("CLOUDINARY_CLOUDNAME") and
    os.environ.get("CLOUDINARY_APIKEY") and
    os.environ.get("CLOUDINARY_APISECRET")
)

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ============ SEGURIDAD (TOKEN API) ============
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "123456")  # cambia esto en Render

def verify_token(authorization: str = Header(...)):
    expected = f"Bearer {ADMIN_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ============ ARCHIVO JSON DE CONTENIDO ============
BASE_DIR = Path(__file__).resolve().parent
CONTENT_PATH = BASE_DIR / "content.json"
LOCK = threading.Lock()

DEFAULT_CONTENT = {
    "heroVideo": None,
    "slots": {
        "servicio_1": None,
        "servicio_2": None,
        "servicio_3": None,
        "servicio_4": None,
        "about_img": None,
        "team_group": None,
        "staff_1": None,
        "staff_2": None,
        "staff_3": None,
        "staff_4": None,
        "staff_5": None,
        "staff_6": None
    },
    "gallery": []  # cada item: {id, url, public_id, category}
}

def load_content():
    with LOCK:
        if not CONTENT_PATH.exists():
            save_content(DEFAULT_CONTENT)
            return DEFAULT_CONTENT
        try:
            with open(CONTENT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = DEFAULT_CONTENT
        # merge slots por si faltan claves
        for k, v in DEFAULT_CONTENT["slots"].items():
            if "slots" not in data:
                data["slots"] = {}
            data["slots"].setdefault(k, v)
        if "gallery" not in data:
            data["gallery"] = []
        if "heroVideo" not in data:
            data["heroVideo"] = None
        return data

def save_content(data: dict):
    with LOCK:
        with open(CONTENT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ============ MODELOS Pydantic ============
class GalleryItem(BaseModel):
    id: str
    url: str
    public_id: str
    category: str

class ContentResponse(BaseModel):
    heroVideo: Optional[str]
    slots: Dict[str, Optional[str]]
    gallery: List[GalleryItem]

# ============ APP FASTAPI ============
app = FastAPI(title="The Secret Spot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # en producción pon tu dominio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files when using local storage
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# Serve admin panel page
@app.get("/panel", response_class=HTMLResponse)
def serve_panel():
    panel_path = BASE_DIR / "panel.html"
    if not panel_path.exists():
        return HTMLResponse("<h1>Panel no encontrado</h1>", status_code=404)
    return HTMLResponse(panel_path.read_text(encoding="utf-8"))

# ============ ENDPOINTS ============

@app.get("/api/content", response_model=ContentResponse)
def get_content():
    """Devuelve TODO el contenido editable."""
    data = load_content()
    # convertir gallery a lista de GalleryItem
    gallery_items = [GalleryItem(**item) for item in data["gallery"]]
    return ContentResponse(
        heroVideo=data["heroVideo"],
        slots=data["slots"],
        gallery=gallery_items
    )

# ---- HERO VIDEO ----
@app.post("/api/hero-video")
async def upload_hero_video(
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    # If Cloudinary is configured, upload there. Otherwise save locally to /uploads
    if USE_CLOUDINARY:
        try:
            result = cloudinary.uploader.upload(
                file.file,
                folder="thesecretspot/hero/api",
                resource_type="video"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cloudinary error: {e}")
        url = result["secure_url"]
        public_id = result.get("public_id")
    else:
        # save locally
        contents = await file.read()
        fname = f"{uuid4().hex}_{file.filename}"
        out_path = UPLOADS_DIR / fname
        with open(out_path, "wb") as out:
            out.write(contents)
        url = f"/uploads/{fname}"
        public_id = str(fname)
    data = load_content()
    data["heroVideo"] = url
    save_content(data)

    return {"url": url, "public_id": public_id, "message": "Hero video actualizado"}

# ---- IMÁGENES DE SECCIONES (SLOTS) ----
VALID_SLOTS = set(DEFAULT_CONTENT["slots"].keys())
@app.post("/api/slot-image")
async def upload_slot_image(
    slot_key: str = Form(...),
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    if slot_key not in VALID_SLOTS:
        raise HTTPException(status_code=400, detail="slot_key inválido")

    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Upload to Cloudinary or save locally
    if USE_CLOUDINARY:
        try:
            result = cloudinary.uploader.upload(
                file.file,
                folder=f"thesecretspot/slots/{slot_key}/api",
                resource_type="image"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cloudinary error: {e}")
        url = result["secure_url"]
        public_id = result.get("public_id")
    else:
        contents = await file.read()
        fname = f"{uuid4().hex}_{file.filename}"
        out_path = UPLOADS_DIR / fname
        with open(out_path, "wb") as out:
            out.write(contents)
        url = f"/uploads/{fname}"
        public_id = str(fname)

    data = load_content()
    data["slots"][slot_key] = url
    save_content(data)

    return {
        "slot_key": slot_key,
        "url": url,
        "public_id": public_id,
        "message": "Imagen de sección actualizada"
    }


# ---- GALERÍA ----
@app.get("/api/gallery", response_model=List[GalleryItem])
def get_gallery():
    data = load_content()
    return [GalleryItem(**item) for item in data["gallery"]]

@app.post("/api/gallery")
async def upload_gallery_image(
    category: str = Form(...),
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    if category not in ["damas", "caballeros", "ninos", "manicura", "pedicura"]:
        raise HTTPException(status_code=400, detail="Categoría inválida")

    if USE_CLOUDINARY:
        try:
            result = cloudinary.uploader.upload(
                file.file,
                folder=f"thesecretspot/gallery/{category}",
                resource_type="image"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cloudinary error: {e}")
        url = result["secure_url"]
        public_id = result.get("public_id")
    else:
        contents = await file.read()
        fname = f"{uuid4().hex}_{file.filename}"
        out_path = UPLOADS_DIR / fname
        with open(out_path, "wb") as out:
            out.write(contents)
        url = f"/uploads/{fname}"
        public_id = str(fname)

    item = {
        "id": str(uuid4()),
        "url": url,
        "public_id": public_id,
        "category": category
    }

    data = load_content()
    data["gallery"].append(item)
    save_content(data)

    return {"item": item, "message": "Imagen añadida a galería"}

@app.delete("/api/gallery/{item_id}")
def delete_gallery_image(item_id: str, token: str = Depends(verify_token)):
    data = load_content()
    gallery = data["gallery"]
    idx = next((i for i, it in enumerate(gallery) if it["id"] == item_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")

    item = gallery[idx]

    # borrar en Cloudinary
    try:
        if USE_CLOUDINARY:
            cloudinary.uploader.destroy(item["public_id"])
        else:
            # eliminar archivo local
            local_path = UPLOADS_DIR / item.get("public_id", "")
            if local_path.exists():
                try:
                    local_path.unlink()
                except Exception:
                    pass
    except Exception:
        # no romper si falla
        pass

    # quitar de la lista y guardar
    del gallery[idx]
    data["gallery"] = gallery
    save_content(data)

    return {"message": "Imagen eliminada", "id": item_id}
