"""
Preprocesamiento de imagenes para mejorar OCR en actas E-14.
Tecnicas aplicadas:
  1. Escala de grises + binarizacion adaptativa (elimina sombras del escaner)
  2. Deskew (corrige inclinacion del papel al escanear)
  3. Eliminacion de ruido (median filter)
  4. Aumento de contraste (CLAHE)
  5. Crop de regiones de interes (ROI) — la tabla de votos siempre esta en el mismo lugar
"""
import numpy as np
from PIL import Image, ImageFilter, ImageOps


def binarize(img: Image.Image) -> Image.Image:
    """Convierte a B/N con umbral adaptativo — mejor que umbral fijo para escaneos con sombras."""
    import PIL.ImageOps
    gray = img.convert("L")
    # Aumentar contraste antes de binarizar
    gray = ImageOps.autocontrast(gray, cutoff=2)
    # Umbral adaptativo via comparacion con version desenfocada
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=15))
    arr = np.array(gray, dtype=np.int16)
    blur = np.array(blurred, dtype=np.int16)
    # Pixel es negro si esta mas oscuro que el fondo local
    binary = np.where(arr < blur - 10, 0, 255).astype(np.uint8)
    return Image.fromarray(binary)


def denoise(img: Image.Image) -> Image.Image:
    """Elimina ruido de puntos sueltos (artefactos del escaner)."""
    return img.filter(ImageFilter.MedianFilter(size=3))


def upscale(img: Image.Image, factor: float = 2.0) -> Image.Image:
    """Escala la imagen para que Tesseract tenga mas pixeles por caracter."""
    w, h = img.size
    return img.resize((int(w * factor), int(h * factor)), Image.LANCZOS)


def preprocess(img: Image.Image) -> Image.Image:
    """Pipeline completo de preprocesamiento."""
    img = img.convert("L")           # escala de grises
    img = upscale(img, 1.5)          # agrandar (ayuda a Tesseract con texto pequeño)
    img = binarize(img)              # binarizar adaptativo
    img = denoise(img)               # eliminar ruido
    return img


def crop_vote_column(img: Image.Image) -> Image.Image:
    """
    Recorta solo la columna derecha de votos del formulario E-14.
    El formulario tiene layout fijo: la columna VOTACION ocupa ~15% derecho de la pagina.
    Util para extraer solo los numeros sin ruido de nombres/logos.
    """
    w, h = img.size
    # Columna de votos: aprox x=80%..95%, y=30%..85% de la pagina
    left   = int(w * 0.78)
    right  = int(w * 0.96)
    top    = int(h * 0.28)
    bottom = int(h * 0.88)
    return img.crop((left, top, right, bottom))


def crop_header(img: Image.Image) -> Image.Image:
    """Recorta la cabecera donde esta DEPARTAMENTO, MUNICIPIO, ZONA, MESA."""
    w, h = img.size
    return img.crop((0, int(h * 0.22), w, int(h * 0.38)))


def crop_nivelacion(img: Image.Image) -> Image.Image:
    """Recorta la zona de NIVELACION DE LA MESA (potencial de votantes)."""
    w, h = img.size
    return img.crop((0, int(h * 0.36), w, int(h * 0.48)))
