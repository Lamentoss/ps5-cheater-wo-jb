"""Draw the app icon and write packaging/icon.icns (macOS only)."""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SCALE = 4


def draw(size: int) -> Image.Image:
    s = size * SCALE
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((s * .08, s * .08, s * .92, s * .92), radius=s * .2, fill=(11, 15, 25, 255))
    d.rounded_rectangle((s * .2, s * .34, s * .8, s * .68), radius=s * .15, fill=(34, 197, 94, 255))
    dark = (5, 46, 20, 255)
    bar = s * .022
    d.rectangle((s * .29, s * .51 - bar, s * .43, s * .51 + bar), fill=dark)
    d.rectangle((s * .36 - bar, s * .44, s * .36 + bar, s * .58), fill=dark)
    for x, y in ((.6, .47), (.69, .55)):
        r = s * .036
        d.ellipse((s * x - r, s * y - r, s * x + r, s * y + r), fill=dark)
    return image.resize((size, size), Image.LANCZOS)


iconset = HERE / "icon.iconset"
iconset.mkdir(exist_ok=True)
for base in (16, 32, 128, 256, 512):
    draw(base).save(iconset / f"icon_{base}x{base}.png")
    draw(base * 2).save(iconset / f"icon_{base}x{base}@2x.png")
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
shutil.rmtree(iconset)
