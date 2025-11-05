 
# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import os
import textwrap
import uuid

def text_to_image(text: str, lang: str = "tr", width: int = 384) -> str:
    """
    Girilen metni (UTF-8) beyaz zeminli siyah yazılı görsele çevirir.
    384 px genişlik çoğu 80mm termal yazıcı için uygundur.
    """
    os.makedirs("data/tmp", exist_ok=True)

    # Yazı tipi ayarı (Windows'ta Arial veya Consolas, Linux'ta DejaVuSans)
    try:
        font_path = "C:/Windows/Fonts/arial.ttf"  # Windows
        font = ImageFont.truetype(font_path, 18)
    except Exception:
        font = ImageFont.load_default()

    # Metni kır (çok uzun satırlar taşmasın)
    lines = textwrap.wrap(text, width=32)
    line_height = font.getbbox("A")[3] + 6
    img_height = max(100, line_height * (len(lines) + 2))

    # Görseli oluştur
    img = Image.new("RGB", (width, img_height), "white")
    draw = ImageDraw.Draw(img)
    y = 10
    for line in lines:
        draw.text((10, y), line, font=font, fill="black")
        y += line_height

    filename = f"text_render_{uuid.uuid4().hex}.png"
    path = os.path.join("data", "tmp", filename)
    img.save(path)
    return path
