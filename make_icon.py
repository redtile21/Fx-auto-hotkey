"""Generates the app icon (assets/icon.png, assets/icon-1024.png) and the
menu-bar template icon (assets/tray.png): a purple->blue lightning bolt."""
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
grad = Image.new("RGBA", (S, S))
px = grad.load()
a, b = (124, 58, 237), (59, 130, 246)
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S - 2)
        px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
mask = Image.new("L", (S, S), 0)
# macOS icon grid: ~10% transparent margin around the rounded square
ImageDraw.Draw(mask).rounded_rectangle((100, 100, S - 100, S - 100), radius=185, fill=255)
img.paste(grad, (0, 0), mask)
bolt = [(580, 210), (320, 560), (480, 560), (430, 820), (700, 455), (530, 455), (630, 210)]
ImageDraw.Draw(img).polygon(bolt, fill=(255, 255, 255, 255))
img.save("assets/icon-1024.png")
img.resize((256, 256), Image.LANCZOS).save("assets/icon.png")

# menu bar: black shape on transparent, drawn at 4x then reduced to 44 px (22 pt @2x)
T = 176
tray = Image.new("RGBA", (T, T), (0, 0, 0, 0))
k = T / 1024
ImageDraw.Draw(tray).polygon([(int(x * k * 1.25 - 0.13 * T), int(y * k * 1.25 - 0.13 * T))
                              for x, y in bolt], fill=(0, 0, 0, 255))
tray.resize((44, 44), Image.LANCZOS).save("assets/tray.png")
