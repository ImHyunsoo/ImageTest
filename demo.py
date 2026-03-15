"""
demo.py — 고객 제안용 데모

게이지 / 팝업 / 텔테일 카테고리별로 이미지 비교를 시연하고
HTML 리포트를 생성합니다.

실행:
  python demo.py
"""
from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from image_compare import ImageComparator, ROI, CompareResult

# ─────────────────────────────────────────────────────────────────────────────
OUT = Path('demo_output')
OUT.mkdir(exist_ok=True)

FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG  = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


# ─────────────────────────────────────────────────────────────────────────────
# 텔테일 / 팝업 정의
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
    'info':    ( 50, 150, 255),
}

ALL_OFF = {k: False for k, *_ in TELLTALE_DEFS}


def _draw_telltale_icon(draw: ImageDraw.Draw, key: str, cx: int, cy: int, ink):
    if key == 'engine':
        draw.rectangle([cx - 7, cy - 3, cx + 7, cy + 6], fill=ink)
        draw.rectangle([cx - 5, cy - 6, cx - 1, cy - 3], fill=ink)
        draw.rectangle([cx + 1, cy - 6, cx + 5, cy - 3], fill=ink)
        draw.rectangle([cx - 10, cy,     cx - 7, cy + 4], fill=ink)
    elif key == 'fuel':
        draw.rectangle([cx - 7, cy - 5, cx + 3, cy + 6], fill=ink)
        draw.rectangle([cx + 3, cy - 5, cx + 8, cy - 1], fill=ink)
        draw.line([(cx + 8, cy - 5), (cx + 8, cy + 3)], fill=ink, width=2)
        draw.ellipse([cx + 5, cy + 1, cx + 10, cy + 6], fill=ink)
    elif key == 'oil':
        draw.polygon([(cx, cy - 7), (cx - 5, cy + 2), (cx + 5, cy + 2)], fill=ink)
        draw.ellipse([cx - 5, cy - 1, cx + 5, cy + 6], fill=ink)
    elif key == 'battery':
        draw.rectangle([cx - 8, cy - 3, cx + 7, cy + 5], fill=ink)
        draw.rectangle([cx - 6, cy - 5, cx - 2, cy - 3], fill=ink)
        draw.rectangle([cx + 2, cy - 5, cx + 5, cy - 3], fill=ink)
        light = (220, 220, 220) if isinstance(ink, tuple) and ink[0] > 100 else (80, 80, 80)
        draw.line([(cx + 3, cy - 1), (cx + 3, cy + 3)], fill=light, width=1)
        draw.line([(cx + 1, cy + 1), (cx + 5, cy + 1)], fill=light, width=1)
    elif key == 'abs':
        draw.text((cx - 9, cy - 5), 'ABS', fill=ink, font=_font(FONT_BOLD, 10))
    elif key == 'door':
        draw.rectangle([cx - 8, cy - 5, cx + 8, cy + 5], outline=ink, width=2)
        draw.arc([cx - 1, cy - 5, cx + 14, cy + 8], start=270, end=360, fill=ink, width=2)
    elif key == 'seatbelt':
        draw.ellipse([cx - 4, cy - 7, cx + 4, cy - 1], fill=ink)
        draw.line([(cx, cy - 1), (cx + 6, cy + 6)], fill=ink, width=2)
        draw.line([(cx, cy + 2), (cx, cy + 6)],     fill=ink, width=2)
        draw.line([(cx - 5, cy + 6), (cx + 6, cy + 6)], fill=ink, width=2)
    elif key == 'temp':
        draw.line([(cx, cy - 7), (cx, cy + 2)], fill=ink, width=2)
        draw.ellipse([cx - 4, cy + 1, cx + 4, cy + 7], fill=ink)
        for ty in (cy - 5, cy - 2, cy + 1):
            draw.line([(cx, ty), (cx + 4, ty)], fill=ink, width=1)


def _draw_telltales(draw: ImageDraw.Draw, telltales: dict):
    n      = len(TELLTALE_DEFS)
    cell_w = 400 // n
    y_top  = 253
    icon_h = 32
    f_lbl  = _font(FONT_REG, 9)

    for i, (key, label, color) in enumerate(TELLTALE_DEFS):
        active  = telltales.get(key, False)
        icon_cx = i * cell_w + cell_w // 2
        x0, x1  = icon_cx - 19, icon_cx + 19
        y0, y1  = y_top, y_top + icon_h
        bg  = color         if active else (38, 38, 52)
        ink = (20, 20, 20)  if active else (75, 75, 88)

        draw.rounded_rectangle([x0, y0, x1, y1], radius=4, fill=bg)
        _draw_telltale_icon(draw, key, icon_cx, y_top + 14, ink)

        lb = draw.textbbox((0, 0), label, font=f_lbl)
        lw = lb[2] - lb[0]
        draw.text((icon_cx - lw // 2, y_top + icon_h + 2), label,
                  fill=(20, 20, 20) if active else (60, 62, 72), font=f_lbl)


def _draw_popup(draw: ImageDraw.Draw, popup: dict):
    color = POPUP_COLORS.get(popup.get('type', 'warning'), POPUP_COLORS['warning'])
    px0, py0 = 78, 178
    px1, py1 = 322, 248

    draw.rectangle([px0, py0, px1, py1], fill=(10, 10, 18))
    draw.rectangle([px0, py0, px1, py1], outline=color, width=2)
    draw.rectangle([px0, py0, px0 + 5, py1], fill=color)

    icx, icy = px0 + 24, (py0 + py1) // 2
    t = popup.get('type', 'warning')
    if t == 'error':
        draw.ellipse([icx - 11, icy - 11, icx + 11, icy + 11], fill=color)
        draw.text((icx - 4, icy - 9), '!', fill=(10, 10, 18), font=_font(FONT_BOLD, 15))
    elif t == 'info':
        draw.ellipse([icx - 11, icy - 11, icx + 11, icy + 11], fill=color)
        draw.text((icx - 3, icy - 9), 'i', fill=(10, 10, 18), font=_font(FONT_BOLD, 15))
    else:
        draw.polygon([(icx, icy - 12), (icx - 12, icy + 8), (icx + 12, icy + 8)], fill=color)
        draw.text((icx - 3, icy - 4), '!', fill=(10, 10, 18), font=_font(FONT_BOLD, 13))

    f_title = _font(FONT_BOLD, 14)
    draw.text((px0 + 44, py0 + 11), popup.get('title', ''), fill=color, font=f_title)
    if popup.get('body'):
        draw.text((px0 + 44, py0 + 30), popup['body'], fill=(175, 175, 195),
                  font=_font(FONT_REG, 12))
    draw.text((px0 + 44, py0 + 48), '확인 버튼을 누르세요', fill=(90, 92, 108),
              font=_font(FONT_REG, 10))


# ─────────────────────────────────────────────────────────────────────────────
# 클러스터 이미지 생성 (400×300)
# ─────────────────────────────────────────────────────────────────────────────

def make_cluster_image(
    speed: int = 80,
    gauge_color: tuple = (0, 200, 100),
    telltales: Optional[dict] = None,
    popup: Optional[dict] = None,
) -> Image.Image:
    if telltales is None:
        telltales = ALL_OFF.copy()

    W, H = 400, 300
    img  = Image.new('RGB', (W, H), (18, 18, 30))
    draw = ImageDraw.Draw(img)

    cx, cy, R = 200, 138, 100

    # 외곽 링
    draw.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(80, 80, 120), width=4)

    # 눈금
    for i in range(25):
        angle    = math.radians(-150 + i * 12)
        is_major = (i % 5 == 0)
        r_inner  = R - (14 if is_major else 7)
        x0 = cx + r_inner * math.cos(angle)
        y0 = cy + r_inner * math.sin(angle)
        x1 = cx + (R - 2) * math.cos(angle)
        y1 = cy + (R - 2) * math.sin(angle)
        draw.line([(x0, y0), (x1, y1)],
                  fill=(200, 200, 220) if is_major else (90, 90, 110),
                  width=2 if is_major else 1)

    # 속도 호
    arc_end = int(-150 + (speed / 200) * 300)
    for deg in range(-150, arc_end):
        rad = math.radians(deg)
        x0  = cx + (R - 22) * math.cos(rad)
        y0  = cy + (R - 22) * math.sin(rad)
        x1  = cx + (R - 10) * math.cos(rad)
        y1  = cy + (R - 10) * math.sin(rad)
        draw.line([(x0, y0), (x1, y1)], fill=gauge_color, width=2)

    # 바늘
    needle_rad = math.radians(-150 + (speed / 200) * 300)
    nx = cx + (R - 28) * math.cos(needle_rad)
    ny = cy + (R - 28) * math.sin(needle_rad)
    draw.line([(cx, cy), (int(nx), int(ny))], fill=(255, 255, 255), width=3)
    draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(200, 200, 220))

    # 속도 숫자
    f_big  = _font(FONT_BOLD, 48)
    f_unit = _font(FONT_REG,  14)
    txt    = str(speed)
    bbox   = draw.textbbox((0, 0), txt, font=f_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), txt, fill=(255, 255, 255), font=f_big)
    draw.text((cx - 14, cy + th // 2 + 5), 'km/h', fill=(125, 125, 160), font=f_unit)

    # 속도 범위 표시 (0 / 100 / 200)
    f_range = _font(FONT_REG, 10)
    for spd, deg in [(0, -150), (100, 0), (200, 150)]:
        a  = math.radians(deg)
        rx = cx + (R - 28) * math.cos(a)
        ry = cy + (R - 28) * math.sin(a)
        lb = draw.textbbox((0, 0), str(spd), font=f_range)
        draw.text((rx - (lb[2] - lb[0]) // 2, ry - (lb[3] - lb[1]) // 2),
                  str(spd), fill=(120, 120, 145), font=f_range)

    # 텔테일 표시줄
    _draw_telltales(draw, telltales)

    # 팝업 오버레이
    if popup:
        _draw_popup(draw, popup)

    return img


# ─────────────────────────────────────────────────────────────────────────────
# HTML 리포트 — 카테고리별 구성
# ─────────────────────────────────────────────────────────────────────────────

def _b64(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _mime(path: str) -> str:
    return 'image/jpeg' if Path(path).suffix.lower() in ('.jpg', '.jpeg') else 'image/png'


def build_html_report(categories: list[dict]) -> str:
    """
    categories: [
        {'name': '게이지 테스트', 'icon': '🎯', 'cases': [...]},
        ...
    ]
    """
    STATUS = {
        'PASS':         ('✅ PASS',          '#16a34a', '#f0fdf4', '#bbf7d0'),
        'SIMILAR_PASS': ('⚠️ SIMILAR PASS',  '#b45309', '#fffbeb', '#fde68a'),
        'FAIL':         ('❌ FAIL',           '#dc2626', '#fef2f2', '#fecaca'),
    }

    all_cases  = [c for cat in categories for c in cat['cases']]
    pass_n     = sum(1 for c in all_cases if c['result'].status == 'PASS')
    similar_n  = sum(1 for c in all_cases if c['result'].status == 'SIMILAR_PASS')
    fail_n     = sum(1 for c in all_cases if c['result'].status == 'FAIL')
    total_n    = len(all_cases)

    body_html = ''
    case_num  = 0

    for cat in categories:
        cat_pass  = sum(1 for c in cat['cases'] if c['result'].status == 'PASS')
        cat_fail  = sum(1 for c in cat['cases'] if c['result'].status == 'FAIL')
        cat_sim   = sum(1 for c in cat['cases'] if c['result'].status == 'SIMILAR_PASS')
        cat_total = len(cat['cases'])

        body_html += f"""
        <div class="category">
          <div class="cat-head">
            <span class="cat-icon">{cat.get('icon', '📋')}</span>
            <span class="cat-title">{cat['name']}</span>
            <span class="cat-stats">
              <span style="color:#16a34a">PASS {cat_pass}</span> &nbsp;
              <span style="color:#b45309">SIMILAR {cat_sim}</span> &nbsp;
              <span style="color:#dc2626">FAIL {cat_fail}</span> &nbsp;
              / {cat_total}
            </span>
          </div>
          <div class="cat-desc">{cat.get('desc', '')}</div>
          <div class="cards">"""

        for case in cat['cases']:
            case_num += 1
            r: CompareResult = case['result']
            label, color, bg, border_bg = STATUS.get(r.status, ('?', '#6b7280', '#f9fafb', '#e5e7eb'))

            diff_cell = ''
            if r.diff_image_path and Path(r.diff_image_path).exists():
                diff_cell = (
                    f'<figure><img src="data:image/png;base64,{_b64(r.diff_image_path)}" alt="diff">'
                    f'<figcaption>Diff<br><small>빨강 = 변경 영역</small></figcaption></figure>'
                )
            else:
                diff_cell = '<figure><div class="no-img">—</div><figcaption>Diff</figcaption></figure>'

            roi_html = ''
            if r.roi_results:
                roi_html = '<div class="roi-block"><b>ROI 검사 결과</b><ul>'
                for rr in r.roi_results:
                    ok = '✅' if rr.passed else '❌'
                    roi_html += f'<li>{ok} <b>{rr.name}</b> &nbsp;SSIM: {rr.ssim} &nbsp;Diff: {rr.diff_pct}%</li>'
                roi_html += '</ul></div>'

            desc_html = case.get('desc', '').replace('\n', '<br>')

            body_html += f"""
            <div class="card" style="border-top:4px solid {color}">
              <div class="card-head" style="background:{border_bg}">
                <span class="case-n">Case {case_num}</span>
                <span class="case-name">{case['name'].replace(chr(10), '<br>')}</span>
                <span class="badge" style="background:{color}">{label}</span>
              </div>
              {'<div class="desc">' + desc_html + '</div>' if desc_html else ''}
              <div class="imgs">
                <figure>
                  <img src="data:{_mime(case['baseline'])};base64,{_b64(case['baseline'])}" alt="baseline">
                  <figcaption>Baseline<br><code>{Path(case['baseline']).name}</code></figcaption>
                </figure>
                <figure>
                  <img src="data:{_mime(case['current'])};base64,{_b64(case['current'])}" alt="current">
                  <figcaption>Current<br><code>{Path(case['current']).name}</code></figcaption>
                </figure>
                {diff_cell}
              </div>
              <div class="metrics">
                <div class="m"><span class="ml">모드</span><span class="mv">{r.mode.upper()}</span></div>
                <div class="m"><span class="ml">SSIM</span><span class="mv">{r.ssim_score:.4f}</span></div>
                <div class="m"><span class="ml">Diff</span><span class="mv">{r.diff_pct:.3f}%</span></div>
                <div class="m"><span class="ml">판정</span><span class="mv" style="color:{color}">{r.status}</span></div>
              </div>
              <div class="msg">{r.message}</div>
              {roi_html}
            </div>"""

        body_html += '</div></div>'  # .cards / .category

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
/* ── Category ── */
.category{{margin:0 40px 36px}}
.cat-head{{display:flex;align-items:center;gap:10px;padding:14px 20px;background:#1e293b;border-radius:10px 10px 0 0}}
.cat-icon{{font-size:20px}}
.cat-title{{flex:1;font-size:17px;font-weight:700;color:#f1f5f9}}
.cat-stats{{font-size:13px;color:#94a3b8}}
.cat-desc{{padding:10px 20px;background:#334155;color:#94a3b8;font-size:12px;border-bottom:1px solid #475569}}
.cards{{display:grid;gap:0;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;overflow:hidden}}
/* ── Card ── */
.card{{background:#fff}}
.card+.card{{border-top:1px solid #f1f5f9}}
.card-head{{display:flex;align-items:center;gap:12px;padding:14px 20px}}
.case-n{{font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase}}
.case-name{{flex:1;font-size:15px;font-weight:600}}
.badge{{padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700;color:#fff}}
.desc{{padding:6px 20px 0;font-size:12px;color:#64748b}}
.imgs{{display:flex;gap:14px;padding:16px 20px;overflow-x:auto}}
figure{{flex:1;min-width:170px;text-align:center}}
figure img{{max-width:100%;border-radius:8px;border:1px solid #e2e8f0}}
figcaption{{margin-top:6px;font-size:12px;color:#64748b}}
figcaption code{{font-size:10px;color:#94a3b8}}
.no-img{{height:160px;background:#f8fafc;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#cbd5e1;font-size:28px}}
.metrics{{display:flex;border-top:1px solid #f1f5f9;border-bottom:1px solid #f1f5f9}}
.m{{flex:1;padding:12px 16px;text-align:center}}
.m+.m{{border-left:1px solid #f1f5f9}}
.ml{{display:block;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}}
.mv{{display:block;font-size:17px;font-weight:700}}
.msg{{padding:11px 20px;font-size:13px;color:#475569;background:#f8fafc}}
.roi-block{{padding:12px 20px;border-top:1px solid #f1f5f9;font-size:13px}}
.roi-block b{{display:block;margin-bottom:8px;color:#374151}}
.roi-block ul{{list-style:none;display:flex;flex-direction:column;gap:5px}}
.roi-block li{{padding:6px 12px;background:#f8fafc;border-radius:6px}}
</style>
</head>
<body>
<header>
  <h1>이미지 비교 테스트 리포트</h1>
  <p>PNG Strict + JPG Perceptual Hybrid &nbsp;|&nbsp; 게이지 / 팝업 / 텔테일 카테고리별 검사</p>
</header>
<div class="summary">
  <div class="sc"><div class="n" style="color:#16a34a">{pass_n}</div><div class="l">PASS</div></div>
  <div class="sc"><div class="n" style="color:#b45309">{similar_n}</div><div class="l">SIMILAR PASS</div></div>
  <div class="sc"><div class="n" style="color:#dc2626">{fail_n}</div><div class="l">FAIL</div></div>
  <div class="sc"><div class="n">{total_n}</div><div class="l">전체</div></div>
</div>
<div class="strategy">
  <p><b>비교 전략</b></p>
  <p>• <b>PNG</b> &nbsp;무손실 → 엄격 비교 (SSIM ≥ 0.98, diff &lt; 0.1%)</p>
  <p>• <b>JPG</b> &nbsp;손실 압축 → 지각적 유사도 기반 (SSIM ≥ 0.95, diff &lt; 3.0%)</p>
  <p>• <b>ROI</b> &nbsp;게이지 숫자 / 텔테일 / 팝업 영역은 포맷 무관 PNG 엄격 기준으로 별도 검사</p>
</div>
{body_html}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 케이스 정의
# ─────────────────────────────────────────────────────────────────────────────

def run():
    cmp = ImageComparator()

    print('\n' + '━' * 58)
    print('  이미지 비교 데모 — 게이지 / 팝업 / 텔테일')
    print('━' * 58)

    # ════════════════════════════════════════════════════════
    # 카테고리 1: 게이지 테스트
    # ════════════════════════════════════════════════════════
    print('\n[ 게이지 테스트 ]')
    gauge_cases = []

    # G-1: PNG 동일 → PASS
    print('  G-1. PNG 동일')
    img = make_cluster_image(speed=80)
    img.save(OUT / 'g1_base.png')
    img.save(OUT / 'g1_curr.png')
    r = cmp.compare(str(OUT / 'g1_base.png'), str(OUT / 'g1_curr.png'),
                    diff_output=str(OUT / 'g1_diff.png'))
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    gauge_cases.append({
        'name': 'PNG 동일',
        'desc': '기준 이미지와 완전히 동일 — PASS 기대',
        'baseline': str(OUT / 'g1_base.png'),
        'current':  str(OUT / 'g1_curr.png'),
        'result': r,
    })

    # G-2: PNG 속도 변화 → FAIL
    print('  G-2. PNG 속도 변화 (80 → 120)')
    img1 = make_cluster_image(speed=80)
    img2 = make_cluster_image(speed=120, gauge_color=(220, 70, 30))
    img1.save(OUT / 'g2_base.png')
    img2.save(OUT / 'g2_curr.png')
    r = cmp.compare(str(OUT / 'g2_base.png'), str(OUT / 'g2_curr.png'),
                    diff_output=str(OUT / 'g2_diff.png'))
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    gauge_cases.append({
        'name': 'PNG 속도 변화\n(80 → 120, 게이지 색)',
        'baseline': str(OUT / 'g2_base.png'),
        'current':  str(OUT / 'g2_curr.png'),
        'result': r,
    })

    # G-3: JPG 압축률 차이만 (동일 속도) → PASS
    print('  G-3. JPG 동일 내용, 압축률 차이 (Q=95 vs Q=70)')
    img = make_cluster_image(speed=60)
    img.save(OUT / 'g3_base.jpg', quality=95)
    img.save(OUT / 'g3_curr.jpg', quality=70)
    r = cmp.compare(str(OUT / 'g3_base.jpg'), str(OUT / 'g3_curr.jpg'),
                    diff_output=str(OUT / 'g3_diff.png'))
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    gauge_cases.append({
        'name': 'JPG 압축률 차이\n(Q=95 vs Q=70, 동일 속도)',
        'desc': 'JPG perceptual 모드 덕분에 PASS — PNG strict 기준이면 압축 아티팩트로 FAIL 가능성 있음',
        'baseline': str(OUT / 'g3_base.jpg'),
        'current':  str(OUT / 'g3_curr.jpg'),
        'result': r,
    })

    # G-4: JPG + ROI 미세 속도 변화 감지
    print('  G-4. JPG 미세 속도 변화 + ROI (80 → 90)')
    img1 = make_cluster_image(speed=80)
    img2 = make_cluster_image(speed=90)
    img1.save(OUT / 'g4_base.jpg', quality=90)
    img2.save(OUT / 'g4_curr.jpg', quality=90)
    speed_roi = ROI(name='속도계 숫자 영역', x=150, y=108, width=100, height=80, strict=True)
    r = cmp.compare(str(OUT / 'g4_base.jpg'), str(OUT / 'g4_curr.jpg'),
                    diff_output=str(OUT / 'g4_diff.png'), rois=[speed_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    if r.roi_results:
        rr = r.roi_results[0]
        print(f'          ROI [{rr.name}] passed={rr.passed}  SSIM={rr.ssim}  diff={rr.diff_pct}%')
    gauge_cases.append({
        'name': 'JPG 미세 속도 변화 + ROI\n(80 → 90)',
        'desc': '전체 SSIM은 높지만 속도 숫자 ROI 영역에서 변화 감지 → FAIL',
        'baseline': str(OUT / 'g4_base.jpg'),
        'current':  str(OUT / 'g4_curr.jpg'),
        'result': r,
    })

    # G-5: SIMILAR_PASS 케이스 — 극단적 JPG 압축 아티팩트
    # PASS 기준(diff<3%)은 살짝 초과하지만 SIMILAR_PASS(diff<8%) 범위
    print('  G-5. JPG 극단 압축 차이 (Q=95 vs Q=40) — SIMILAR_PASS 기대')
    img = make_cluster_image(speed=100)
    img.save(OUT / 'g5_base.jpg', quality=95)
    img.save(OUT / 'g5_curr.jpg', quality=40)
    r = cmp.compare(str(OUT / 'g5_base.jpg'), str(OUT / 'g5_curr.jpg'),
                    diff_output=str(OUT / 'g5_diff.png'))
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    gauge_cases.append({
        'name': 'JPG 극단 압축 차이\n(Q=95 vs Q=40)',
        'desc': (
            'SIMILAR PASS 시연 케이스 — 동일 내용이지만 압축 품질 차이가 커서 PASS 기준(diff<3%)을 초과함. '
            '그러나 시각적으로 유사하므로 FAIL이 아닌 SIMILAR PASS로 판정.'
        ),
        'baseline': str(OUT / 'g5_base.jpg'),
        'current':  str(OUT / 'g5_curr.jpg'),
        'result': r,
    })

    # ════════════════════════════════════════════════════════
    # 카테고리 2: 팝업 테스트
    # ════════════════════════════════════════════════════════
    print('\n[ 팝업 테스트 ]')
    popup_cases = []

    # P-1: 팝업 없음 vs 없음 → PASS
    print('  P-1. JPG 팝업 없음 (동일)')
    img = make_cluster_image(speed=70)
    img.save(OUT / 'p1_base.jpg', quality=90)
    img.save(OUT / 'p1_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 'p1_base.jpg'), str(OUT / 'p1_curr.jpg'),
                    diff_output=str(OUT / 'p1_diff.png'))
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    popup_cases.append({
        'name': 'JPG 팝업 없음 (동일)',
        'baseline': str(OUT / 'p1_base.jpg'),
        'current':  str(OUT / 'p1_curr.jpg'),
        'result': r,
    })

    # P-2: 팝업 없음 → warning 팝업 등장 → FAIL
    print('  P-2. JPG 팝업 등장 — warning (오일 교환 필요)')
    img1 = make_cluster_image(speed=70)
    img2 = make_cluster_image(speed=70,
                               popup={'title': '오일 교환 필요',
                                      'body': '주행 5,000km 초과',
                                      'type': 'warning'})
    img1.save(OUT / 'p2_base.jpg', quality=90)
    img2.save(OUT / 'p2_curr.jpg', quality=90)
    popup_roi = ROI(name='팝업 영역', x=78, y=175, width=244, height=75, strict=True)
    r = cmp.compare(str(OUT / 'p2_base.jpg'), str(OUT / 'p2_curr.jpg'),
                    diff_output=str(OUT / 'p2_diff.png'), rois=[popup_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    if r.roi_results:
        rr = r.roi_results[0]
        print(f'          ROI [{rr.name}] passed={rr.passed}  SSIM={rr.ssim}  diff={rr.diff_pct}%')
    popup_cases.append({
        'name': 'JPG 팝업 등장\n(warning: 오일 교환 필요)',
        'desc': '팝업 없음 → warning 팝업 등장. 팝업 ROI 영역에서 변화 감지 → FAIL',
        'baseline': str(OUT / 'p2_base.jpg'),
        'current':  str(OUT / 'p2_curr.jpg'),
        'result': r,
    })

    # P-3: warning → error 팝업 변경 → FAIL
    print('  P-3. JPG 팝업 종류 변경 — warning → error')
    img1 = make_cluster_image(speed=70,
                               popup={'title': '오일 교환 필요',
                                      'body': '주행 5,000km 초과',
                                      'type': 'warning'})
    img2 = make_cluster_image(speed=70,
                               popup={'title': '차량 점검 필요',
                                      'body': '가까운 정비소 방문',
                                      'type': 'error'})
    img1.save(OUT / 'p3_base.jpg', quality=90)
    img2.save(OUT / 'p3_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 'p3_base.jpg'), str(OUT / 'p3_curr.jpg'),
                    diff_output=str(OUT / 'p3_diff.png'), rois=[popup_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    popup_cases.append({
        'name': 'JPG 팝업 종류 변경\n(warning → error)',
        'baseline': str(OUT / 'p3_base.jpg'),
        'current':  str(OUT / 'p3_curr.jpg'),
        'result': r,
    })

    # P-4: 동일 팝업 상태 → PASS  ← 사용자 요청
    print('  P-4. JPG 동일 팝업 (warning 켜진 상태에서 동일)')
    img = make_cluster_image(speed=70,
                             popup={'title': '오일 교환 필요',
                                    'body': '주행 5,000km 초과',
                                    'type': 'warning'})
    img.save(OUT / 'p4_base.jpg', quality=90)
    img.save(OUT / 'p4_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 'p4_base.jpg'), str(OUT / 'p4_curr.jpg'),
                    diff_output=str(OUT / 'p4_diff.png'), rois=[popup_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    popup_cases.append({
        'name': 'JPG 동일 팝업\n(warning 켜진 상태, 동일)',
        'desc': '팝업이 켜진 상태에서 동일한 이미지 비교 — False Positive 없이 PASS 기대',
        'baseline': str(OUT / 'p4_base.jpg'),
        'current':  str(OUT / 'p4_curr.jpg'),
        'result': r,
    })

    # P-5: 팝업 텍스트만 변경 → FAIL
    print('  P-5. JPG 팝업 텍스트 변경 (내용만 다름)')
    img1 = make_cluster_image(speed=70,
                               popup={'title': '오일 교환 필요',
                                      'body': '주행 5,000km 초과',
                                      'type': 'warning'})
    img2 = make_cluster_image(speed=70,
                               popup={'title': '타이어 공기압 부족',
                                      'body': '앞 우측 타이어 확인',
                                      'type': 'warning'})
    img1.save(OUT / 'p5_base.jpg', quality=90)
    img2.save(OUT / 'p5_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 'p5_base.jpg'), str(OUT / 'p5_curr.jpg'),
                    diff_output=str(OUT / 'p5_diff.png'), rois=[popup_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    popup_cases.append({
        'name': 'JPG 팝업 텍스트 변경\n(오일 교환 → 타이어 공기압)',
        'desc': '팝업 타입(warning)은 같지만 메시지 내용이 다름 → 팝업 ROI에서 텍스트 변경 감지 → FAIL',
        'baseline': str(OUT / 'p5_base.jpg'),
        'current':  str(OUT / 'p5_curr.jpg'),
        'result': r,
    })

    # ════════════════════════════════════════════════════════
    # 카테고리 3: 텔테일 테스트
    # ════════════════════════════════════════════════════════
    print('\n[ 텔테일 테스트 ]')
    telltale_cases = []
    telltale_roi = ROI(name='텔테일 표시줄', x=0, y=250, width=400, height=48, strict=True)

    # T-1: 모두 off vs off → PASS
    print('  T-1. JPG 텔테일 모두 off (동일)')
    img = make_cluster_image(speed=80, telltales=ALL_OFF.copy())
    img.save(OUT / 't1_base.jpg', quality=90)
    img.save(OUT / 't1_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 't1_base.jpg'), str(OUT / 't1_curr.jpg'),
                    diff_output=str(OUT / 't1_diff.png'))
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    telltale_cases.append({
        'name': 'JPG 텔테일 모두 off (동일)',
        'baseline': str(OUT / 't1_base.jpg'),
        'current':  str(OUT / 't1_curr.jpg'),
        'result': r,
    })

    # T-2: ENG + OIL 켜짐 → FAIL
    print('  T-2. JPG ENG + OIL 텔테일 켜짐')
    img1 = make_cluster_image(speed=80, telltales=ALL_OFF.copy())
    img2 = make_cluster_image(speed=80,
                               telltales={**ALL_OFF, 'engine': True, 'oil': True})
    img1.save(OUT / 't2_base.jpg', quality=90)
    img2.save(OUT / 't2_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 't2_base.jpg'), str(OUT / 't2_curr.jpg'),
                    diff_output=str(OUT / 't2_diff.png'), rois=[telltale_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    if r.roi_results:
        rr = r.roi_results[0]
        print(f'          ROI [{rr.name}] passed={rr.passed}  SSIM={rr.ssim}  diff={rr.diff_pct}%')
    telltale_cases.append({
        'name': 'JPG ENG + OIL 켜짐',
        'desc': '전체 SSIM은 높지만 텔테일 ROI에서 변화 감지 → FAIL',
        'baseline': str(OUT / 't2_base.jpg'),
        'current':  str(OUT / 't2_curr.jpg'),
        'result': r,
    })

    # T-3: 다수 텔테일 활성 (BAT + DOOR + TEMP + SBT) → FAIL
    print('  T-3. JPG BAT + DOOR + TEMP + SBT 켜짐')
    img1 = make_cluster_image(speed=80, telltales=ALL_OFF.copy())
    img2 = make_cluster_image(speed=80,
                               telltales={**ALL_OFF,
                                          'battery': True, 'door': True,
                                          'temp': True, 'seatbelt': True})
    img1.save(OUT / 't3_base.jpg', quality=90)
    img2.save(OUT / 't3_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 't3_base.jpg'), str(OUT / 't3_curr.jpg'),
                    diff_output=str(OUT / 't3_diff.png'), rois=[telltale_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    if r.roi_results:
        rr = r.roi_results[0]
        print(f'          ROI [{rr.name}] passed={rr.passed}  SSIM={rr.ssim}  diff={rr.diff_pct}%')
    telltale_cases.append({
        'name': 'JPG BAT + DOOR + TEMP + SBT 켜짐',
        'baseline': str(OUT / 't3_base.jpg'),
        'current':  str(OUT / 't3_curr.jpg'),
        'result': r,
    })

    # T-4: 동일 텔테일 활성 상태 → PASS  ← 사용자 요청
    print('  T-4. JPG 동일 텔테일 활성 (ENG+OIL 켜진 상태에서 동일)')
    img = make_cluster_image(speed=80, telltales={**ALL_OFF, 'engine': True, 'oil': True})
    img.save(OUT / 't4_base.jpg', quality=90)
    img.save(OUT / 't4_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 't4_base.jpg'), str(OUT / 't4_curr.jpg'),
                    diff_output=str(OUT / 't4_diff.png'), rois=[telltale_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    telltale_cases.append({
        'name': 'JPG 동일 텔테일 활성\n(ENG+OIL 켜진 상태, 동일)',
        'desc': '텔테일이 켜진 상태에서 동일한 이미지 비교 — False Positive 없이 PASS 기대',
        'baseline': str(OUT / 't4_base.jpg'),
        'current':  str(OUT / 't4_curr.jpg'),
        'result': r,
    })

    # T-5: 텔테일 패턴 교체 (같은 수, 다른 경고등) → FAIL
    print('  T-5. JPG 텔테일 패턴 교체 (ENG → FUEL, 켜진 수는 동일)')
    img1 = make_cluster_image(speed=80, telltales={**ALL_OFF, 'engine': True})
    img2 = make_cluster_image(speed=80, telltales={**ALL_OFF, 'fuel': True})
    img1.save(OUT / 't5_base.jpg', quality=90)
    img2.save(OUT / 't5_curr.jpg', quality=90)
    r = cmp.compare(str(OUT / 't5_base.jpg'), str(OUT / 't5_curr.jpg'),
                    diff_output=str(OUT / 't5_diff.png'), rois=[telltale_roi])
    print(f'       → {r.status}  SSIM={r.ssim_score:.4f}  diff={r.diff_pct:.3f}%')
    if r.roi_results:
        rr = r.roi_results[0]
        print(f'          ROI [{rr.name}] passed={rr.passed}  SSIM={rr.ssim}  diff={rr.diff_pct}%')
    telltale_cases.append({
        'name': 'JPG 텔테일 패턴 교체\n(ENG → FUEL, 켜진 수는 동일)',
        'desc': '켜진 텔테일 수(1개)는 같지만 종류가 다름 — 패턴 차이를 감지해야 FAIL',
        'baseline': str(OUT / 't5_base.jpg'),
        'current':  str(OUT / 't5_curr.jpg'),
        'result': r,
    })

    # ════════════════════════════════════════════════════════
    # HTML 리포트 생성
    # ════════════════════════════════════════════════════════
    categories = [
        {
            'name': '게이지 테스트',
            'icon': '🎯',
            'desc': '속도 변화 / 게이지 색 변경 / JPG 압축 아티팩트 허용 여부 검증',
            'cases': gauge_cases,
        },
        {
            'name': '팝업 테스트',
            'icon': '💬',
            'desc': '팝업 등장 / 팝업 종류 변경(warning→error) 감지',
            'cases': popup_cases,
        },
        {
            'name': '텔테일 테스트',
            'icon': '⚠️',
            'desc': '경고등 활성 상태 변화 감지 — ROI로 텔테일 표시줄 영역을 별도 엄격 검사',
            'cases': telltale_cases,
        },
    ]

    print('\n' + '━' * 58)
    print('HTML 리포트 생성 중...')
    report_path = OUT / 'report.html'
    report_path.write_text(build_html_report(categories), encoding='utf-8')
    print(f'\n완료: {report_path.resolve()}')
    print('\n브라우저로 열기:')
    print(f'  wslview "{report_path.resolve()}"')
    print(f'  또는 Windows 탐색기에서 파일 더블클릭\n')


if __name__ == '__main__':
    run()
