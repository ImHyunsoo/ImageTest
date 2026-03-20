"""
roi_picker.py — ROI 좌표 선택 도구

이미지 위에서 마우스 드래그로 ROI 사각형을 그리면
image_compare.py / demo.py 에 바로 붙여 쓸 수 있는 ROI 코드를 출력합니다.

실행:
  python roi_picker.py image.png
  python roi_picker.py image.jpg --scale 2   # 작은 이미지는 확대해서 표시

조작:
  마우스 드래그 : 사각형 그리기
  Enter / Space : 현재 ROI 확정 (여러 개 추가 가능)
  Backspace     : 마지막 ROI 취소
  Escape / Q    : 종료 (확정된 ROI 목록 출력)

필요 패키지:
  pip install pillow
  (tkinter 는 Python 표준 라이브러리에 포함)
"""
from __future__ import annotations

import argparse
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Optional

try:
    from PIL import Image, ImageTk
except ImportError:
    print('Pillow 가 필요합니다:  pip install pillow', file=sys.stderr)
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 색상 팔레트 (ROI 번호 순환)
# ─────────────────────────────────────────────────────────────────────────────
_COLORS = ['#ef4444', '#3b82f6', '#16a34a', '#f59e0b', '#8b5cf6',
           '#06b6d4', '#ec4899', '#84cc16']


def _color(i: int) -> str:
    return _COLORS[i % len(_COLORS)]


# ─────────────────────────────────────────────────────────────────────────────
# ROI Picker UI
# ─────────────────────────────────────────────────────────────────────────────

class ROIPicker:
    """
    tkinter 기반 ROI 좌표 선택기.

    사용자가 드래그로 사각형을 그리면 실제 이미지 좌표(scale 보정)를
    rois 리스트에 누적합니다.
    """

    def __init__(self, img_path: str, scale: float = 1.0):
        self.img_path = img_path
        self.scale    = scale
        self.rois: list[dict] = []   # 확정된 ROI 목록

        # 이미지 로드
        pil_img = Image.open(img_path).convert('RGB')
        self.orig_w, self.orig_h = pil_img.size
        disp_w = int(self.orig_w * scale)
        disp_h = int(self.orig_h * scale)
        pil_disp = pil_img.resize((disp_w, disp_h), Image.LANCZOS)

        # Tk 루트
        self.root = tk.Tk()
        self.root.title(f'ROI Picker — {img_path}  [{self.orig_w}×{self.orig_h}]')
        self.root.resizable(False, False)

        # 안내 레이블
        info = tk.Label(
            self.root,
            text=(
                '드래그: ROI 그리기  |  Enter/Space: 확정  |  '
                'Backspace: 취소  |  Esc/Q: 완료'
            ),
            bg='#1e293b', fg='#94a3b8', font=('Consolas', 10), pady=6,
        )
        info.pack(fill='x')

        # 캔버스
        self.canvas = tk.Canvas(
            self.root, width=disp_w, height=disp_h,
            cursor='crosshair', highlightthickness=0,
        )
        self.canvas.pack()
        self._tk_img = ImageTk.PhotoImage(pil_disp)
        self.canvas.create_image(0, 0, anchor='nw', image=self._tk_img)

        # 상태 레이블 (하단)
        self.status_var = tk.StringVar(value='이미지를 드래그해 ROI를 그리세요.')
        status_lbl = tk.Label(
            self.root, textvariable=self.status_var,
            bg='#0f172a', fg='#e2e8f0', font=('Consolas', 10), pady=5,
            anchor='w', padx=10,
        )
        status_lbl.pack(fill='x')

        # 드래그 상태
        self._drag_start: Optional[tuple[int, int]] = None
        self._rect_id: Optional[int] = None

        # 이벤트 바인딩
        self.canvas.bind('<ButtonPress-1>',   self._on_press)
        self.canvas.bind('<B1-Motion>',       self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Return>',     self._on_confirm)
        self.root.bind('<space>',      self._on_confirm)
        self.root.bind('<BackSpace>',  self._on_undo)
        self.root.bind('<Escape>',     self._on_quit)
        self.root.bind('<q>',          self._on_quit)
        self.root.bind('<Q>',          self._on_quit)

        # 현재 드래그 중인 임시 ROI
        self._pending: Optional[dict] = None

    # ── 드래그 이벤트 ─────────────────────────────────────────────────────────

    def _on_press(self, event):
        self._drag_start = (event.x, event.y)
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        color = _color(len(self.rois))
        self._rect_id = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=color, width=2, dash=(4, 4),
        )
        # 실제 좌표 계산
        rx, ry = int(min(x0, x1) / self.scale), int(min(y0, y1) / self.scale)
        rw, rh = int(abs(x1 - x0) / self.scale), int(abs(y1 - y0) / self.scale)
        self.status_var.set(f'드래그 중: x={rx}, y={ry}, width={rw}, height={rh}')
        self._pending = {'x': rx, 'y': ry, 'width': rw, 'height': rh}

    def _on_release(self, event):
        if self._drag_start and self._pending:
            p = self._pending
            if p['width'] > 2 and p['height'] > 2:
                self.status_var.set(
                    f'[{len(self.rois)+1}] x={p["x"]}, y={p["y"]}, '
                    f'width={p["width"]}, height={p["height"]} — '
                    f'Enter 로 확정 / 다시 드래그해 수정'
                )
            else:
                self._pending = None
                self.status_var.set('너무 작습니다. 다시 드래그하세요.')

    # ── 확정 / 취소 ───────────────────────────────────────────────────────────

    def _on_confirm(self, event=None):
        if self._pending is None:
            return
        p = self._pending
        # 이름 입력 다이얼로그
        name = _ask_string(self.root, f'ROI {len(self.rois)+1} 이름', '영역 이름을 입력하세요:')
        if name is None:  # 취소
            return
        name = name.strip() or f'ROI{len(self.rois)+1}'

        # 캔버스에 확정 표시
        color = _color(len(self.rois))
        x0d = int(p['x'] * self.scale)
        y0d = int(p['y'] * self.scale)
        x1d = x0d + int(p['width'] * self.scale)
        y1d = y0d + int(p['height'] * self.scale)
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None
        self.canvas.create_rectangle(x0d, y0d, x1d, y1d, outline=color, width=2)
        self.canvas.create_text(
            x0d + 4, y0d + 4, anchor='nw', text=f'{len(self.rois)+1}:{name}',
            fill=color, font=('Consolas', 9, 'bold'),
        )
        self.rois.append({**p, 'name': name})
        self._pending = None
        self.status_var.set(f'ROI {len(self.rois)}개 확정. 계속 그리거나 Esc 로 완료하세요.')

    def _on_undo(self, event=None):
        if self.rois:
            removed = self.rois.pop()
            self.status_var.set(f'마지막 ROI 취소: {removed["name"]}. 캔버스를 새로 그려주세요.')

    def _on_quit(self, event=None):
        self.root.quit()

    # ── 실행 진입점 ───────────────────────────────────────────────────────────

    def run(self) -> list[dict]:
        self.root.mainloop()
        self.root.destroy()
        return self.rois


# ─────────────────────────────────────────────────────────────────────────────
# 간단한 이름 입력 다이얼로그 (tkinter simpledialog 대체)
# ─────────────────────────────────────────────────────────────────────────────

def _ask_string(parent, title: str, prompt: str) -> Optional[str]:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.grab_set()

    tk.Label(dialog, text=prompt, padx=14, pady=10).pack()
    var = tk.StringVar()
    entry = tk.Entry(dialog, textvariable=var, width=32, font=('Consolas', 11))
    entry.pack(padx=14, pady=(0, 4))
    entry.focus_set()

    result: list[Optional[str]] = [None]

    def ok(_=None):
        result[0] = var.get()
        dialog.destroy()

    def cancel(_=None):
        dialog.destroy()

    tk.Button(dialog, text='확인', command=ok, width=10).pack(side='left',  padx=10, pady=8)
    tk.Button(dialog, text='취소', command=cancel, width=10).pack(side='right', padx=10, pady=8)
    entry.bind('<Return>', ok)
    entry.bind('<Escape>', cancel)
    parent.wait_window(dialog)
    return result[0]


# ─────────────────────────────────────────────────────────────────────────────
# 코드 생성 출력
# ─────────────────────────────────────────────────────────────────────────────

def _print_code(rois: list[dict], img_path: str):
    if not rois:
        print('ROI 가 없습니다.')
        return

    print('\n' + '─' * 60)
    print('# demo.py / image_compare.py 에 붙여 넣을 ROI 코드:')
    print('─' * 60)
    print()

    # Python ROI 객체 목록
    print('# ── Python (ROI 객체 목록) ──────────────────────────────')
    for r in rois:
        print(
            f'ROI(name={repr(r["name"])}, '
            f'x={r["x"]}, y={r["y"]}, '
            f'width={r["width"]}, height={r["height"]}, '
            f'strict=True),'
        )

    print()
    print('# ── YAML / JSON 설정 (tests.yaml) ───────────────────────')
    print(f'# baseline: {img_path}')
    print('# current:  screenshots/current.png')
    print('rois:')
    for r in rois:
        print(f'  - name:   {repr(r["name"])}')
        print(f'    x:      {r["x"]}')
        print(f'    y:      {r["y"]}')
        print(f'    width:  {r["width"]}')
        print(f'    height: {r["height"]}')
        print(f'    strict: true')

    print()
    print('# ── CLI (--roi 플래그) ──────────────────────────────────')
    for r in rois:
        print(
            f'--roi {r["x"]},{r["y"]},{r["width"]},{r["height"]},'
            f'{r["name"]}'
        )
    print('─' * 60)


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='이미지 클릭으로 ROI 좌표를 선택하는 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""예시:
  python roi_picker.py baseline.png
  python roi_picker.py screenshot.jpg --scale 2
        """,
    )
    parser.add_argument('image', help='ROI 를 정의할 이미지 파일 경로')
    parser.add_argument(
        '--scale', '-s', type=float, default=1.0,
        help='표시 배율 (기본 1.0 — 작은 이미지는 2~3 권장)',
    )
    args = parser.parse_args()

    print(f'이미지: {args.image}')
    print('조작: 드래그로 ROI 그리기 → Enter 로 확정 → Esc 로 종료')

    picker = ROIPicker(args.image, scale=args.scale)
    rois   = picker.run()
    _print_code(rois, args.image)


if __name__ == '__main__':
    main()
