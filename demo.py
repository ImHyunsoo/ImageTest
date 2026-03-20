"""
demo.py — 고객 제안용 데모

Tesla / Hyundai / Kia 차세대 클러스터별로
게이지·팝업·텔테일 비교를 시연하고 HTML 리포트를 생성합니다.

실행:
  python demo.py                   # ACTIVE_BRAND 에 설정된 브랜드 테스트
  python demo.py --brand hyundai   # 현대 클러스터만 테스트
  python demo.py --brand all       # 전체 브랜드 테스트
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from image_compare import ImageComparator, ROI, CompareResult

# ─────────────────────────────────────────────────────────────────────────────
# ★ 브랜드 설정 — 여기서 테스트할 브랜드를 선택하세요
#   'tesla'   : 테슬라 클러스터만 테스트
#   'hyundai' : 현대 (IONIQ 스타일) 클러스터만 테스트
#   'kia'     : 기아 (EV6 스타일) 클러스터만 테스트
#   'all'     : 전체 브랜드 테스트 (기본값)
# ─────────────────────────────────────────────────────────────────────────────
ACTIVE_BRAND = 'all'

OUT = Path('demo_output')
OUT.mkdir(exist_ok=True)

FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG  = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_KO_BOLD = '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'
FONT_KO_REG  = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'

W, H = 480, 270  # 클러스터 이미지 크기 (16:9)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


# ─────────────────────────────────────────────────────────────────────────────
# 텔테일 / 팝업 정의 (공통)
# ─────────────────────────────────────────────────────────────────────────────

TELLTALE_DEFS = [
    ('engine',   'ENG',  (255, 165,   0)),
    ('fuel',     'FUEL', (255, 165,   0)),
    ('oil',      'OIL',  (255,  50,  50)),
    ('battery',  'BAT',  (255,  50,  50)),
    ('abs',      'ABS',  (255, 165,   0)),
    ('door',     'DOOR', (255, 165,   0)),
    ('seatbelt', 'SBT',  (255,  50,  50)),
    ('temp',     'TEMP', (255,  50,  50)),
]

POPUP_COLORS = {
    'warning': (255, 165,   0),
    'error':   (255,  50,  50),
    'info':    ( 50, 165, 255),
}

ALL_OFF = {k: False for k, *_ in TELLTALE_DEFS}

GEAR_LABELS = {'D': 'DRIVE', 'R': 'REVERSE', 'N': 'NEUTRAL', 'P': 'PARK'}

# ─────────────────────────────────────────────────────────────────────────────
# 브랜드별 표준 ROI 세트 (480×270 기준)
#
# 텔테일·속도·배터리·팝업 4개 영역을 모든 테스트에 자동 적용합니다.
# 실제 클러스터 해상도에 맞게 좌표만 조정하면 됩니다.
# ─────────────────────────────────────────────────────────────────────────────

BRAND_ROIS = {
    'tesla': [
        ROI(name='텔테일 표시줄',   x=0,   y=0,   width=480, height=48,  strict=True, color_check=True),
        ROI(name='속도 표시',       x=158, y=52,  width=164, height=120, strict=True),
        ROI(name='배터리/주행거리', x=322, y=52,  width=155, height=140, strict=False),
        ROI(name='팝업 영역',       x=0,   y=210, width=480, height=60,  strict=True),
    ],
    'hyundai': [
        ROI(name='텔테일 표시줄',   x=0,   y=0,   width=480, height=48,  strict=True, color_check=True),
        ROI(name='속도 표시',       x=155, y=52,  width=168, height=118, strict=True),
        ROI(name='배터리/주행거리', x=318, y=52,  width=160, height=140, strict=False),
        ROI(name='팝업 영역',       x=0,   y=210, width=480, height=60,  strict=True),
    ],
    'kia': [
        ROI(name='텔테일 표시줄',   x=0,   y=0,   width=480, height=48,  strict=True, color_check=True),
        ROI(name='속도 표시',       x=30,  y=58,  width=178, height=110, strict=True),
        ROI(name='배터리/주행거리', x=240, y=52,  width=238, height=140, strict=False),
        ROI(name='팝업 영역',       x=0,   y=210, width=480, height=60,  strict=True),
    ],
}

# OCR 전용 속도 ROI — 숫자 인식에 최적화된 좌표 (텍스트 전용 영역)
BRAND_OCR_SPEED_ROI = {
    'tesla':   dict(x=145, y=70, width=195, height=95),
    'hyundai': dict(x=145, y=70, width=195, height=95),
    'kia':     dict(x=25,  y=68, width=200, height=87),
}

# 팝업 제목+본문 OCR 좌표 — _draw_popup 기준 (모든 브랜드 공통)
# 제목: (px0+46, py0+11) = (56, 224),  본문: (56, 243)
POPUP_TEXT_OCR_COORD = dict(x=40, y=205, width=390, height=60)

# ─────────────────────────────────────────────────────────────────────────────
# 브랜드별 스타일 설정
# ─────────────────────────────────────────────────────────────────────────────

BRAND_STYLE = {
    'tesla': {
        'bg':           (  8,   8,   8),
        'accent':       (  0, 190, 110),
        'sep_line':     ( 38,  38,  52),
        'inactive_bg':  ( 18,  18,  26),
        'inactive_fg':  ( 48,  48,  60),
        'label':        'Tesla  Model S/3/X/Y',
    },
    'hyundai': {
        'bg':           ( 10,  20,  37),
        'accent':       (  0, 170, 210),   # Hyundai teal
        'sep_line':     (  0,  60,  90),
        'inactive_bg':  ( 10,  26,  48),
        'inactive_fg':  ( 30,  70, 100),
        'label':        'Hyundai  IONIQ 5 / IONIQ 6',
    },
    'kia': {
        'bg':           ( 13,  12,  14),
        'accent':       (204,  14,  42),   # Kia red
        'sep_line':     ( 60,  14,  22),
        'inactive_bg':  ( 20,  14,  16),
        'inactive_fg':  ( 60,  32,  36),
        'label':        'Kia  EV6 / EV9',
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 공통 드로잉 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _draw_telltale_icon(draw: ImageDraw.Draw, key: str, cx: int, cy: int, ink):
    if key == 'engine':
        draw.rectangle([cx - 7, cy - 3, cx + 7, cy + 5], fill=ink)
        draw.rectangle([cx - 5, cy - 6, cx - 1, cy - 3], fill=ink)
        draw.rectangle([cx + 1, cy - 6, cx + 5, cy - 3], fill=ink)
        draw.rectangle([cx - 10, cy,     cx - 7, cy + 3], fill=ink)
    elif key == 'fuel':
        draw.rectangle([cx - 6, cy - 5, cx + 3, cy + 5], fill=ink)
        draw.rectangle([cx + 3, cy - 5, cx + 7, cy - 1], fill=ink)
        draw.line([(cx + 7, cy - 5), (cx + 7, cy + 2)], fill=ink, width=2)
        draw.ellipse([cx + 4, cy + 1, cx + 9, cy + 5], fill=ink)
    elif key == 'oil':
        draw.polygon([(cx, cy - 7), (cx - 5, cy + 1), (cx + 5, cy + 1)], fill=ink)
        draw.ellipse([cx - 5, cy - 1, cx + 5, cy + 5], fill=ink)
    elif key == 'battery':
        draw.rectangle([cx - 7, cy - 3, cx + 6, cy + 4], fill=ink)
        draw.rectangle([cx - 5, cy - 5, cx - 1, cy - 3], fill=ink)
        draw.rectangle([cx + 1, cy - 5, cx + 4, cy - 3], fill=ink)
        light = (220, 220, 220) if isinstance(ink, tuple) and sum(ink) > 300 else (70, 70, 80)
        draw.line([(cx + 2, cy - 1), (cx + 2, cy + 2)], fill=light, width=1)
        draw.line([(cx,     cy + 1), (cx + 4, cy + 1)], fill=light, width=1)
    elif key == 'abs':
        draw.text((cx - 9, cy - 5), 'ABS', fill=ink, font=_font(FONT_BOLD, 9))
    elif key == 'door':
        draw.rectangle([cx - 8, cy - 5, cx + 8, cy + 4], outline=ink, width=2)
        draw.arc([cx - 1, cy - 5, cx + 13, cy + 7], start=270, end=360, fill=ink, width=2)
    elif key == 'seatbelt':
        draw.ellipse([cx - 4, cy - 7, cx + 4, cy - 1], fill=ink)
        draw.line([(cx, cy - 1), (cx + 6, cy + 5)],    fill=ink, width=2)
        draw.line([(cx, cy + 2), (cx, cy + 5)],         fill=ink, width=2)
        draw.line([(cx - 5, cy + 5), (cx + 6, cy + 5)], fill=ink, width=2)
    elif key == 'temp':
        draw.line([(cx, cy - 7), (cx, cy + 1)], fill=ink, width=2)
        draw.ellipse([cx - 4, cy, cx + 4, cy + 6], fill=ink)
        for ty in (cy - 5, cy - 2):
            draw.line([(cx, ty), (cx + 4, ty)], fill=ink, width=1)


def _draw_telltales(draw: ImageDraw.Draw, telltales: dict,
                    inactive_bg=(18, 18, 26), inactive_fg=(48, 48, 60)):
    """상단 텔테일 바 (아이콘 + 라벨)"""
    n      = len(TELLTALE_DEFS)
    cell_w = W // n  # 60px
    f_lbl  = _font(FONT_REG, 8)

    for i, (key, label, color) in enumerate(TELLTALE_DEFS):
        active  = telltales.get(key, False)
        icon_cx = i * cell_w + cell_w // 2
        x0, x1  = i * cell_w + 2, (i + 1) * cell_w - 2
        y0, y1  = 2, 44

        bg  = color        if active else inactive_bg
        ink = (12, 12, 18) if active else inactive_fg

        draw.rounded_rectangle([x0, y0, x1, y1], radius=4, fill=bg)
        _draw_telltale_icon(draw, key, icon_cx, 20, ink)

        lb = draw.textbbox((0, 0), label, font=f_lbl)
        lw = lb[2] - lb[0]
        draw.text((icon_cx - lw // 2, 33), label,
                  fill=(12, 12, 18) if active else inactive_fg, font=f_lbl)


def _draw_popup(draw: ImageDraw.Draw, popup: dict):
    """하단 팝업 카드"""
    color = POPUP_COLORS.get(popup.get('type', 'warning'), POPUP_COLORS['warning'])
    px0, py0 = 10, 213
    px1, py1 = W - 10, 263

    draw.rounded_rectangle([px0, py0, px1, py1], radius=6, fill=(14, 14, 22))
    draw.rounded_rectangle([px0, py0, px1, py1], radius=6, outline=color, width=1)
    draw.rounded_rectangle([px0, py0, px0 + 5, py1], radius=3, fill=color)

    icx, icy = px0 + 26, (py0 + py1) // 2
    t = popup.get('type', 'warning')
    if t == 'error':
        draw.ellipse([icx - 10, icy - 10, icx + 10, icy + 10], fill=color)
        draw.text((icx - 4, icy - 9), '!', fill=(12, 12, 20), font=_font(FONT_BOLD, 14))
    elif t == 'info':
        draw.ellipse([icx - 10, icy - 10, icx + 10, icy + 10], fill=color)
        draw.text((icx - 3, icy - 9), 'i', fill=(12, 12, 20), font=_font(FONT_BOLD, 14))
    else:
        draw.polygon([(icx, icy - 11), (icx - 11, icy + 8), (icx + 11, icy + 8)], fill=color)
        draw.text((icx - 3, icy - 3), '!', fill=(12, 12, 20), font=_font(FONT_BOLD, 12))

    draw.text((px0 + 46, py0 + 11), popup.get('title', ''),  fill=color,
              font=_font(FONT_KO_BOLD, 13))
    if popup.get('body'):
        draw.text((px0 + 46, py0 + 30), popup['body'], fill=(155, 155, 175),
                  font=_font(FONT_KO_REG, 11))


def _draw_prnd(draw: ImageDraw.Draw, gear: str, cx: int, cy: int, active_color, inactive_color):
    """P R N D 가로 선택 표시 (현대·기아 스타일)"""
    prnd    = ['P', 'R', 'N', 'D']
    f_prnd  = _font(FONT_BOLD, 20)
    spacing = 28
    total   = len(prnd) * spacing
    sx      = cx - total // 2 + 4

    for i, g in enumerate(prnd):
        gx = sx + i * spacing
        is_active = (g == gear)
        if is_active:
            draw.rounded_rectangle([gx - 11, cy - 13, gx + 11, cy + 11],
                                   radius=3, fill=active_color)
            txt_c = (10, 10, 16)
        else:
            txt_c = inactive_color
        b = draw.textbbox((0, 0), g, font=f_prnd)
        tw = b[2] - b[0]
        draw.text((gx - tw // 2, cy - 11), g, fill=txt_c, font=f_prnd)


# ─────────────────────────────────────────────────────────────────────────────
# Tesla 클러스터 (Model S/3/X/Y 스타일)
# ─────────────────────────────────────────────────────────────────────────────

_TESLA_GEAR_COLORS = {
    'D': (  0, 200, 120),
    'R': (220,  70,  70),
    'N': (200, 175,   0),
    'P': ( 90,  90, 115),
}


def _make_tesla_cluster(
    speed: int, gear: str, battery_pct: int, range_km: int,
    telltales: dict, popup: Optional[dict],
) -> Image.Image:
    sty  = BRAND_STYLE['tesla']
    img  = Image.new('RGB', (W, H), sty['bg'])
    draw = ImageDraw.Draw(img)

    _draw_telltales(draw, telltales, sty['inactive_bg'], sty['inactive_fg'])
    draw.line([(0, 47), (W, 47)], fill=sty['sep_line'], width=1)

    # ── 기어 (좌, x=0..160) ─────────────────────────────────
    gc    = _TESLA_GEAR_COLORS.get(gear, (120, 120, 140))
    f_g   = _font(FONT_BOLD, 70)
    f_glb = _font(FONT_REG, 11)
    gb    = draw.textbbox((0, 0), gear, font=f_g)
    draw.text((80 - (gb[2] - gb[0]) // 2, 85), gear, fill=gc, font=f_g)
    mode_lbl = GEAR_LABELS.get(gear, '')
    mb = draw.textbbox((0, 0), mode_lbl, font=f_glb)
    draw.text((80 - (mb[2] - mb[0]) // 2, 165), mode_lbl, fill=(70, 70, 90), font=f_glb)

    # ── 속도 (중앙, x=160..320) ──────────────────────────────
    f_spd  = _font(FONT_BOLD, 80)
    f_unit = _font(FONT_REG,  16)
    cx_spd = 240
    spd_txt = str(speed)
    sb = draw.textbbox((0, 0), spd_txt, font=f_spd)
    draw.text((cx_spd - (sb[2] - sb[0]) // 2, 80), spd_txt, fill=(255, 255, 255), font=f_spd)
    ub = draw.textbbox((0, 0), 'km/h', font=f_unit)
    draw.text((cx_spd - (ub[2] - ub[0]) // 2, 158), 'km/h', fill=(110, 110, 135), font=f_unit)
    for dot_x in (175, 200, 225, 255, 280, 305):
        active_dot = dot_x <= (175 + int((speed / 200) * 130))
        draw.ellipse([dot_x - 2, 183, dot_x + 2, 187],
                     fill=(0, 190, 110) if active_dot else (30, 30, 42))

    # ── 배터리 / 주행거리 (우, x=320..480) ───────────────────
    rx      = 400
    f_range = _font(FONT_BOLD, 22)
    f_pct   = _font(FONT_REG,  13)
    f_small = _font(FONT_REG,  10)
    rng_txt = f'{range_km} km'
    rnb = draw.textbbox((0, 0), rng_txt, font=f_range)
    draw.text((rx - (rnb[2] - rnb[0]) // 2, 72), rng_txt, fill=(220, 220, 235), font=f_range)
    draw.text((330, 108), '배터리', fill=(60, 60, 78), font=_font(FONT_KO_REG, 10))
    bx0, by0, bx1, by1 = 330, 122, 468, 134
    fill_x1  = bx0 + max(6, int((bx1 - bx0) * battery_pct / 100))
    bar_color = (0, 185, 108) if battery_pct > 30 else ((215, 158, 0) if battery_pct > 15 else (215, 55, 55))
    draw.rounded_rectangle([bx0, by0, bx1, by1],           radius=3, fill=(32, 32, 44))
    draw.rounded_rectangle([bx0, by0, fill_x1, by1],       radius=3, fill=bar_color)
    pct_txt = f'{battery_pct}%'
    pb = draw.textbbox((0, 0), pct_txt, font=f_pct)
    draw.text((rx - (pb[2] - pb[0]) // 2, 140), pct_txt, fill=(110, 110, 135), font=f_pct)

    if popup:
        _draw_popup(draw, popup)
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Hyundai 클러스터 (IONIQ 5 / IONIQ 6 스타일)
#
# Layout:
#   상단 텔테일 바 | P·R·N·D 선택(좌) + 속도(중앙) | 주행거리/배터리(우) | 팝업(하단)
# ─────────────────────────────────────────────────────────────────────────────

def _make_hyundai_cluster(
    speed: int, gear: str, battery_pct: int, range_km: int,
    telltales: dict, popup: Optional[dict],
) -> Image.Image:
    sty = BRAND_STYLE['hyundai']
    acc = sty['accent']  # (0, 170, 210) teal

    img  = Image.new('RGB', (W, H), sty['bg'])
    draw = ImageDraw.Draw(img)

    _draw_telltales(draw, telltales, sty['inactive_bg'], sty['inactive_fg'])
    draw.line([(0, 47), (W, 47)], fill=sty['sep_line'], width=1)

    # ── P·R·N·D 선택 (좌 패널 상단) ─────────────────────────
    _draw_prnd(draw, gear, cx=80, cy=65, active_color=acc, inactive_color=(30, 70, 100))

    # ── 속도 (중앙) ──────────────────────────────────────────
    f_spd  = _font(FONT_BOLD, 80)
    f_unit = _font(FONT_REG,  14)
    cx_spd = 240
    spd_txt = str(speed)
    sb = draw.textbbox((0, 0), spd_txt, font=f_spd)
    draw.text((cx_spd - (sb[2] - sb[0]) // 2, 75), spd_txt, fill=(255, 255, 255), font=f_spd)
    ub = draw.textbbox((0, 0), 'km/h', font=f_unit)
    draw.text((cx_spd - (ub[2] - ub[0]) // 2, 158), 'km/h', fill=(40, 110, 140), font=f_unit)

    # 속도 아크 (현대 스타일 — 얇은 teal 반원 아래)
    ar = 52
    arc_box = [cx_spd - ar, 175, cx_spd + ar, 175 + ar * 2]
    draw.arc(arc_box, start=190, end=350, fill=(15, 50, 70), width=3)
    end_angle = 190 + int((speed / 200) * 160)
    if speed > 0:
        draw.arc(arc_box, start=190, end=min(end_angle, 350), fill=acc, width=3)

    # ── 주행거리 / 배터리 (우 패널) ─────────────────────────
    rx      = 405
    f_range = _font(FONT_BOLD, 20)
    f_pct   = _font(FONT_REG,  12)
    f_small = _font(FONT_REG,  10)

    rng_txt = f'{range_km} km'
    rnb = draw.textbbox((0, 0), rng_txt, font=f_range)
    draw.text((rx - (rnb[2] - rnb[0]) // 2, 75), rng_txt, fill=(210, 235, 245), font=f_range)

    draw.text((332, 105), '예상 주행거리', fill=(25, 70, 100), font=_font(FONT_KO_REG, 10))

    # 배터리 바
    bx0, by0, bx1, by1 = 332, 122, 468, 133
    fill_x1  = bx0 + max(5, int((bx1 - bx0) * battery_pct / 100))
    bar_color = acc if battery_pct > 30 else ((200, 150, 0) if battery_pct > 15 else (210, 50, 50))
    draw.rounded_rectangle([bx0, by0, bx1, by1],     radius=3, fill=(15, 40, 65))
    draw.rounded_rectangle([bx0, by0, fill_x1, by1], radius=3, fill=bar_color)

    pct_txt = f'{battery_pct}%'
    pb = draw.textbbox((0, 0), pct_txt, font=f_pct)
    draw.text((rx - (pb[2] - pb[0]) // 2, 140), pct_txt, fill=(40, 110, 140), font=f_pct)

    # 우 패널 구분선 (현대 특유의 얇은 수직 장식선)
    draw.line([(320, 52), (320, 195)], fill=(0, 45, 70), width=1)

    if popup:
        _draw_popup(draw, popup)
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Kia 클러스터 (EV6 / EV9 스타일)
#
# Layout (비대칭):
#   상단 텔테일 바 | 속도 + P·R·N·D(좌측) | 에너지/주행거리(우측) | 팝업(하단)
# ─────────────────────────────────────────────────────────────────────────────

def _make_kia_cluster(
    speed: int, gear: str, battery_pct: int, range_km: int,
    telltales: dict, popup: Optional[dict],
) -> Image.Image:
    sty = BRAND_STYLE['kia']
    acc = sty['accent']  # (204, 14, 42) Kia red

    img  = Image.new('RGB', (W, H), sty['bg'])
    draw = ImageDraw.Draw(img)

    _draw_telltales(draw, telltales, sty['inactive_bg'], sty['inactive_fg'])
    draw.line([(0, 47), (W, 47)], fill=sty['sep_line'], width=1)

    # ── 속도 (좌측 중앙, cx=120) ────────────────────────────
    f_spd  = _font(FONT_BOLD, 76)
    f_unit = _font(FONT_REG,  13)
    cx_spd = 120
    spd_txt = str(speed)
    sb = draw.textbbox((0, 0), spd_txt, font=f_spd)
    draw.text((cx_spd - (sb[2] - sb[0]) // 2, 78), spd_txt, fill=(255, 255, 255), font=f_spd)
    ub = draw.textbbox((0, 0), 'km/h', font=f_unit)
    draw.text((cx_spd - (ub[2] - ub[0]) // 2, 161), 'km/h', fill=(80, 40, 46), font=f_unit)

    # ── P·R·N·D 선택 (속도 아래) ────────────────────────────
    _draw_prnd(draw, gear, cx=120, cy=184, active_color=acc, inactive_color=(60, 32, 36))

    # 속도 영역 우측 경계선 (기아 스타일 분리선)
    draw.line([(215, 52), (215, 205)], fill=(50, 18, 22), width=1)

    # ── 에너지 게이지 / 주행거리 (우 패널, x=225..470) ──────
    rx       = 350
    f_range  = _font(FONT_BOLD, 22)
    f_pct    = _font(FONT_REG,  12)
    f_label  = _font(FONT_REG,  10)
    f_small  = _font(FONT_REG,   9)

    # 주행거리
    rng_txt = f'{range_km} km'
    rnb = draw.textbbox((0, 0), rng_txt, font=f_range)
    draw.text((rx - (rnb[2] - rnb[0]) // 2, 72), rng_txt, fill=(230, 220, 222), font=f_range)

    draw.text((228, 100), '주행가능거리', fill=(55, 28, 32), font=_font(FONT_KO_REG, 10))

    # 배터리 수직 바 (기아 스타일)
    vbx0, vby0, vbx1, vby1 = 228, 115, 268, 175
    fill_y0 = vby1 - max(4, int((vby1 - vby0) * battery_pct / 100))
    bar_color = acc if battery_pct > 30 else ((200, 140, 0) if battery_pct > 15 else (180, 40, 40))
    draw.rounded_rectangle([vbx0, vby0, vbx1, vby1],     radius=4, fill=(30, 18, 20))
    draw.rounded_rectangle([vbx0, fill_y0, vbx1, vby1],  radius=4, fill=bar_color)

    pct_txt = f'{battery_pct}%'
    pb = draw.textbbox((0, 0), pct_txt, font=f_pct)
    draw.text((248 - (pb[2] - pb[0]) // 2, 178), pct_txt, fill=(80, 40, 46), font=f_pct)

    # 속도 스케일 바 (우 패널 오른쪽)
    draw.text((290, 100), '속도 범위', fill=(55, 28, 32), font=_font(FONT_KO_REG, 10))
    sbx0, sby0, sbx1, sby1 = 290, 115, 468, 125
    spd_fill = sbx0 + max(4, int((sbx1 - sbx0) * min(speed, 200) / 200))
    draw.rounded_rectangle([sbx0, sby0, sbx1, sby1],          radius=3, fill=(30, 18, 20))
    draw.rounded_rectangle([sbx0, sby0, spd_fill, sby1],      radius=3, fill=acc)

    draw.text((290, 130), '배터리 상태', fill=(55, 28, 32), font=_font(FONT_KO_REG, 10))
    for seg in range(10):
        sx0 = 290 + seg * 18
        sx1 = sx0 + 14
        filled = (seg < battery_pct // 10)
        seg_color = bar_color if filled else (30, 18, 20)
        draw.rounded_rectangle([sx0, 143, sx1, 158], radius=2, fill=seg_color)

    spd_lbl = f'{speed} km/h'
    sl = draw.textbbox((0, 0), spd_lbl, font=f_small)
    draw.text((468 - (sl[2] - sl[0]), 128), spd_lbl, fill=(60, 30, 34), font=f_small)

    if popup:
        _draw_popup(draw, popup)
    return img


# ─────────────────────────────────────────────────────────────────────────────
# 공통 인터페이스
# ─────────────────────────────────────────────────────────────────────────────

_BRAND_MAKE = {
    'tesla':   _make_tesla_cluster,
    'hyundai': _make_hyundai_cluster,
    'kia':     _make_kia_cluster,
}


def make_cluster_image(
    brand: str,
    speed: int = 80,
    gear: str = 'D',
    battery_pct: int = 80,
    range_km: int = 320,
    telltales: Optional[dict] = None,
    popup: Optional[dict] = None,
) -> Image.Image:
    if telltales is None:
        telltales = ALL_OFF.copy()
    return _BRAND_MAKE[brand](speed, gear, battery_pct, range_km, telltales, popup)


def compare_cluster(cmp: ImageComparator, brand: str,
                    base: str, curr: str, diff: str) -> CompareResult:
    """브랜드별 CLUSTER_ROIS 를 자동 적용한 비교"""
    return cmp.compare(base, curr, diff_output=diff, rois=BRAND_ROIS[brand])


def _rois(brand: str, *, popup_ocr: bool = False) -> list[ROI]:
    """
    BRAND_ROIS[brand] + OCR ROI 조합.

    속도 OCR은 항상 포함 (baseline vs current 자동 비교).
    popup_ocr=True 시 팝업 텍스트 OCR도 추가.
    """
    rois = list(BRAND_ROIS[brand])
    rois.append(ROI(
        name='속도(OCR)', strict=False, ocr=True,
        **BRAND_OCR_SPEED_ROI[brand],
    ))
    if popup_ocr:
        rois.append(ROI(
            name='팝업텍스트(OCR)', strict=False, ocr=True,
            ocr_lang='kor+eng', ocr_threshold=160,
            **POPUP_TEXT_OCR_COORD,
        ))
    return rois


# ─────────────────────────────────────────────────────────────────────────────
# HTML 리포트 생성
# ─────────────────────────────────────────────────────────────────────────────

def _b64(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _mime(path: str) -> str:
    return 'image/jpeg' if Path(path).suffix.lower() in ('.jpg', '.jpeg') else 'image/png'


def _img_to_b64(img: Image.Image) -> str:
    """PIL Image → PNG base64 문자열"""
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _roi_overlay_b64(img_path: str, roi_results: list) -> str:
    """
    이미지에 ROI 박스를 오버레이한 PNG를 base64로 반환합니다.
    통과 ROI → 초록, 실패 ROI → 빨간 테두리로 표시합니다.
    """
    img = Image.open(img_path).convert('RGB')
    draw = ImageDraw.Draw(img)
    for rr in roi_results:
        color = (220, 38, 38) if not rr.passed else (22, 163, 74)
        x0, y0, x1, y1 = rr.x, rr.y, rr.x + rr.width, rr.y + rr.height
        # 테두리 박스
        for w in range(2):
            draw.rectangle([x0 - w, y0 - w, x1 + w, y1 + w], outline=color)
        # 이름 레이블 배경 + 텍스트
        lbl = rr.name
        lx, ly = x0, max(y0 - 14, 0)
        lw = len(lbl) * 6 + 6
        draw.rectangle([lx, ly, lx + lw, y0], fill=color)
        draw.text((lx + 3, ly + 1), lbl, fill='white', font=_font(FONT_KO_REG, 9))
    return _img_to_b64(img)


def _roi_crop_b64(img_path: str, rr, scale: int = 3) -> str:
    """ROI 영역을 크롭한 PNG를 base64로 반환합니다."""
    img = Image.open(img_path).convert('RGB')
    crop = img.crop((rr.x, rr.y, rr.x + rr.width, rr.y + rr.height))
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    return _img_to_b64(crop)


def build_html_report(brand_sections: list[dict]) -> str:
    STATUS = {
        'PASS':         ('✅ PASS',         '#16a34a', '#f0fdf4', '#bbf7d0'),
        'SIMILAR_PASS': ('⚠️ SIMILAR PASS', '#b45309', '#fffbeb', '#fde68a'),
        'FAIL':         ('❌ FAIL',          '#dc2626', '#fef2f2', '#fecaca'),
    }

    all_cases = [c for bs in brand_sections for cat in bs['categories'] for c in cat['cases']]
    pass_n    = sum(1 for c in all_cases if c['result'].status == 'PASS')
    similar_n = sum(1 for c in all_cases if c['result'].status == 'SIMILAR_PASS')
    fail_n    = sum(1 for c in all_cases if c['result'].status == 'FAIL')

    # 브랜드별 통계 (탭 전환 시 summary 업데이트용)
    brand_stats: dict = {'all': {'pass': pass_n, 'similar': similar_n,
                                  'fail': fail_n, 'total': len(all_cases)}}
    for bs in brand_sections:
        bc = [c for cat in bs['categories'] for c in cat['cases']]
        brand_stats[bs['brand']] = {
            'pass':    sum(1 for c in bc if c['result'].status == 'PASS'),
            'similar': sum(1 for c in bc if c['result'].status == 'SIMILAR_PASS'),
            'fail':    sum(1 for c in bc if c['result'].status == 'FAIL'),
            'total':   len(bc),
        }

    # 브랜드 탭 버튼 HTML 사전 생성
    _tab_btns = ''
    for bs in brand_sections:
        bname = bs['brand']
        blabel = BRAND_STYLE[bname]['label'].split()[0]
        _tab_btns += f'<button class="tab-btn" onclick="filterBrand(\'{bname}\')">{blabel}</button>'

    body_html = ''
    case_num  = 0

    for bs in brand_sections:
        brand       = bs['brand']
        brand_label = BRAND_STYLE[brand]['label']
        brand_color = {
            'tesla':   '#00C878',
            'hyundai': '#00AAD2',
            'kia':     '#CC0E2A',
        }[brand]

        body_html += f"""
        <div class="brand-section" data-brand="{brand}">
          <div class="brand-head" style="border-left:6px solid {brand_color}">
            <span class="brand-title">{brand_label}</span>
          </div>"""

        for cat in bs['categories']:
            cat_pass = sum(1 for c in cat['cases'] if c['result'].status == 'PASS')
            cat_fail = sum(1 for c in cat['cases'] if c['result'].status == 'FAIL')
            cat_sim  = sum(1 for c in cat['cases'] if c['result'].status == 'SIMILAR_PASS')

            body_html += f"""
          <div class="category">
            <div class="cat-head">
              <span class="cat-icon">{cat.get('icon','📋')}</span>
              <span class="cat-title">{cat['name']}</span>
              <span class="cat-stats">
                <span style="color:#86efac">PASS {cat_pass}</span> &nbsp;
                <span style="color:#fde68a">SIMILAR {cat_sim}</span> &nbsp;
                <span style="color:#fca5a5">FAIL {cat_fail}</span> &nbsp;
                / {len(cat['cases'])}
              </span>
            </div>
            <div class="cat-desc">{cat.get('desc','')}</div>
            <div class="cards">"""

            for case in cat['cases']:
                case_num += 1
                r: CompareResult = case['result']
                label, color, bg, border_bg = STATUS.get(r.status, ('?', '#6b7280', '#f9fafb', '#e5e7eb'))

                def _img_tag(src_b64, mime='image/png', alt='', title='', clickable=True):
                    """클릭 시 라이트박스로 확대 가능한 img 태그"""
                    onclick = f' onclick="lb(this.src,\'{title}\')" style="cursor:zoom-in"' if clickable else ''
                    return f'<img src="data:{mime};base64,{src_b64}" alt="{alt}" title="{title}"{onclick}>'

                base_name = Path(case['baseline']).name
                curr_name = Path(case['current']).name

                if r.diff_image_path and Path(r.diff_image_path).exists():
                    diff_cell = (
                        f'<figure>{_img_tag(_b64(r.diff_image_path), alt="diff", title="Diff 이미지")}'
                        f'<figcaption>Diff<br><small>빨강 = 변경 영역</small></figcaption></figure>'
                    )
                else:
                    diff_cell = '<figure><div class="no-img">—</div><figcaption>Diff</figcaption></figure>'

                # ROI 오버레이 이미지 (ROI가 있을 때만)
                if r.roi_results:
                    base_ov = _roi_overlay_b64(case['baseline'], r.roi_results)
                    curr_ov = _roi_overlay_b64(case['current'],  r.roi_results)
                    base_fig = (
                        f'<figure>'
                        f'{_img_tag(base_ov, alt="baseline+ROI", title=f"Baseline: {base_name}")}'
                        f'<figcaption>Baseline<br><small>ROI 박스 오버레이</small><br>'
                        f'<code>{base_name}</code></figcaption></figure>'
                    )
                    curr_fig = (
                        f'<figure>'
                        f'{_img_tag(curr_ov, alt="current+ROI", title=f"Current: {curr_name}")}'
                        f'<figcaption>Current<br><small>ROI 박스 오버레이</small><br>'
                        f'<code>{curr_name}</code></figcaption></figure>'
                    )
                else:
                    base_fig = (
                        f'<figure>'
                        f'{_img_tag(_b64(case["baseline"]), mime=_mime(case["baseline"]), alt="baseline", title=f"Baseline: {base_name}")}'
                        f'<figcaption>Baseline<br><code>{base_name}</code></figcaption></figure>'
                    )
                    curr_fig = (
                        f'<figure>'
                        f'{_img_tag(_b64(case["current"]), mime=_mime(case["current"]), alt="current", title=f"Current: {curr_name}")}'
                        f'<figcaption>Current<br><code>{curr_name}</code></figcaption></figure>'
                    )

                roi_rows = ''
                if r.roi_results:
                    for rr in r.roi_results:
                        row_cls = 'rpass' if rr.passed else 'rfail'
                        st_icon = '✅' if rr.passed else '❌'

                        # 크롭 썸네일 (baseline / current)
                        b_crop = _roi_crop_b64(case['baseline'], rr)
                        c_crop = _roi_crop_b64(case['current'],  rr)
                        crop_td = (
                            f'<td><div class="crop-cell">'
                            f'<div class="crop-pair">'
                            f'<div>{_img_tag(b_crop, alt=f"Base:{rr.name}", title=f"Baseline: {rr.name}")}'
                            f'<div class="crop-label">Base</div></div>'
                            f'<div>{_img_tag(c_crop, alt=f"Curr:{rr.name}", title=f"Current: {rr.name}")}'
                            f'<div class="crop-label">Curr</div></div>'
                            f'</div>'
                            f'<b style="font-size:12px">{rr.name}</b>'
                            f'</div></td>'
                        )

                        # Hue 열
                        if rr.hue_diff > 0:
                            hue_cls = 'ocr-ng' if rr.color_failed else 'ocr-ok'
                            hue_td  = f'<td class="rval {hue_cls}">{rr.hue_diff:.1f}°</td>'
                        else:
                            hue_td  = '<td class="ocr-na">—</td>'

                        # OCR 열 (baseline vs current 비교)
                        def _ocr_disp(val):
                            if val is None:
                                return '<span class="ocr-na">N/A</span>'
                            if val.strip() == '':
                                return '<span class="ocr-na">(없음)</span>'
                            return val.replace('\n', '<br>')

                        if rr.ocr_base is not None or rr.ocr_curr is not None:
                            match_cls  = 'ocr-ok' if not rr.ocr_failed else 'ocr-ng'
                            match_icon = '✅' if not rr.ocr_failed else '❌'
                            ocr_tds = (
                                f'<td class="rval">{_ocr_disp(rr.ocr_base)}</td>'
                                f'<td class="rval {match_cls}">{_ocr_disp(rr.ocr_curr)}</td>'
                                f'<td>{match_icon}</td>'
                            )
                        else:
                            ocr_tds = '<td class="ocr-na" colspan="3">—</td>'

                        roi_rows += (
                            f'<tr class="{row_cls}">'
                            f'{crop_td}'
                            f'<td class="rval">{rr.ssim:.4f}</td>'
                            f'<td class="rval">{rr.diff_pct:.3f}%</td>'
                            f'{hue_td}{ocr_tds}'
                            f'<td style="text-align:center">{st_icon}</td>'
                            f'</tr>'
                        )

                desc_html = case.get('desc', '').replace('\n', '<br>')

                body_html += f"""
              <div class="card" style="border-top:4px solid {color}">
                <div class="card-head" style="background:{border_bg}">
                  <span class="case-n">Case {case_num}</span>
                  <span class="case-name">{case['name'].replace(chr(10),'<br>')}</span>
                  <span class="badge" style="background:{color}">{label}</span>
                </div>
                {'<div class="desc">' + desc_html + '</div>' if desc_html else ''}
                <div class="imgs">
                  {base_fig}
                  {curr_fig}
                  {diff_cell}
                </div>
                <div class="metrics">
                  <div class="m"><span class="ml">브랜드</span><span class="mv">{brand.upper()}</span></div>
                  <div class="m"><span class="ml">모드</span><span class="mv">{r.mode.upper()}</span></div>
                  <div class="m"><span class="ml">SSIM</span><span class="mv">{r.ssim_score:.4f}</span></div>
                  <div class="m"><span class="ml">Diff</span><span class="mv">{r.diff_pct:.3f}%</span></div>
                  <div class="m"><span class="ml">판정</span><span class="mv" style="color:{color}">{r.status}</span></div>
                </div>
                <div class="msg">{r.message}</div>
                {'''<div class="roi-section">
                  <div class="roi-title">ROI 검사 결과</div>
                  <div style="overflow-x:auto">
                  <table class="roi-table">
                    <thead><tr>
                      <th>영역 (Base / Curr 크롭)</th><th>SSIM</th><th>Diff</th>
                      <th>Hue</th><th>OCR 기대 (Baseline)</th><th>OCR 실제 (Current)</th><th>OCR</th><th>결과</th>
                    </tr></thead>
                    <tbody>''' + roi_rows + '''</tbody>
                  </table>
                  </div>
                </div>''' if roi_rows else ''}
              </div>"""

            body_html += '</div></div>'
        body_html += '</div>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>이미지 비교 테스트 리포트</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic',sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.5}}
header{{background:linear-gradient(135deg,#0f172a,#1e3a8a);color:#fff;padding:28px 40px}}
header h1{{font-size:22px;font-weight:700;margin-bottom:6px}}
header p{{font-size:13px;opacity:.7}}
.summary{{display:flex;gap:14px;padding:22px 40px}}
.sc{{flex:1;background:#fff;border-radius:12px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.sc .n{{font-size:34px;font-weight:700}}
.sc .l{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-top:4px}}
.strategy{{margin:0 40px 28px;background:#eff6ff;border-left:5px solid #3b82f6;padding:14px 18px;border-radius:0 10px 10px 0;font-size:13px}}
.strategy p{{margin:4px 0}}
/* Brand section */
.brand-section{{margin:0 40px 40px}}
.brand-head{{padding:14px 20px;background:#fff;border-radius:10px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.brand-title{{font-size:18px;font-weight:700;color:#0f172a}}
/* Category */
.category{{margin-bottom:20px}}
.cat-head{{display:flex;align-items:center;gap:10px;padding:12px 20px;background:#1e293b;border-radius:10px 10px 0 0}}
.cat-icon{{font-size:18px}}
.cat-title{{flex:1;font-size:15px;font-weight:700;color:#f1f5f9}}
.cat-stats{{font-size:12px;color:#94a3b8}}
.cat-desc{{padding:8px 20px;background:#334155;color:#94a3b8;font-size:12px;border-bottom:1px solid #475569}}
.cards{{display:grid;gap:0;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;overflow:hidden}}
/* Card */
.card{{background:#fff}}
.card+.card{{border-top:1px solid #f1f5f9}}
.card-head{{display:flex;align-items:center;gap:12px;padding:12px 20px}}
.case-n{{font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase}}
.case-name{{flex:1;font-size:14px;font-weight:600}}
.badge{{padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700;color:#fff}}
.desc{{padding:6px 20px 0;font-size:12px;color:#64748b}}
.imgs{{display:flex;gap:14px;padding:14px 20px;overflow-x:auto}}
figure{{flex:1;min-width:170px;text-align:center}}
figure img{{max-width:100%;border-radius:8px;border:1px solid #e2e8f0}}
figcaption{{margin-top:6px;font-size:12px;color:#64748b}}
figcaption code{{font-size:10px;color:#94a3b8}}
.no-img{{height:130px;background:#f8fafc;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#cbd5e1;font-size:28px}}
.metrics{{display:flex;border-top:1px solid #f1f5f9;border-bottom:1px solid #f1f5f9}}
.m{{flex:1;padding:10px 8px;text-align:center}}
.m+.m{{border-left:1px solid #f1f5f9}}
.ml{{display:block;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}}
.mv{{display:block;font-size:15px;font-weight:700}}
.msg{{padding:10px 20px;font-size:12px;color:#475569;background:#f8fafc}}
.elements{{display:flex;flex-wrap:wrap;gap:8px;padding:12px 20px;border-top:1px solid #f1f5f9;background:#fafbfc}}
.chip{{padding:5px 13px;border-radius:20px;font-size:12px;font-weight:600}}
.chip-pass{{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}}
.chip-fail{{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}}
/* ROI 상세 테이블 */
.roi-section{{border-top:1px solid #f1f5f9}}
.roi-title{{padding:8px 20px 4px;font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em;background:#fafbfc}}
.roi-table{{width:100%;border-collapse:collapse;font-size:12px}}
.roi-table th{{background:#f1f5f9;color:#64748b;font-weight:600;padding:6px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #e2e8f0}}
.roi-table td{{padding:7px 12px;border-bottom:1px solid #f8fafc;vertical-align:middle}}
.roi-table tr:last-child td{{border-bottom:none}}
.roi-table tr.rpass td{{background:#fafffe}}
.roi-table tr.rfail td{{background:#fff8f8}}
.rval{{font-family:monospace;font-weight:600;font-size:12px}}
.ocr-ok{{color:#16a34a;font-weight:700}}
.ocr-ng{{color:#dc2626;font-weight:700}}
.ocr-na{{color:#cbd5e1}}
/* ROI 크롭 썸네일 */
.crop-pair{{display:flex;gap:4px;align-items:center}}
.crop-pair img{{height:44px;border-radius:4px;border:1px solid #e2e8f0;cursor:pointer}}
.crop-pair img:hover{{border-color:#94a3b8;transform:scale(1.05);transition:.15s}}
.crop-label{{font-size:10px;color:#94a3b8;text-align:center;margin-top:2px}}
.crop-cell{{display:flex;flex-direction:column;gap:6px}}
/* 브랜드 탭 */
.tab-bar{{display:flex;gap:8px;padding:18px 40px 0;background:#f1f5f9}}
.tab-btn{{padding:8px 22px;border:none;border-radius:8px 8px 0 0;font-size:13px;font-weight:600;cursor:pointer;background:#e2e8f0;color:#64748b;transition:.15s}}
.tab-btn:hover{{background:#cbd5e1;color:#1e293b}}
.tab-btn.active{{background:#fff;color:#0f172a;box-shadow:0 -2px 0 #3b82f6 inset}}
.brand-section{{display:block}}
.brand-section.hidden{{display:none}}
</style>
</head>
<body>
<header>
  <h1>이미지 비교 테스트 리포트</h1>
  <p>PNG Strict + JPG Perceptual Hybrid &nbsp;|&nbsp; 클러스터 요소별 ROI 자동 검사 &nbsp;|&nbsp; Tesla / Hyundai / Kia</p>
</header>
<div class="tab-bar">
  <button class="tab-btn active" onclick="filterBrand('all')">전체</button>
  {_tab_btns}
</div>
<div class="summary">
  <div class="sc"><div class="n" id="sc-pass" style="color:#16a34a">{pass_n}</div><div class="l">PASS</div></div>
  <div class="sc"><div class="n" id="sc-similar" style="color:#b45309">{similar_n}</div><div class="l">SIMILAR PASS</div></div>
  <div class="sc"><div class="n" id="sc-fail" style="color:#dc2626">{fail_n}</div><div class="l">FAIL</div></div>
  <div class="sc"><div class="n" id="sc-total">{len(all_cases)}</div><div class="l">전체</div></div>
</div>
<div class="strategy">
  <p><b>비교 전략</b></p>
  <p>• <b>PNG</b> &nbsp;무손실 → 엄격 비교 (SSIM ≥ 0.98, diff &lt; 0.1%)</p>
  <p>• <b>JPG</b> &nbsp;손실 압축 → 지각적 유사도 기반 (SSIM ≥ 0.95, diff &lt; 3.0%)</p>
  <p>• <b>ROI</b> &nbsp;모든 케이스에 브랜드별 표준 4개 영역(텔테일/속도/배터리/팝업) 자동 검사</p>
</div>
{body_html}
<script>
const STATS = {json.dumps(brand_stats, ensure_ascii=False)};
function filterBrand(brand) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {{
    if (b.getAttribute('onclick') === `filterBrand('${{brand}}')`) b.classList.add('active');
  }});
  document.querySelectorAll('.brand-section').forEach(el => {{
    if (brand === 'all' || el.dataset.brand === brand) el.classList.remove('hidden');
    else el.classList.add('hidden');
  }});
  const s = STATS[brand] || STATS['all'];
  document.getElementById('sc-pass').textContent    = s.pass;
  document.getElementById('sc-similar').textContent = s.similar;
  document.getElementById('sc-fail').textContent    = s.fail;
  document.getElementById('sc-total').textContent   = s.total;
}}
function lb(src, title) {{
  document.getElementById('lb-img').src = src;
  document.getElementById('lb-cap').textContent = title || '';
  document.getElementById('lb').style.display = 'flex';
}}
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') document.getElementById('lb').style.display = 'none';
}});
</script>
<!-- 라이트박스 오버레이 -->
<div id="lb" onclick="this.style.display='none'"
  style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;
         justify-content:center;align-items:center;flex-direction:column;cursor:zoom-out;">
  <img id="lb-img" style="max-width:92vw;max-height:88vh;object-fit:contain;
       border:2px solid #555;border-radius:6px;box-shadow:0 8px 40px #000a">
  <div id="lb-cap" style="color:#bbb;margin-top:10px;font-size:13px;max-width:90vw;text-align:center"></div>
  <div style="color:#666;font-size:11px;margin-top:4px">클릭하거나 ESC 로 닫기</div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 케이스 실행 (브랜드별 공통 15케이스)
# ─────────────────────────────────────────────────────────────────────────────

def _print_result(r: CompareResult):
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    for rr in r.roi_results:
        ok = '✅' if rr.passed else '❌'
        print(f'          {ok} [{rr.name}]  SSIM={rr.ssim}  diff={rr.diff_pct}%')


def _save(img: Image.Image, path: Path, quality: Optional[int] = None):
    if quality is not None:
        img.save(path, quality=quality)
    else:
        img.save(path)


def run_brand(brand: str, cmp: ImageComparator) -> list[dict]:
    """브랜드별 15개 케이스 실행 → categories 리스트 반환"""
    bd = OUT / brand
    bd.mkdir(exist_ok=True)

    def p(name): return str(bd / name)  # 경로 단축

    print(f'\n{"━"*62}')
    print(f'  [{brand.upper()}]  {BRAND_STYLE[brand]["label"]}')
    print(f'{"━"*62}')

    # ── 속도 표시 테스트 ──────────────────────────────────
    print('\n  [ 속도 표시 테스트 ]')
    gauge_cases = []

    # G-1: PNG 동일
    print('    G-1. PNG 동일')
    img = make_cluster_image(brand, speed=80)
    _save(img, bd/'g1_base.png'); _save(img, bd/'g1_curr.png')
    r = cmp.compare(p('g1_base.png'), p('g1_curr.png'), diff_output=p('g1_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    gauge_cases.append({'name': 'PNG 동일', 'baseline': p('g1_base.png'), 'current': p('g1_curr.png'), 'result': r})

    # G-2: PNG 속도 변화 (80→120)
    print('    G-2. PNG 속도 변화 (80 → 120)')
    _save(make_cluster_image(brand, speed=80),  bd/'g2_base.png')
    _save(make_cluster_image(brand, speed=120), bd/'g2_curr.png')
    r = cmp.compare(p('g2_base.png'), p('g2_curr.png'), diff_output=p('g2_diff.png'),
                    rois=_rois(brand))  # baseline OCR=80, current OCR=120 → 불일치 FAIL
    _print_result(r)
    gauge_cases.append({'name': 'PNG 속도 변화\n(80 → 120)', 'baseline': p('g2_base.png'), 'current': p('g2_curr.png'), 'result': r})

    # G-3: JPG 동일 내용, 압축률 차이
    print('    G-3. JPG 압축률 차이 (Q=95 vs Q=70)')
    img = make_cluster_image(brand, speed=60)
    _save(img, bd/'g3_base.jpg', quality=95); _save(img, bd/'g3_curr.jpg', quality=70)
    r = cmp.compare(p('g3_base.jpg'), p('g3_curr.jpg'), diff_output=p('g3_diff.png'),
                    rois=_rois(brand))  # 동일 내용 → baseline=current=60 → PASS
    _print_result(r)
    gauge_cases.append({'name': 'JPG 압축률 차이\n(Q=95 vs Q=70)',
                        'desc': 'JPG perceptual 모드로 PASS — 압축 아티팩트에도 OCR은 속도=60 정확히 인식',
                        'baseline': p('g3_base.jpg'), 'current': p('g3_curr.jpg'), 'result': r})

    # G-4: JPG 미세 속도 변화 (80→90) — ROI + OCR 가 잡아냄
    print('    G-4. JPG 미세 속도 변화 (80 → 90)')
    _save(make_cluster_image(brand, speed=80), bd/'g4_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=90), bd/'g4_curr.jpg', quality=90)
    r = cmp.compare(p('g4_base.jpg'), p('g4_curr.jpg'), diff_output=p('g4_diff.png'),
                    rois=_rois(brand))  # baseline OCR=80, current OCR=90 → 불일치 FAIL
    _print_result(r)
    gauge_cases.append({'name': 'JPG 미세 속도 변화\n(80 → 90)',
                        'desc': '전체 SSIM은 높지만 속도 ROI + OCR에서 변화 감지 → FAIL',
                        'baseline': p('g4_base.jpg'), 'current': p('g4_curr.jpg'), 'result': r})

    # G-5: JPG 극단 압축 (SIMILAR PASS 시연 — ROI 없음, 포맷 허용 오차 전용)
    print('    G-5. JPG 극단 압축 차이 (Q=95 vs Q=20)')
    img = make_cluster_image(brand, speed=100)
    _save(img, bd/'g5_base.jpg', quality=95); _save(img, bd/'g5_curr.jpg', quality=20)
    r = cmp.compare(p('g5_base.jpg'), p('g5_curr.jpg'), diff_output=p('g5_diff.png'))
    _print_result(r)
    gauge_cases.append({'name': 'JPG 극단 압축 차이\n(Q=95 vs Q=20)',
                        'desc': ('SIMILAR PASS 시연 — 극단적 Q=20 압축 아티팩트로 ROI 검사 불가\n'
                                 '전체 SSIM 기반 지각적 유사도만 판정 (ROI·OCR 검사 없음)'),
                        'baseline': p('g5_base.jpg'), 'current': p('g5_curr.jpg'), 'result': r})

    # G-6: OCR 속도 검증 — 동일 (PASS 기대)
    print('    G-6. OCR 속도 검증 — 동일 (80 → 80)')
    img = make_cluster_image(brand, speed=80)
    _save(img, bd/'g6_base.jpg', quality=90); _save(img, bd/'g6_curr.jpg', quality=90)
    r = cmp.compare(p('g6_base.jpg'), p('g6_curr.jpg'), diff_output=p('g6_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    gauge_cases.append({'name': 'OCR 속도 검증\n(80 → 80, PASS 기대)',
                        'desc': 'OCR로 속도 숫자를 직접 읽어 기대값(80)과 비교 — 동일하므로 PASS',
                        'baseline': p('g6_base.jpg'), 'current': p('g6_curr.jpg'), 'result': r})

    # G-7: OCR 속도 검증 — 변경 감지 (FAIL 기대)
    print('    G-7. OCR 속도 검증 — 속도 변경 감지 (80 → 60)')
    _save(make_cluster_image(brand, speed=80), bd/'g7_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=60), bd/'g7_curr.jpg', quality=90)
    r = cmp.compare(p('g7_base.jpg'), p('g7_curr.jpg'), diff_output=p('g7_diff.png'),
                    rois=_rois(brand))  # baseline OCR=80, current OCR=60 → 불일치 FAIL
    _print_result(r)
    gauge_cases.append({'name': 'OCR 속도 검증\n(80 → 60, FAIL 기대)',
                        'desc': 'OCR 기대값=80, 실제=60 — 숫자가 달라 FAIL\nSSIM만으로는 놓칠 수 있는 케이스를 OCR이 정확히 잡아냄',
                        'baseline': p('g7_base.jpg'), 'current': p('g7_curr.jpg'), 'result': r})

    # ── 팝업 테스트 ────────────────────────────────────────
    print('\n  [ 팝업 테스트 ]')
    popup_cases = []

    # P-1
    print('    P-1. JPG 팝업 없음 (동일)')
    img = make_cluster_image(brand, speed=70)
    _save(img, bd/'p1_base.jpg', quality=90); _save(img, bd/'p1_curr.jpg', quality=90)
    r = cmp.compare(p('p1_base.jpg'), p('p1_curr.jpg'), diff_output=p('p1_diff.png'),
                    rois=_rois(brand, popup_ocr=True))
    _print_result(r)
    popup_cases.append({'name': 'JPG 팝업 없음 (동일)', 'baseline': p('p1_base.jpg'), 'current': p('p1_curr.jpg'), 'result': r})

    # P-2
    print('    P-2. JPG 팝업 등장 (warning)')
    _save(make_cluster_image(brand, speed=70), bd/'p2_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=70, popup={'title':'오일 교환 필요','body':'주행 5,000km 초과','type':'warning'}),
          bd/'p2_curr.jpg', quality=90)
    r = cmp.compare(p('p2_base.jpg'), p('p2_curr.jpg'), diff_output=p('p2_diff.png'),
                    rois=_rois(brand, popup_ocr=True))
    _print_result(r)
    popup_cases.append({'name': 'JPG 팝업 등장\n(warning: 오일 교환 필요)',
                        'desc': '팝업 없음 → warning 팝업 등장 — SSIM FAIL + OCR로 팝업 텍스트 내용 확인',
                        'baseline': p('p2_base.jpg'), 'current': p('p2_curr.jpg'), 'result': r})

    # P-3
    print('    P-3. JPG 팝업 종류 변경 (warning → error)')
    _save(make_cluster_image(brand, speed=70, popup={'title':'오일 교환 필요','body':'주행 5,000km 초과','type':'warning'}),
          bd/'p3_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=70, popup={'title':'차량 점검 필요','body':'가까운 정비소 방문','type':'error'}),
          bd/'p3_curr.jpg', quality=90)
    r = cmp.compare(p('p3_base.jpg'), p('p3_curr.jpg'), diff_output=p('p3_diff.png'),
                    rois=_rois(brand, popup_ocr=True))
    _print_result(r)
    popup_cases.append({'name': 'JPG 팝업 종류 변경\n(warning → error)',
                        'desc': '팝업 타입 변경 → SSIM FAIL + OCR로 변경된 텍스트 내용 확인',
                        'baseline': p('p3_base.jpg'), 'current': p('p3_curr.jpg'), 'result': r})

    # P-4
    print('    P-4. JPG 동일 팝업 (warning 켜진 상태, 동일)')
    img = make_cluster_image(brand, speed=70, popup={'title':'오일 교환 필요','body':'주행 5,000km 초과','type':'warning'})
    _save(img, bd/'p4_base.jpg', quality=90); _save(img, bd/'p4_curr.jpg', quality=90)
    r = cmp.compare(p('p4_base.jpg'), p('p4_curr.jpg'), diff_output=p('p4_diff.png'),
                    rois=_rois(brand, popup_ocr=True))
    _print_result(r)
    popup_cases.append({'name': 'JPG 동일 팝업\n(warning 상태, 동일)',
                        'desc': '팝업 켜진 상태에서 동일 비교 — SSIM PASS + OCR로 팝업 텍스트 동일 확인',
                        'baseline': p('p4_base.jpg'), 'current': p('p4_curr.jpg'), 'result': r})

    # P-5: 팝업 텍스트만 변경 — OCR 핵심 시연 케이스
    print('    P-5. JPG 팝업 텍스트 변경 (오일 → 타이어)')
    _save(make_cluster_image(brand, speed=70, popup={'title':'오일 교환 필요','body':'주행 5,000km 초과','type':'warning'}),
          bd/'p5_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=70, popup={'title':'타이어 공기압 부족','body':'앞 우측 타이어 확인','type':'warning'}),
          bd/'p5_curr.jpg', quality=90)
    # 기대값='오일 교환 필요', 실제='타이어 공기압 부족' → OCR FAIL
    r = cmp.compare(p('p5_base.jpg'), p('p5_curr.jpg'), diff_output=p('p5_diff.png'),
                    rois=_rois(brand, popup_ocr=True))
    _print_result(r)
    popup_cases.append({'name': 'JPG 팝업 텍스트 변경\n(오일 → 타이어 공기압)',
                        'desc': ('팝업 타입·구조는 같지만 메시지 내용이 다름\n'
                                 'SSIM은 구조 유사로 놓칠 수 있지만 OCR이 텍스트 변경을 정확히 감지 → FAIL'),
                        'baseline': p('p5_base.jpg'), 'current': p('p5_curr.jpg'), 'result': r})

    # ── 텔테일 테스트 ──────────────────────────────────────
    print('\n  [ 텔테일 테스트 ]')
    telltale_cases = []

    # T-1
    print('    T-1. JPG 텔테일 모두 off (동일)')
    img = make_cluster_image(brand, speed=80, telltales=ALL_OFF.copy())
    _save(img, bd/'t1_base.jpg', quality=90); _save(img, bd/'t1_curr.jpg', quality=90)
    r = cmp.compare(p('t1_base.jpg'), p('t1_curr.jpg'), diff_output=p('t1_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    telltale_cases.append({'name': 'JPG 텔테일 모두 off (동일)',
                           'baseline': p('t1_base.jpg'), 'current': p('t1_curr.jpg'), 'result': r})

    # T-2
    print('    T-2. JPG ENG + OIL 텔테일 켜짐')
    _save(make_cluster_image(brand, speed=80, telltales=ALL_OFF.copy()), bd/'t2_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=80, telltales={**ALL_OFF, 'engine':True, 'oil':True}),
          bd/'t2_curr.jpg', quality=90)
    r = cmp.compare(p('t2_base.jpg'), p('t2_curr.jpg'), diff_output=p('t2_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    telltale_cases.append({'name': 'JPG ENG + OIL 켜짐',
                           'desc': '텔테일 ROI에서 변화 감지 → FAIL',
                           'baseline': p('t2_base.jpg'), 'current': p('t2_curr.jpg'), 'result': r})

    # T-3
    print('    T-3. JPG BAT + DOOR + TEMP + SBT 켜짐')
    _save(make_cluster_image(brand, speed=80, telltales=ALL_OFF.copy()), bd/'t3_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=80,
                              telltales={**ALL_OFF, 'battery':True,'door':True,'temp':True,'seatbelt':True}),
          bd/'t3_curr.jpg', quality=90)
    r = cmp.compare(p('t3_base.jpg'), p('t3_curr.jpg'), diff_output=p('t3_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    telltale_cases.append({'name': 'JPG BAT+DOOR+TEMP+SBT 켜짐',
                           'baseline': p('t3_base.jpg'), 'current': p('t3_curr.jpg'), 'result': r})

    # T-4
    print('    T-4. JPG 동일 텔테일 활성 (ENG+OIL 켜진 상태, 동일)')
    img = make_cluster_image(brand, speed=80, telltales={**ALL_OFF, 'engine':True, 'oil':True})
    _save(img, bd/'t4_base.jpg', quality=90); _save(img, bd/'t4_curr.jpg', quality=90)
    r = cmp.compare(p('t4_base.jpg'), p('t4_curr.jpg'), diff_output=p('t4_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    telltale_cases.append({'name': 'JPG 동일 텔테일 활성\n(ENG+OIL 켜진 상태, 동일)',
                           'desc': '텔테일 켜진 상태에서 동일 비교 — False Positive 없이 PASS 기대',
                           'baseline': p('t4_base.jpg'), 'current': p('t4_curr.jpg'), 'result': r})

    # T-5
    print('    T-5. JPG 텔테일 패턴 교체 (ENG → FUEL, 켜진 수 동일)')
    _save(make_cluster_image(brand, speed=80, telltales={**ALL_OFF, 'engine':True}),
          bd/'t5_base.jpg', quality=90)
    _save(make_cluster_image(brand, speed=80, telltales={**ALL_OFF, 'fuel':True}),
          bd/'t5_curr.jpg', quality=90)
    r = cmp.compare(p('t5_base.jpg'), p('t5_curr.jpg'), diff_output=p('t5_diff.png'),
                    rois=_rois(brand))
    _print_result(r)
    telltale_cases.append({'name': 'JPG 텔테일 패턴 교체\n(ENG → FUEL, 켜진 수 동일)',
                           'desc': '켜진 수(1개)는 같지만 종류가 다름 — 패턴 차이를 감지해야 FAIL',
                           'baseline': p('t5_base.jpg'), 'current': p('t5_curr.jpg'), 'result': r})

    return [
        {'name': '속도 표시 테스트', 'icon': '🎯',
         'desc': '속도 변화 / JPG 압축 아티팩트 허용 / 미세 변화 ROI 감지 검증',
         'cases': gauge_cases},
        {'name': '팝업 테스트', 'icon': '💬',
         'desc': '팝업 등장 / 종류 변경 / 텍스트 변경 감지',
         'cases': popup_cases},
        {'name': '텔테일 테스트', 'icon': '⚠️',
         'desc': '경고등 활성 상태 변화 감지 — 패턴 교체(수는 같아도 종류 다르면 FAIL) 포함',
         'cases': telltale_cases},
    ]


def run(active_brand: str = 'all'):
    cmp    = ImageComparator()
    brands = ['tesla', 'hyundai', 'kia'] if active_brand == 'all' else [active_brand]

    brand_sections = []
    for brand in brands:
        categories = run_brand(brand, cmp)
        brand_sections.append({'brand': brand, 'categories': categories})

    print(f'\n{"━"*62}')
    print('HTML 리포트 생성 중...')
    report_path = OUT / 'report.html'
    report_path.write_text(build_html_report(brand_sections), encoding='utf-8')
    print(f'\n완료: {report_path.resolve()}')
    print(f'\n브라우저로 열기: wslview "{report_path.resolve()}"\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='클러스터 이미지 비교 데모')
    parser.add_argument(
        '--brand',
        choices=['tesla', 'hyundai', 'kia', 'all'],
        default=ACTIVE_BRAND,
        help='테스트할 브랜드 (기본값: ACTIVE_BRAND 설정값)',
    )
    args = parser.parse_args()
    run(args.brand)
