from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cloudinary
import cloudinary.uploader
import json
from pathlib import Path
import re

# ============ CONFIG CLOUDINARY ============
cloudinary.config(
    cloud_name="dnd427uub",
    api_key="456318294928817",
    api_secret="NH5awUrt2NriqWmgPZKk4To1gZY",
    secure=True
)

# ============ INICIALIZAR FASTAPI ============
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ============ ARCHIVO JSON DE CONTENIDO ============
BASE_DIR = Path(__file__).resolve().parent
CONTENT_PATH = BASE_DIR / "content.json"

DEFAULT_CONTENT = {
    "header_video": "",
    "servicios": [],
    "sobre_nosotros": "",
    "foto_grupal": "",
    "equipo": [],
    "galeria": []
}

def load_content():
    if CONTENT_PATH.exists():
        with open(CONTENT_PATH, "r") as f:
            data = json.load(f)
    else:
        data = {}

    # Asegurar todas las claves
    for k, v in DEFAULT_CONTENT.items():
        data.setdefault(k, v)

    return data

def save_content(data):
    with open(CONTENT_PATH, "w") as f:
        json.dump(data, f, indent=4)

# Extraer public_id de la URL de Cloudinary para borrar la imagen
def extract_public_id(url: str):
    # Ejemplo de URL: https://res.cloudinary.com/xxx/image/upload/v123456789/abc123.jpg
    match = re.search(r"/upload/(?:v\d+/)?([^\.]+)", url)
    return match.group(1) if match else None

# ============ ENDPOINT: OBTENER CONTENIDO ============
@app.get("/content")
def get_content():
    return load_content()

# ============ ENDPOINT: ACTUALIZAR VIDEO HEADER ============
@app.post("/update-header-video")
async def update_header_video(video_url: str = Form(...)):
    data = load_content()
    data["header_video"] = video_url
    save_content(data)
    return {"message": "ok", "url": video_url}

@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(400, "No se subió un archivo")

    # Subir como VIDEO a Cloudinary
    upload = cloudinary.uploader.upload(
        file.file,
        resource_type="video"  # 👈 ESTO ES LA CLAVE
    )

    url = upload.get("secure_url")

    # Guardar en el JSON
    data = load_content()
    data["header_video"] = url
    save_content(data)

    return {"message": "ok", "url": url}


# ============ ENDPOINT: SUBIR IMAGEN (GENERAL + GALERÍA) ============
@app.post("/upload-image")
async def upload_image(
    section: str = Form(...),
    categoria: str = Form(None),
    file: UploadFile = File(...)
):
    if not file:
        raise HTTPException(400, "No file uploaded")

    # Subir a Cloudinary (imagen)
    upload = cloudinary.uploader.upload(file.file)
    url = upload.get("secure_url")

    data = load_content()

    if section not in data:
        raise HTTPException(400, "Sección no válida")

    # Galería con categoría
    if section == "galeria":
        if not categoria:
            raise HTTPException(400, "La galería requiere una categoría")
        data[section].append({"url": url, "categoria": categoria})
    else:
        # Secciones que son listas
        if isinstance(data[section], list):
            data[section].append(url)
        else:
            # Secciones de imagen única (sobre_nosotros, foto_grupal, etc.)
            data[section] = url

    save_content(data)

    return {"message": "ok", "url": url}

# ============ ENDPOINT: ELIMINAR IMAGEN ============
@app.delete("/delete-image")
def delete_image(section: str, url: str):
    data = load_content()

    if section not in data:
        raise HTTPException(400, "La sección no existe")

    # Borrar de Cloudinary (opcional pero recomendable)
    public_id = extract_public_id(url)
    if public_id:
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            # No romper si falla el borrado en Cloudinary
            pass

    # Si es lista (servicios, equipo, galeria)
    if isinstance(data[section], list):
        if section == "galeria":
            data[section] = [img for img in data[section] if img.get("url") != url]
        else:
            data[section] = [img for img in data[section] if img != url]
    else:
        # Si es string (header_video NO, pero sobre_nosotros, foto_grupal)
        if data[section] == url:
            data[section] = ""

    save_content(data)

    return {"message": "Imagen eliminada correctamente"}
from cloudinary.api import usage

@app.get("/cloudinary-usage")
def cloudinary_usage():
    try:
        u = usage()
        return {
            "storage": {
                "image": u["storage"]["image"]["usage"],
                "video": u["storage"]["video"]["usage"],
                "raw": u["storage"]["raw"]["usage"],
                "total": u["storage"]["total"]["usage"],
                "limit": u["storage"]["total"]["limit"]
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Error al obtener uso: {str(e)}")
