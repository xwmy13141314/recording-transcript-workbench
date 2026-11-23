"""生成应用图标：方案 1「声波文稿」——蓝色圆角方形 + 白色声波 + 文字行。

输出：
    图标/图标_512.png   高清 PNG（预览/其他用途）
    图标/图标.ico       Windows 多尺寸图标（16/24/32/48/64/128/256）
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "图标"
OUT.mkdir(parents=True, exist_ok=True)

BLUE = (0, 113, 227, 255)
WHITE = (255, 255, 255, 255)


def rounded_icon(size: int) -> Image.Image:
    # 超采样绘制，缩小后边缘更平滑
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    m = int(S * 0.06)
    r = int(S * 0.22)
    d.rounded_rectangle([m, m, S - m, S - m], radius=r, fill=BLUE)

    cx = S / 2
    # 声波：7 根竖条，左右对称高低不同
    bars = [
        (-0.27, 0.10), (-0.18, 0.19), (-0.09, 0.29), (0.0, 0.36),
        (0.09, 0.24), (0.18, 0.15), (0.27, 0.07),
    ]
    wave_top = S * 0.29
    bar_w = max(2, int(S * 0.035))
    for off, half in bars:
        x = cx + S * off
        h = S * half
        y0 = wave_top + (S * 0.20 - h) / 2
        d.rounded_rectangle([x - bar_w / 2, y0, x + bar_w / 2, y0 + h], radius=bar_w / 2, fill=WHITE)

    # 文字行：三条，长度递减/错落
    line_h = max(2, int(S * 0.022))
    gap = S * 0.055
    y = S * 0.60
    widths = [0.46, 0.34, 0.40]
    for i, w in enumerate(widths):
        x0 = cx - S * 0.27
        alpha = int(255 * (0.95 - i * 0.13))
        d.rounded_rectangle([x0, y + i * gap, x0 + S * w, y + i * gap + line_h],
                            radius=line_h / 2, fill=(255, 255, 255, alpha))

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    png = rounded_icon(512)
    png.save(OUT / "图标_512.png")

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico = rounded_icon(256)
    ico.save(OUT / "图标.ico", sizes=[(s, s) for s in ico_sizes])
    print(OUT / "图标_512.png")
    print(OUT / "图标.ico")


if __name__ == "__main__":
    main()
