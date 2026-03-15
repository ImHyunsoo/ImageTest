"""
image_compare.py — 이미지 비교 엔진

PNG/JPG 포맷에 따라 비교 전략을 자동으로 선택합니다.
  PNG: 무손실 → 엄격 비교 (SSIM ≥ 0.98, diff < 0.1%)
  JPG: 손실 압축 → 지각적 유사도 기반 (SSIM ≥ 0.95, diff < 3.0%)
  ROI: 핵심 UI 영역은 포맷에 관계없이 PNG 엄격 기준으로 별도 검사

CLI 사용:
  python image_compare.py baseline.png current.jpg
  python image_compare.py baseline.png current.jpg --diff out/diff.png
  python image_compare.py baseline.png current.jpg --roi 150,110,100,80,속도계
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter


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
            )
        # PNG (기본)
        return cls(
            mode='png',
            ssim_pass=0.98,
            ssim_similar=0.95,
            diff_pass=0.1,
            diff_similar=0.5,
            pixel_tol=2,
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
    strict: bool = True  # True = 포맷 무관 PNG 엄격 기준 적용


@dataclass
class ROIResult:
    name: str
    ssim: float
    diff_pct: float
    passed: bool


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
            print(f'   ROI [{r.name}] {ok}  SSIM={r.ssim:.4f}  diff={r.diff_pct:.3f}%')
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


def _save_diff_image(baseline: np.ndarray, mask: np.ndarray, out_path: str):
    """
    diff 이미지 저장.
    변경 없는 픽셀: 원본 그대로 (context 유지)
    변경된 픽셀:   빨간색으로 강조
    """
    vis = baseline.copy()
    vis[mask] = [255, 0, 0]
    Image.fromarray(vis).save(out_path)


def detect_mode(path1: str, path2: str) -> str:
    """파일 확장자로 비교 모드 결정. 둘 중 하나라도 JPG면 jpg 모드."""
    exts = {Path(path1).suffix.lower(), Path(path2).suffix.lower()}
    return 'jpg' if exts & {'.jpg', '.jpeg'} else 'png'


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
    ) -> CompareResult:
        """
        두 이미지를 비교합니다.

        Args:
            baseline_path: 기준 이미지
            current_path:  비교 대상 이미지
            diff_output:   diff 이미지 저장 경로 (None이면 저장 안 함)
            rois:          핵심 영역 별도 검사 목록

        Returns:
            CompareResult  (status, ssim_score, diff_pct, roi_results 등 포함)
        """
        mode = detect_mode(baseline_path, current_path)
        cfg = CompareConfig.for_mode(mode)

        arr1 = _load(baseline_path)
        arr2 = _load(current_path, target_size=(arr1.shape[1], arr1.shape[0]))

        # ── 전체 이미지 비교 ──────────────────────────────────
        ssim_score  = _compute_ssim(arr1, arr2)
        mask        = _diff_mask(arr1, arr2, cfg.pixel_tol)
        diff_pixels = int(mask.sum())
        total_pixels = arr1.shape[0] * arr1.shape[1]
        diff_pct    = diff_pixels / total_pixels * 100

        if diff_output:
            _save_diff_image(arr1, mask, diff_output)

        # ── ROI 별도 검사 ─────────────────────────────────────
        roi_results: list[ROIResult] = []
        roi_failed = False
        for roi in (rois or []):
            y0, y1 = roi.y, roi.y + roi.height
            x0, x1 = roi.x, roi.x + roi.width
            r1, r2 = arr1[y0:y1, x0:x1], arr2[y0:y1, x0:x1]

            roi_cfg = CompareConfig.for_mode('png') if roi.strict else cfg

            # ROI가 너무 작으면 SSIM window 효과로 부정확해지므로 pixel diff만 사용
            if r1.shape[0] >= 22 and r1.shape[1] >= 22:
                roi_ssim = _compute_ssim(r1, r2)
            else:
                roi_ssim = 1.0 - float(_diff_mask(r1, r2, roi_cfg.pixel_tol).mean())

            r_mask    = _diff_mask(r1, r2, roi_cfg.pixel_tol)
            r_diff    = r_mask.sum() / (r1.shape[0] * r1.shape[1]) * 100
            r_passed  = roi_ssim >= roi_cfg.ssim_pass and r_diff < roi_cfg.diff_pass

            roi_results.append(ROIResult(
                name=roi.name,
                ssim=round(roi_ssim, 4),
                diff_pct=round(r_diff, 3),
                passed=r_passed,
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
    parts = s.split(',', 4)
    if len(parts) != 5:
        raise argparse.ArgumentTypeError('ROI 형식: x,y,width,height,이름  (예: 150,110,100,80,속도계)')
    x, y, w, h = (int(p) for p in parts[:4])
    return ROI(name=parts[4], x=x, y=y, width=w, height=h)


def main():
    parser = argparse.ArgumentParser(
        description='이미지 비교 도구 — PNG strict / JPG perceptual',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""예시:
  python image_compare.py baseline.png current.jpg
  python image_compare.py baseline.png current.jpg --diff diff.png
  python image_compare.py baseline.png current.jpg --roi 150,110,100,80,속도계
  python image_compare.py b.png c.jpg --roi 150,110,100,80,속도계 --roi 50,230,40,30,경고등
        """,
    )
    parser.add_argument('baseline', help='기준 이미지')
    parser.add_argument('current', help='비교 이미지')
    parser.add_argument('--diff', '-d', default=None, metavar='PATH', help='diff 이미지 저장 경로')
    parser.add_argument('--roi', '-r', type=_parse_roi, action='append', default=[],
                        metavar='x,y,w,h,name', help='관심 영역 (여러 번 지정 가능)')
    args = parser.parse_args()

    result = ImageComparator().compare(
        args.baseline, args.current,
        diff_output=args.diff,
        rois=args.roi,
    )
    result.print_summary()
    sys.exit(0 if result.status != 'FAIL' else 1)


if __name__ == '__main__':
    main()
