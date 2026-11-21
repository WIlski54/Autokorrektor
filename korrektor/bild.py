"""Fotos laden: aufrecht drehen (EXIF), verkleinern, Ausschnitte bilden."""
import io

from PIL import Image, ImageOps


def offen(pfad):
    """Öffnet ein Foto so gedreht, wie ein Browser es anzeigt."""
    return ImageOps.exif_transpose(Image.open(pfad)).convert("RGB")


def als_jpeg(img, qualitaet=90):
    puffer = io.BytesIO()
    img.save(puffer, format="JPEG", quality=qualitaet)
    return puffer.getvalue()


def laden(pfad, max_kante):
    """Gibt (JPEG-Bytes, Originalgröße, Faktor gesendet/original) zurück."""
    img = offen(pfad)
    groesse = img.size
    faktor = min(1.0, max_kante / max(groesse))
    if faktor < 1.0:
        img = img.resize((round(groesse[0] * faktor), round(groesse[1] * faktor)), Image.LANCZOS)
    return als_jpeg(img), groesse, faktor


def ausschnitt(pfad, rahmen, rand=0.25):
    """Schneidet einen Rahmen [x, y, b, h] mit Rand (Anteil der Höhe) aus."""
    img = offen(pfad)
    x, y, b, h = rahmen
    r = h * rand
    kasten = (max(0, round(x - r)), max(0, round(y - r)),
              min(img.width, round(x + b + r)), min(img.height, round(y + h + r)))
    return als_jpeg(img.crop(kasten))
