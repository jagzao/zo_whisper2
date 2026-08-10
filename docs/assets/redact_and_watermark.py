"""Script de un solo uso: redacta datos sensibles en las screenshots del
dashboard y les agrega el logo como marca de agua. No es parte del paquete.
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SHOTS = HERE.parent / "screenshots"
LOGO_PATH = HERE / "zo-systems-logo.png"

# Columna "Nombre" de la tabla de fondo — aparece (atenuada pero legible)
# detras de TODOS los modales. Cada modal tapa un ancho/alto distinto, asi
# que la parte de la columna que "se escapa" es distinta por imagen: una
# tira angosta a la izquierda del modal + lo que queda visible debajo.
def _bg_leak(modal_left: int, modal_bottom: int | None) -> list[tuple[int, int, int, int]]:
    boxes = [(16, 430, modal_left, 900)]  # tira a la izquierda del modal
    if modal_bottom is not None:
        boxes.append((modal_left, modal_bottom, 515, 900))  # lo que sigue debajo del modal
    return boxes


# Cajas generosas — mejor tapar de mas que dejar texto sensible visible.
REDACTIONS: dict[str, list[tuple[int, int, int, int]]] = {
    "dashboard_home.png": [
        (16, 430, 515, 900),
    ],
    "dashboard_edit.png": [
        *_bg_leak(modal_left=115, modal_bottom=650),
        (120, 320, 1280, 575),  # textarea con transcripcion real
    ],
    "dashboard_insights.png": [
        *_bg_leak(modal_left=100, modal_bottom=None),  # modal llega hasta abajo
        (105, 50, 410, 90),      # titulo del modal (filename)
        (175, 195, 555, 415),    # tile con foto de cara + nombre
        (560, 195, 990, 415),    # tile EG + nombre
        (175, 415, 990, 630),    # tiles AG/LB + nombres inferiores
    ],
    "dashboard_preview.png": [
        *_bg_leak(modal_left=100, modal_bottom=None),
        (105, 50, 410, 90),
        (175, 195, 555, 415),
        (560, 195, 990, 415),
        (175, 415, 990, 630),
        (120, 740, 975, 900),   # transcripcion real visible en este tab
    ],
    "dashboard_logs.png": [
        *_bg_leak(modal_left=245, modal_bottom=650),
        (270, 320, 1140, 620),  # panel completo de logs (paths + nombres de proyecto)
    ],
    "dashboard_projects.png": [
        *_bg_leak(modal_left=105, modal_bottom=715),
        (120, 320, 400, 350),   # fila Valeris
        (120, 450, 400, 480),   # fila JM
        (120, 580, 400, 610),   # fila Databiz
    ],
    "dashboard_help.png": [
        *_bg_leak(modal_left=350, modal_bottom=815),
        (365, 604, 750, 682),   # lineas valeris_/jm_/databiz_ -> nombres reales
    ],
}


def redact(im: Image.Image, boxes: list[tuple[int, int, int, int]]) -> Image.Image:
    draw = ImageDraw.Draw(im)
    for box in boxes:
        draw.rectangle(box, fill=(10, 14, 22))
    return im


def add_watermark(im: Image.Image, logo: Image.Image, margin: int = 18, width: int = 120) -> Image.Image:
    im = im.convert("RGBA")
    ratio = width / logo.width
    logo_resized = logo.resize((width, int(logo.height * ratio)), Image.LANCZOS)

    alpha = logo_resized.split()[3].point(lambda p: int(p * 0.55))
    logo_resized.putalpha(alpha)

    pos = (im.width - logo_resized.width - margin, im.height - logo_resized.height - margin)
    im.alpha_composite(logo_resized, pos)
    return im.convert("RGB")


def main() -> None:
    logo = Image.open(LOGO_PATH).convert("RGBA")

    for filename, boxes in REDACTIONS.items():
        path = SHOTS / filename
        im = Image.open(path).convert("RGB")
        im = redact(im, boxes)
        im = add_watermark(im, logo)
        im.save(path)
        print(f"[OK] {filename}: {len(boxes)} caja(s) redactada(s) + watermark")


if __name__ == "__main__":
    main()
