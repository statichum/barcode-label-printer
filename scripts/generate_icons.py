from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parents[1] / "app" / "static"
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


def bold_font(size: int) -> ImageFont.FreeTypeFont:
    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            return ImageFont.truetype(font_path, size)
    raise RuntimeError("No supported bold font was found for icon generation")


def make_icon(size: int, filename: str) -> None:
    scale = 4
    canvas = size * scale
    image = Image.new("RGB", (canvas, canvas), "#17483e")
    draw = ImageDraw.Draw(image)

    # Keep the important artwork within Android's maskable safe area.
    inset = int(canvas * 0.105)
    draw.rounded_rectangle(
        (inset, inset, canvas - inset, canvas - inset),
        radius=int(canvas * 0.16),
        fill="#fffef9",
    )

    font = bold_font(int(canvas * 0.245))
    label = "PRV"
    box = draw.textbbox((0, 0), label, font=font)
    text_width = box[2] - box[0]
    draw.text(
        ((canvas - text_width) / 2, canvas * 0.17),
        label,
        font=font,
        fill="#17342d",
    )

    baseline = int(canvas * 0.76)
    widths = [0.022, 0.012, 0.032, 0.016, 0.012, 0.027, 0.014, 0.034, 0.016]
    heights = [0.16, 0.12, 0.22, 0.15, 0.20, 0.13, 0.18, 0.23, 0.14]
    gap = int(canvas * 0.018)
    total = sum(int(canvas * width) for width in widths) + gap * (len(widths) - 1)
    x = (canvas - total) // 2
    for width, height in zip(widths, heights, strict=True):
        bar_width = int(canvas * width)
        bar_top = baseline - int(canvas * height)
        draw.rounded_rectangle(
            (x, bar_top, x + bar_width, baseline),
            radius=max(2, bar_width // 5),
            fill="#337866",
        )
        x += bar_width + gap

    image.resize((size, size), Image.Resampling.LANCZOS).save(
        OUTPUT / filename,
        optimize=True,
    )


make_icon(192, "icon-192.png")
make_icon(512, "icon-512.png")
make_icon(512, "icon-maskable-512.png")
make_icon(180, "apple-touch-icon.png")
