"""부동산 — 오버레이 렌더러 (슬라이드쇼 구조 탈피).

기존 pptx→Keynote 경로와 근본적으로 다른 화면 문법:
  · 페이지를 넘기는 "슬라이드"가 아니라, **현장(지도·로드뷰)이 배경이고
    정보는 그 위에 뜨는 플로팅 카드**다. 부동산 앱 화면을 보는 감각.
  · PIL로 직접 그려서 라운드·그림자·블러·그라데이션에 제약이 없다.
  · Keynote/AppleScript 의존이 사라져 맥이 아닌 서버에서도 렌더된다.

입력은 deck.js와 동일한 spec JSON — 두 엔진을 바꿔 끼울 수 있다.
출력: out_dir/{1..N}.png (produce의 --images 규약)
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
W, H = 1920, 1080
SAFE_BOTTOM = 200          # 자막이 굽히는 영역 — 카드가 침범하지 않는다
PAD = 84                   # 화면 여백

# 팔레트 — Seed carrot 계열
INK = (18, 20, 24)
CARD = (255, 255, 255)
CARD_DARK = (22, 25, 31)
BRAND = (255, 102, 0)
FG = (26, 28, 32)
FG_DIM = (110, 116, 126)
WHITE = (255, 255, 255)
WHITE_DIM = (214, 218, 224)

_BOLD = str(ROOT / "data/assets/fonts/Pretendard-Bold.otf")
_BLACK = str(ROOT / "data/assets/fonts/Pretendard-Black.otf")
_SYS = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    if weight == "black":
        return ImageFont.truetype(_BLACK, size)
    if weight == "bold":
        return ImageFont.truetype(_BOLD, size)
    return ImageFont.truetype(_SYS, size, index=0)   # regular


# ── 기본 파츠 ───────────────────────────────────────────────────────────────

def backdrop(img_path: str | None, dim: float = 0.45, blur: int = 0) -> Image.Image:
    """배경 = 현장 사진을 화면 가득. 카드 가독성을 위해 어둡게(+옵션 블러)."""
    base = Image.new("RGB", (W, H), INK)
    if img_path and pathlib.Path(img_path).exists():
        im = Image.open(img_path).convert("RGB")
        scale = max(W / im.width, H / im.height)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        im = im.crop(((im.width - W) // 2, (im.height - H) // 2,
                      (im.width - W) // 2 + W, (im.height - H) // 2 + H))
        if blur:
            im = im.filter(ImageFilter.GaussianBlur(blur))
        base = im
    if dim:
        veil = Image.new("RGBA", (W, H), (12, 14, 18, int(255 * dim)))
        base = Image.alpha_composite(base.convert("RGBA"), veil).convert("RGB")
    return base


def card(base: Image.Image, box: tuple[int, int, int, int], *, fill=CARD,
         radius: int = 28, shadow: int = 34, alpha: int = 255) -> Image.Image:
    """그림자 있는 라운드 카드 — 오버레이 구조의 기본 단위."""
    x0, y0, x1, y1 = box
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + 10, x1, y1 + 12), radius, fill=(0, 0, 0, 92))
        sh = sh.filter(ImageFilter.GaussianBlur(shadow))
        base = Image.alpha_composite(base.convert("RGBA"), sh).convert("RGB")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius, fill=(*fill, alpha))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def pill(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *,
         bg=BRAND, fg=WHITE, size: int = 30, padx: int = 22, pady: int = 12) -> int:
    f = font(size, "bold")
    tw = d.textlength(text, font=f)
    x, y = xy
    h = size + pady * 2
    d.rounded_rectangle((x, y, x + tw + padx * 2, y + h), h // 2, fill=bg)
    d.text((x + padx, y + pady - 2), text, font=f, fill=fg)
    return int(tw + padx * 2)


def wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_lines(d, xy, lines, f, fill, leading: float = 1.34) -> int:
    x, y = xy
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill)
        y += int(f.size * leading)
    return y


def fit_font(d, text: str, max_w: int, start: int, weight="black", floor: int = 40):
    """한 줄에 들어갈 때까지 폰트를 줄인다."""
    size = start
    while size > floor and d.textlength(text, font=font(size, weight)) > max_w:
        size -= 4
    return font(size, weight)


# ── 화면 렌더러 (spec 타입별) ───────────────────────────────────────────────

def _cover(p: dict) -> Image.Image:
    base = backdrop(p.get("image"), dim=0.42)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "예린이의 부동산 뽀개기")
    # 하단 정보 카드 (안전영역 위에 앉힘)
    top = H - SAFE_BOTTOM - 250
    base = card(base, (PAD, top, W - PAD, top + 230), fill=CARD_DARK, alpha=235)
    d = ImageDraw.Draw(base)
    f = fit_font(d, p["name"], W - PAD * 2 - 96, 92)
    d.text((PAD + 48, top + 44), p["name"], font=f, fill=WHITE)
    d.text((PAD + 50, top + 156), p["subtitle"], font=font(30, "regular"), fill=WHITE_DIM)
    return base


def _summary(p: dict) -> Image.Image:
    base = backdrop(p.get("bg_image"), dim=0.62, blur=14)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "오늘의 결론")
    d.text((PAD, PAD + 84), "먼저 숫자 세 개만", font=font(72, "black"), fill=WHITE)

    cards = p["cards"][:3]
    gap = 28
    cw = (W - PAD * 2 - gap * (len(cards) - 1)) // len(cards)
    top = 330
    for i, c in enumerate(cards):
        x = PAD + i * (cw + gap)
        base = card(base, (x, top, x + cw, top + 260), fill=CARD if i == 0 else CARD_DARK,
                    alpha=250 if i == 0 else 232)
        d = ImageDraw.Draw(base)
        big = str(c["big"]).replace("월 ", "")
        fg_num = BRAND if i == 0 else WHITE
        fnum = fit_font(d, big, cw - 76, 84)
        d.text((x + 38, top + 52), big, font=fnum, fill=fg_num)
        label = (c.get("small") or "").split("\n")[0]
        d.text((x + 40, top + 176), label, font=font(26, "regular"),
               fill=FG_DIM if i == 0 else WHITE_DIM)

    # 한 줄 평 — 브랜드 바 + 텍스트
    oy = top + 320
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((PAD, oy, PAD + 8, oy + 96), 4, fill=BRAND)
    txt = p["oneliner"].strip('"')
    draw_lines(d, (PAD + 34, oy + 4), wrap(d, txt, font(30, "regular"), W - PAD * 2 - 60)[:2],
               font(30, "regular"), WHITE_DIM)
    return base


def _map(p: dict) -> Image.Image:
    """지도가 배경 전체 — 정보는 좌측 플로팅 카드."""
    base = backdrop(p["image"], dim=0.18)
    d = ImageDraw.Draw(base)
    cw = 760
    top = 210
    rows = p["items"][:3]
    ch = 150 + len(rows) * 132
    base = card(base, (PAD, top, PAD + cw, top + ch), fill=CARD_DARK, alpha=238)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "위치 확인")
    ft = fit_font(d, p["title"], cw - 96, 56, "bold", floor=34)
    d.text((PAD + 44, top + 44), p["title"], font=ft, fill=WHITE)
    y = top + 44 + ft.size + 46
    for h, b in rows:
        d.text((PAD + 44, y), h, font=font(26, "bold"), fill=BRAND)
        body = wrap(d, b, font(28, "regular"), cw - 96)[:2]
        y = draw_lines(d, (PAD + 44, y + 38), body, font(28, "regular"), WHITE_DIM) + 22
    return base


def _photo(p: dict) -> Image.Image:
    base = backdrop(p["image"], dim=0.30)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), p["chip"].replace("  ", " "))
    top = H - SAFE_BOTTOM - 210
    base = card(base, (PAD, top, W - PAD, top + 190), fill=CARD_DARK, alpha=230)
    d = ImageDraw.Draw(base)
    fh = fit_font(d, p["head"], W - PAD * 2 - 96, 60, "bold", floor=36)
    d.text((PAD + 44, top + 38), p["head"], font=fh, fill=WHITE)
    body = p["body"].split("(")[0].strip()
    d.text((PAD + 46, top + 40 + fh.size + 18), body, font=font(28, "regular"), fill=WHITE_DIM)
    return base


def _overview(p: dict) -> Image.Image:
    base = backdrop(p.get("image"), dim=0.55, blur=10)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "단지 개요")
    rows = p["rows"][:6]
    top = 250
    ch = 90 + len(rows) * 92
    base = card(base, (PAD, top, W - PAD, min(top + ch, H - SAFE_BOTTOM - 30)),
                fill=CARD, alpha=250)
    d = ImageDraw.Draw(base)
    y = top + 44
    for i, (k, v) in enumerate(rows):
        if i:
            d.line((PAD + 44, y - 16, W - PAD - 44, y - 16), fill=(234, 236, 240), width=2)
        d.text((PAD + 48, y + 6), str(k), font=font(26, "bold"), fill=BRAND)
        d.text((PAD + 300, y), str(v), font=font(34, "bold"), fill=FG)
        y += 92
    return base


def _price(p: dict) -> Image.Image:
    base = backdrop(p.get("bg_image"), dim=0.62, blur=14)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "비용")
    d.text((PAD, PAD + 84), "그래서, 얼마냐면요", font=font(72, "black"), fill=WHITE)
    gap = 28
    cw = (W - PAD * 2 - gap) // 2
    top = 340
    for i, (label, val, accent) in enumerate(
            [("보증금", p["deposit"], True), ("월 임대료", p["rent"], False)]):
        x = PAD + i * (cw + gap)
        base = card(base, (x, top, x + cw, top + 300), fill=CARD if accent else CARD_DARK,
                    alpha=250 if accent else 232)
        d = ImageDraw.Draw(base)
        d.text((x + 44, top + 46), label, font=font(30, "bold"),
               fill=FG_DIM if accent else WHITE_DIM)
        v = str(val).replace(" ~", "").replace("~", "")
        fv = fit_font(d, v, cw - 88, 96)
        d.text((x + 42, top + 116), v, font=fv, fill=BRAND if accent else WHITE)
        d.text((x + 46, top + 232), "부터", font=font(28, "regular"),
               fill=FG_DIM if accent else WHITE_DIM)
    return base


def _rating(p: dict) -> Image.Image:
    base = backdrop(p.get("bg_image"), dim=0.66, blur=16)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "예린이의 평가")
    total = f'{p["total"]:.1f}'
    d.text((PAD, PAD + 84), "뽀개기 총점", font=font(60, "black"), fill=WHITE)
    tw = d.textlength("뽀개기 총점", font=font(60, "black"))
    d.text((PAD + tw + 28, PAD + 74), total, font=font(84, "black"), fill=BRAND)
    d.text((PAD + tw + 34 + d.textlength(total, font=font(84, "black")), PAD + 118),
           "/ 5.0", font=font(34, "bold"), fill=WHITE_DIM)

    rows = p["rows"][:5]
    top = 330
    ch = 60 + len(rows) * 82
    base = card(base, (PAD, top, W - PAD, top + ch), fill=CARD_DARK, alpha=236)
    d = ImageDraw.Draw(base)
    bx, bw = PAD + 460, W - PAD * 2 - 620
    y = top + 44
    for name, score, *_ in rows:
        d.text((PAD + 46, y + 2), str(name), font=font(32, "bold"), fill=WHITE)
        d.rounded_rectangle((bx, y + 14, bx + bw, y + 40), 13, fill=(46, 51, 60))
        filled = int(bw * (float(score) / 5))
        d.rounded_rectangle((bx, y + 14, bx + filled, y + 40), 13,
                            fill=BRAND if score >= 4.5 else (255, 147, 100))
        d.text((bx + bw + 28, y), f"{float(score):.1f}", font=font(36, "black"), fill=WHITE)
        y += 82
    return base


def _verdict(p: dict) -> Image.Image:
    base = backdrop(p.get("bg_image"), dim=0.66, blur=16)
    d = ImageDraw.Draw(base)
    pill(d, (PAD, PAD), "총평")
    gap = 28
    cw = (W - PAD * 2 - gap) // 2
    top = 230
    ch = H - SAFE_BOTTOM - top - 120
    for i, (label, items, warm) in enumerate(
            [("이건 좋았다", p["pros"], True), ("이건 따져보자", p["cons"], False)]):
        x = PAD + i * (cw + gap)
        base = card(base, (x, top, x + cw, top + ch),
                    fill=(255, 102, 0) if warm else CARD_DARK, alpha=248 if warm else 234)
        d = ImageDraw.Draw(base)
        d.text((x + 44, top + 40), label, font=font(40, "black"),
               fill=(42, 18, 0) if warm else BRAND)
        y = top + 118
        for t in items[:4]:
            d.ellipse((x + 46, y + 14, x + 60, y + 28), fill=(42, 18, 0) if warm else BRAND)
            body = wrap(d, t, font(27, "regular"), cw - 130)[:2]
            y = draw_lines(d, (x + 78, y), body, font(27, "regular"),
                           (60, 26, 0) if warm else WHITE_DIM) + 16
    d = ImageDraw.Draw(base)
    closing = p["closing"].strip('"')
    fc = fit_font(d, closing, W - PAD * 2, 40, "bold", floor=26)
    d.text(((W - d.textlength(closing, font=fc)) // 2, top + ch + 34), closing, font=fc, fill=WHITE)
    return base


RENDERERS = {
    "cover": _cover, "summary": _summary, "map": _map, "photo": _photo,
    "overview": _overview, "price": _price, "rating": _rating, "verdict": _verdict,
}


def render_spec(spec: dict, out_dir: pathlib.Path) -> list[pathlib.Path]:
    """spec.slides[] → out_dir/{n}.png. deck.js와 동일한 입력을 받는다."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 텍스트 전용 화면도 현장 사진을 흐린 배경으로 깔아 톤을 잇는다
    hero = next((s.get("image") for s in spec["slides"] if s.get("image")), None)
    paths: list[pathlib.Path] = []
    for i, slide in enumerate(spec["slides"], 1):
        slide = {**slide, "bg_image": slide.get("image") or hero}
        img = RENDERERS[slide["type"]](slide)
        p = out_dir / f"{i}.png"
        img.save(p, quality=95)
        paths.append(p)
    return paths
