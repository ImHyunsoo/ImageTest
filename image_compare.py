"""
image_compare.py — 이미지 비교 엔진

PNG/JPG 포맷에 따라 비교 전략을 자동으로 선택합니다.
  PNG: 무손실 → 엄격 비교 (SSIM ≥ 0.98, diff < 0.1%)
  JPG: 손실 압축 → 지각적 유사도 기반 (SSIM ≥ 0.95, diff < 3.0%)
  ROI(strict):  포맷에 맞는 엄격 기준 적용
                PNG strict — SSIM ≥ 0.98, diff < 0.1%  (픽셀 퍼펙트)
                JPG strict — SSIM ≥ 0.96, diff < 1.5%  (압축 아티팩트 허용)
  ROI(color):   Hue 색상 변화 별도 감지 (경고등 색상 전환 등)
                기본 임계값 20° — 이 이상 hue 차이 시 FAIL
  ROI(ocr):     baseline · current 양쪽을 OCR로 읽어 서로 비교
                baseline에서 읽은 값과 current에서 읽은 값이 다르면 FAIL
                (pytesseract 필요)
  Mask:         동적 UI 영역(시계·애니메이션) 비교 제외
                diff 이미지에서 파란 오버레이로 표시

CLI 사용:
  python image_compare.py baseline.png current.jpg
  python image_compare.py baseline.png current.jpg --diff out/diff.png
  python image_compare.py baseline.png current.jpg --roi 130,72,220,93,속도계,ocr
  python image_compare.py baseline.png current.jpg --roi 50,10,60,38,경고등,color
  python image_compare.py baseline.png current.jpg --mask 380,0,100,48,시계
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageOps
from scipy.ndimage import uniform_filter

try:
    import pytesseract
    _TESSERACT_OK = True
except ImportError:
    _TESSERACT_OK = False


# ─────────────────────────────────────────────────────────────────────────────
# Threshold 설정
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompareConfig:
    """모드별 비교 임계값 묶음"""
    mode: str          # 'png' or 'jpg'
    ssim_pass: float   # 이 이상이면 PASS 후보
    ssim_similar: float
    diff_pass: float   # diff % 이 미만이면 PASS 후보
    diff_similar: float
    pixel_tol: int     # 이 값 초과 변화만 "다른 픽셀"로 계산 (0–255)
    # strict ROI 전용 임계값 — 포맷에 맞게 조정
    roi_strict_ssim: float = 0.98
    roi_strict_diff: float = 0.1
    # color_check ROI 전용 — hue 차이가 이 값(도) 이상이면 색상 변화로 판정
    color_hue_thr: float = 20.0

    @classmethod
    def for_mode(cls, mode: str) -> CompareConfig:
        if mode == 'jpg':
            return cls(
                mode='jpg',
                ssim_pass=0.95,
                ssim_similar=0.90,
                diff_pass=3.0,
                diff_similar=8.0,
                pixel_tol=15,
                roi_strict_ssim=0.96,  # JPG 압축 아티팩트를 허용하되 UI 변화는 감지
                roi_strict_diff=1.5,
            )
        # PNG (기본)
        return cls(
            mode='png',
            ssim_pass=0.98,
            ssim_similar=0.95,
            diff_pass=0.1,
            diff_similar=0.5,
            pixel_tol=2,
            roi_strict_ssim=0.98,  # 픽셀 퍼펙트
            roi_strict_diff=0.1,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 모델
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ROI:
    """관심 영역 — 핵심 UI 부분을 별도 엄격하게 검사"""
    name: str
    x: int
    y: int
    width: int
    height: int
    strict: bool = True        # True = 포맷에 맞는 엄격 기준 적용
    color_check: bool = False  # True = Hue 색상 변화도 별도 감지 (경고등 색상 전환 등)
    ocr: bool = False          # True = baseline·current 양쪽 OCR 후 비교
    ocr_lang: str = 'num'      # 'num'=숫자전용, 'kor'=한국어, 'eng'=영어
    ocr_threshold: int = 80    # 전처리 이진화 임계값 (숫자=80, 컬러텍스트=160)


@dataclass
class Mask:
    """비교 제외 영역 — 시계·애니메이션 등 동적 UI"""
    name: str
    x: int
    y: int
    width: int
    height: int


@dataclass
class ROIResult:
    name: str
    ssim: float
    diff_pct: float
    passed: bool
    hue_diff: float = 0.0          # color_check=True 일 때 채워짐 (도 단위)
    color_failed: bool = False     # hue_diff 가 임계값 초과
    ocr_base: Optional[str] = None # ocr=True 일 때 baseline 에서 읽은 텍스트
    ocr_curr: Optional[str] = None # ocr=True 일 때 current 에서 읽은 텍스트
    ocr_failed: bool = False       # ocr_base != ocr_curr
    # 크롭/오버레이 시각화를 위해 ROI 원본 좌표 보존
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class CompareResult:
    status: str          # 'PASS' | 'SIMILAR_PASS' | 'FAIL'
    message: str
    mode: str
    ssim_score: float
    diff_pct: float
    diff_pixels: int
    total_pixels: int
    diff_image_path: Optional[str] = None
    roi_results: list[ROIResult] = field(default_factory=list)

    def print_summary(self):
        icon = {'PASS': '✅', 'SIMILAR_PASS': '⚠️', 'FAIL': '❌'}.get(self.status, '?')
        sep = '─' * 52
        print(f'\n{sep}')
        print(f'{icon}  {self.status}')
        print(f'   {self.message}')
        print(f'   모드  : {self.mode.upper()}')
        print(f'   SSIM  : {self.ssim_score:.4f}')
        print(f'   Diff  : {self.diff_pct:.3f}%  ({self.diff_pixels:,} / {self.total_pixels:,} px)')
        if self.diff_image_path:
            print(f'   Diff 이미지: {self.diff_image_path}')
        for r in self.roi_results:
            ok = '✅' if r.passed else '❌'
            extra = ''
            if r.hue_diff > 0:
                extra += f'  🎨 Hue={r.hue_diff:.1f}°'
                if r.color_failed:
                    extra += ' ❌색상변화'
            if r.ocr_base is not None or r.ocr_curr is not None:
                extra += f'  🔤 기준={repr(r.ocr_base)} 비교={repr(r.ocr_curr)}'
                if r.ocr_failed:
                    extra += ' ❌OCR불일치'
            print(f'   ROI [{r.name}] {ok}  SSIM={r.ssim:.4f}  diff={r.diff_pct:.3f}%{extra}')
        print(sep)


# ─────────────────────────────────────────────────────────────────────────────
# 핵심 알고리즘
# ─────────────────────────────────────────────────────────────────────────────

def _compute_ssim(arr1: np.ndarray, arr2: np.ndarray) -> float:
    """
    SSIM (Structural Similarity Index) 계산 — Wang et al. 2004 기준.

    grayscale 변환 후 11×11 sliding window로 국소 평균/분산/공분산을 구해
    구조적 유사도를 0~1 범위로 반환합니다.
    값이 1에 가까울수록 원본과 동일합니다.
    """
    def to_gray(a: np.ndarray) -> np.ndarray:
        # BT.601 luma 계수로 그레이스케일 변환 후 0~1 정규화
        r, g, b = a[:, :, 0].astype(np.float64), a[:, :, 1].astype(np.float64), a[:, :, 2].astype(np.float64)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0

    g1, g2 = to_gray(arr1), to_gray(arr2)
    K1, K2 = 0.01, 0.03
    C1, C2 = K1 ** 2, K2 ** 2   # 안정화 상수 (L=1.0 기준)
    win = 11

    mu1 = uniform_filter(g1, win)
    mu2 = uniform_filter(g2, win)
    mu1_sq, mu2_sq, mu12 = mu1 * mu1, mu2 * mu2, mu1 * mu2

    sig1_sq = np.maximum(uniform_filter(g1 * g1, win) - mu1_sq, 0)
    sig2_sq = np.maximum(uniform_filter(g2 * g2, win) - mu2_sq, 0)
    sig12   = uniform_filter(g1 * g2, win) - mu12

    num = (2 * mu12 + C1) * (2 * sig12 + C2)
    den = (mu1_sq + mu2_sq + C1) * (sig1_sq + sig2_sq + C2)
    return float((num / den).mean())


def _load(path: str, target_size: Optional[tuple] = None) -> np.ndarray:
    """이미지 로드 → RGB uint8 배열. 크기가 다르면 baseline 크기로 리사이즈."""
    img = Image.open(path).convert('RGB')
    if target_size and img.size != target_size:
        img = img.resize(target_size, Image.LANCZOS)
    return np.array(img)


def _diff_mask(arr1: np.ndarray, arr2: np.ndarray, tol: int) -> np.ndarray:
    """어느 채널이든 tol 초과 차이가 있는 픽셀의 boolean mask."""
    return (np.abs(arr1.astype(np.int16) - arr2.astype(np.int16)).max(axis=2) > tol)


def _save_diff_image(baseline: np.ndarray, mask: np.ndarray, out_path: str,
                     masked_regions: Optional[list] = None):
    """
    diff 이미지 저장.
    변경 없는 픽셀: 원본 그대로 (context 유지)
    변경된 픽셀:   빨간색으로 강조
    마스크 영역:   파란 오버레이 (비교 제외 표시)
    """
    vis = baseline.copy()
    vis[mask] = [255, 0, 0]
    for m in (masked_regions or []):
        region = vis[m.y:m.y + m.height, m.x:m.x + m.width].astype(np.float32)
        blue = np.array([0, 80, 200], dtype=np.float32)
        vis[m.y:m.y + m.height, m.x:m.x + m.width] = \
            (region * 0.5 + blue * 0.5).astype(np.uint8)
    Image.fromarray(vis).save(out_path)


def detect_mode(path1: str, path2: str) -> str:
    """파일 확장자로 비교 모드 결정. 둘 중 하나라도 JPG면 jpg 모드."""
    exts = {Path(path1).suffix.lower(), Path(path2).suffix.lower()}
    return 'jpg' if exts & {'.jpg', '.jpeg'} else 'png'


def _mean_hue_diff(arr1: np.ndarray, arr2: np.ndarray) -> float:
    """
    평균 Hue 차이 반환 (0~180°).

    RGB → HSV 변환 후, 채도가 있는 픽셀만 비교합니다.
    무채색 픽셀(채도 < 0.15)은 hue 값이 불안정하므로 제외합니다.
    반환값이 클수록 색상 차이가 큽니다 (예: 녹색→빨간색 ≈ 120°).
    """
    def to_hue_sat(a: np.ndarray):
        f = a.astype(np.float64) / 255.0
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        cmax = np.maximum(r, np.maximum(g, b))
        cmin = np.minimum(r, np.minimum(g, b))
        d = cmax - cmin
        h = np.zeros_like(r)
        mr = (cmax == r) & (d > 1e-6)
        mg = (cmax == g) & (d > 1e-6)
        mb = (cmax == b) & (d > 1e-6)
        h[mr] = (60.0 * ((g[mr] - b[mr]) / d[mr])) % 360.0
        h[mg] = 60.0 * ((b[mg] - r[mg]) / d[mg] + 2.0)
        h[mb] = 60.0 * ((r[mb] - g[mb]) / d[mb] + 4.0)
        s = np.where(cmax > 1e-6, d / cmax, 0.0)
        return h, s

    h1, s1 = to_hue_sat(arr1)
    h2, s2 = to_hue_sat(arr2)
    # 어느 쪽이든 채도가 있는 픽셀만 비교
    sat_mask = (s1 > 0.15) | (s2 > 0.15)
    if not sat_mask.any():
        return 0.0
    dh = np.abs(h1[sat_mask] - h2[sat_mask])
    dh = np.minimum(dh, 360.0 - dh)  # circular distance (hue는 0°=360° 같음)
    return float(dh.mean())


def _ocr_read(arr: np.ndarray, lang: str = 'num', threshold: int = 80) -> Optional[str]:
    """
    이미지 배열에서 텍스트를 OCR로 읽습니다.

    lang='num':
      전처리: 4배 upscale → grayscale → invert → threshold=80
      어두운 배경에 흰색/밝은 숫자 전용

    lang='kor' / 'kor+eng':
      전처리: 4배 upscale → R채널 추출 → threshold=80 → invert
      R채널(>80)이 텍스트를 포함 — 주황·빨강·흰색 텍스트 모두 대응.
      어두운 배경(R≈20)은 제외되고 텍스트(R>80)만 검정으로 추출됨.

    lang='eng': 기본 invert+threshold

    언어 데이터 미설치 시 None 반환 (판정 보류, FAIL로 처리하지 않음).
    pytesseract 미설치 시 None 반환.
    """
    if not _TESSERACT_OK:
        return None
    img = Image.fromarray(arr)
    big = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)

    if lang in ('kor', 'kor+eng'):
        # R채널 기반 전처리: 주황/빨강/흰색 텍스트를 어두운 배경에서 분리
        # R > 80 인 픽셀 = 텍스트, 나머지 = 배경(R≈20)
        r_channel = np.array(big)[:, :, 0]
        mask = np.where(r_channel > 80, 0, 255).astype(np.uint8)  # 텍스트=검정
        processed = Image.fromarray(mask)
        try:
            return pytesseract.image_to_string(
                processed, config=f'--psm 6 --oem 1 -l {lang}'
            ).strip()
        except Exception:
            return None  # tesseract-ocr-kor 미설치
    else:
        # 숫자/영어: grayscale invert + threshold
        inverted = ImageOps.invert(big.convert('L'))
        thresholded = np.where(np.array(inverted) > threshold, 255, 0).astype(np.uint8)
        processed = Image.fromarray(thresholded)
        if lang == 'num':
            text = pytesseract.image_to_string(
                processed, config='--psm 6 -c tessedit_char_whitelist=0123456789'
            ).strip()
            if not text:
                text = pytesseract.image_to_string(
                    processed, config='--psm 8 -c tessedit_char_whitelist=0123456789'
                ).strip()
            return text
        else:  # eng
            return pytesseract.image_to_string(processed, config='--psm 6').strip()


def _apply_masks(arr: np.ndarray, masks: list, reference: np.ndarray) -> np.ndarray:
    """
    마스크 영역을 reference(baseline) 픽셀로 대체합니다.

    마스크된 영역은 baseline과 동일해지므로 SSIM/diff 계산에서 제외됩니다.
    원본 배열은 수정하지 않고 복사본을 반환합니다.
    """
    if not masks:
        return arr
    result = arr.copy()
    for m in masks:
        result[m.y:m.y + m.height, m.x:m.x + m.width] = \
            reference[m.y:m.y + m.height, m.x:m.x + m.width]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 메인 비교기
# ─────────────────────────────────────────────────────────────────────────────

class ImageComparator:
    """
    PNG/JPG 이미지 비교기.

    사용 예:
        cmp = ImageComparator()
        result = cmp.compare('baseline.png', 'current.jpg', diff_output='diff.png')
        result.print_summary()
    """

    def compare(
        self,
        baseline_path: str,
        current_path: str,
        diff_output: Optional[str] = None,
        rois: Optional[list[ROI]] = None,
        masks: Optional[list[Mask]] = None,
    ) -> CompareResult:
        """
        두 이미지를 비교합니다.

        Args:
            baseline_path: 기준 이미지
            current_path:  비교 대상 이미지
            diff_output:   diff 이미지 저장 경로 (None이면 저장 안 함)
            rois:          핵심 영역 별도 검사 목록
            masks:         비교 제외 영역 (시계·애니메이션 등 동적 UI)

        Returns:
            CompareResult  (status, ssim_score, diff_pct, roi_results 등 포함)
        """
        mode = detect_mode(baseline_path, current_path)
        cfg = CompareConfig.for_mode(mode)

        arr1 = _load(baseline_path)
        arr2 = _load(current_path, target_size=(arr1.shape[1], arr1.shape[0]))

        # 마스크 영역을 baseline으로 대체 → 해당 영역은 비교에서 제외
        arr2_cmp = _apply_masks(arr2, masks or [], arr1)

        # ── 전체 이미지 비교 ──────────────────────────────────
        ssim_score  = _compute_ssim(arr1, arr2_cmp)
        mask        = _diff_mask(arr1, arr2_cmp, cfg.pixel_tol)
        diff_pixels = int(mask.sum())
        total_pixels = arr1.shape[0] * arr1.shape[1]
        diff_pct    = diff_pixels / total_pixels * 100

        if diff_output:
            _save_diff_image(arr1, mask, diff_output, masked_regions=masks)

        # ── ROI 별도 검사 ─────────────────────────────────────
        roi_results: list[ROIResult] = []
        roi_failed = False
        for roi in (rois or []):
            y0, y1 = roi.y, roi.y + roi.height
            x0, x1 = roi.x, roi.x + roi.width
            r1, r2 = arr1[y0:y1, x0:x1], arr2_cmp[y0:y1, x0:x1]

            # strict ROI: 포맷에 맞는 엄격 기준 사용 (JPG라도 PNG 기준 강요하지 않음)
            roi_tol      = cfg.pixel_tol
            roi_ssim_thr = cfg.roi_strict_ssim if roi.strict else cfg.ssim_pass
            roi_diff_thr = cfg.roi_strict_diff  if roi.strict else cfg.diff_pass

            # ROI가 너무 작으면 SSIM window 효과로 부정확해지므로 pixel diff만 사용
            if r1.shape[0] >= 22 and r1.shape[1] >= 22:
                roi_ssim = _compute_ssim(r1, r2)
            else:
                roi_ssim = 1.0 - float(_diff_mask(r1, r2, roi_tol).mean())

            r_mask  = _diff_mask(r1, r2, roi_tol)
            r_diff  = r_mask.sum() / (r1.shape[0] * r1.shape[1]) * 100

            # ── 색상 변화 감지 (color_check=True 인 ROI만) ───
            hue_diff     = 0.0
            color_failed = False
            if roi.color_check:
                r2_orig = arr2[y0:y1, x0:x1]
                hue_diff = _mean_hue_diff(r1, r2_orig)
                color_failed = hue_diff > cfg.color_hue_thr

            # ── OCR 텍스트 검증 (ocr=True 인 ROI만) ──
            # baseline 과 current 양쪽을 읽어 서로 비교
            ocr_base   = None
            ocr_curr   = None
            ocr_failed = False
            if roi.ocr:
                ocr_base = _ocr_read(arr1[y0:y1, x0:x1],
                                     lang=roi.ocr_lang, threshold=roi.ocr_threshold)
                ocr_curr = _ocr_read(arr2[y0:y1, x0:x1],
                                     lang=roi.ocr_lang, threshold=roi.ocr_threshold)
                if ocr_base is None or ocr_curr is None:
                    ocr_failed = False   # 언어 데이터 없음 → 판정 보류
                else:
                    ocr_failed = (ocr_base.strip() != ocr_curr.strip())

            r_passed = (roi_ssim >= roi_ssim_thr and r_diff < roi_diff_thr
                        and not color_failed and not ocr_failed)

            roi_results.append(ROIResult(
                name=roi.name,
                ssim=round(roi_ssim, 4),
                diff_pct=round(r_diff, 3),
                passed=r_passed,
                hue_diff=round(hue_diff, 1),
                color_failed=color_failed,
                ocr_base=ocr_base,
                ocr_curr=ocr_curr,
                ocr_failed=ocr_failed,
                x=roi.x, y=roi.y, width=roi.width, height=roi.height,
            ))
            if not r_passed:
                roi_failed = True

        # ── 최종 판정 ─────────────────────────────────────────
        if roi_failed:
            status = 'FAIL'
            msg = f'핵심 영역(ROI) 변경 감지 (전체 SSIM={ssim_score:.4f}, diff={diff_pct:.3f}%)'
        elif ssim_score >= cfg.ssim_pass and diff_pct < cfg.diff_pass:
            status = 'PASS'
            msg = f'이미지 동일 (SSIM={ssim_score:.4f}, diff={diff_pct:.3f}%)'
        elif ssim_score >= cfg.ssim_similar and diff_pct < cfg.diff_similar:
            status = 'SIMILAR_PASS'
            msg = f'시각적으로 유사 — 압축/렌더링 차이 수준 (SSIM={ssim_score:.4f}, diff={diff_pct:.3f}%)'
        else:
            status = 'FAIL'
            msg = f'이미지 불일치 (SSIM={ssim_score:.4f}, diff={diff_pct:.3f}%)'

        return CompareResult(
            status=status, message=msg, mode=mode,
            ssim_score=ssim_score, diff_pct=diff_pct,
            diff_pixels=diff_pixels, total_pixels=total_pixels,
            diff_image_path=diff_output,
            roi_results=roi_results,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_roi(s: str) -> ROI:
    """ROI 파싱. 형식: x,y,w,h,이름[,color][,ocr]"""
    parts = s.split(',', 5)
    if len(parts) < 5:
        raise argparse.ArgumentTypeError(
            'ROI 형식: x,y,w,h,이름[,color][,ocr]\n'
            '  예) 130,72,220,93,속도계,ocr\n'
            '      50,10,60,38,경고등,color')
    x, y, w, h = (int(p) for p in parts[:4])
    color_check = False
    ocr         = False
    for opt in parts[5:]:
        opt = opt.strip().lower()
        if opt == 'color':
            color_check = True
        elif opt == 'ocr':
            ocr = True
    return ROI(name=parts[4], x=x, y=y, width=w, height=h,
               color_check=color_check, ocr=ocr)


def _parse_mask(s: str) -> Mask:
    """Mask 파싱. 형식: x,y,w,h,이름"""
    parts = s.split(',', 4)
    if len(parts) != 5:
        raise argparse.ArgumentTypeError(
            'Mask 형식: x,y,w,h,이름  (예: 380,0,100,48,시계)')
    x, y, w, h = (int(p) for p in parts[:4])
    return Mask(name=parts[4], x=x, y=y, width=w, height=h)


def main():
    parser = argparse.ArgumentParser(
        description='이미지 비교 도구 — PNG strict / JPG perceptual',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""예시:
  python image_compare.py baseline.png current.jpg
  python image_compare.py baseline.png current.jpg --diff diff.png
  python image_compare.py baseline.png current.jpg --roi 150,110,100,80,속도계
  python image_compare.py baseline.png current.jpg --roi 50,10,60,38,경고등,color
  python image_compare.py baseline.png current.jpg --mask 380,0,100,48,시계
  python image_compare.py b.png c.jpg --roi 150,110,100,80,속도계 --mask 380,0,100,48,시계
        """,
    )
    parser.add_argument('baseline', help='기준 이미지')
    parser.add_argument('current', help='비교 이미지')
    parser.add_argument('--diff', '-d', default=None, metavar='PATH', help='diff 이미지 저장 경로')
    parser.add_argument('--roi', '-r', type=_parse_roi, action='append', default=[],
                        metavar='x,y,w,h,name[,color]', help='관심 영역 (여러 번 지정 가능, ,color 접미사로 색상 감지 활성화)')
    parser.add_argument('--mask', '-m', type=_parse_mask, action='append', default=[],
                        metavar='x,y,w,h,name', help='비교 제외 영역 (여러 번 지정 가능)')
    args = parser.parse_args()

    result = ImageComparator().compare(
        args.baseline, args.current,
        diff_output=args.diff,
        rois=args.roi,
        masks=args.mask,
    )
    result.print_summary()
    sys.exit(0 if result.status != 'FAIL' else 1)


if __name__ == '__main__':
    main()
