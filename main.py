# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header, Form
from fastapi.middleware.cors import CORSMiddleware
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

    try:
        result = cloudinary.uploader.upload(
            file.file,
            folder="thesecretspot/hero/api",
            resource_type="video"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary error: {e}")

    url = result["secure_url"]
    data = load_content()
    data["heroVideo"] = url
    save_content(data)

    return {"url": url, "message": "Hero video actualizado"}

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

    try:
        result = cloudinary.uploader.upload(
            file.file,
            folder=f"thesecretspot/slots/{slot_key}/api",
            resource_type="image"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary error: {e}")

    url = result["secure_url"]

    data = load_content()
    data["slots"][slot_key] = url
    save_content(data)

    return {
        "slot_key": slot_key,
        "url": url,
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

    try:
        result = cloudinary.uploader.upload(
            file.file,
            folder=f"thesecretspot/gallery/{category}",
            resource_type="image"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary error: {e}")

    item = {
        "id": str(uuid4()),
        "url": result["secure_url"],
        "public_id": result["public_id"],
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
        cloudinary.uploader.destroy(item["public_id"])
    except Exception:
        # no romper si falla
        pass

    # quitar de la lista y guardar
    del gallery[idx]
    data["gallery"] = gallery
    save_content(data)

    return {"message": "Imagen eliminada", "id": item_id}
