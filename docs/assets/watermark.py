"""Watermark utility used when (re)generating dashboard screenshots.

Not part of the installable package. Usage:

    from watermark import add_watermark
    im = add_watermark(Image.open("dashboard_home.png"), Image.open("zo-systems-logo.png"))
"""
from PIL import Image


def add_watermark(im: Image.Image, logo: Image.Image, margin: int = 18, width: int = 120) -> Image.Image:
    im = im.convert("RGBA")
    ratio = width / logo.width
    logo_resized = logo.resize((width, int(logo.height * ratio)), Image.LANCZOS)

    alpha = logo_resized.split()[3].point(lambda p: int(p * 0.55))
    logo_resized.putalpha(alpha)

    pos = (im.width - logo_resized.width - margin, im.height - logo_resized.height - margin)
    im.alpha_composite(logo_resized, pos)
    return im.convert("RGB")
