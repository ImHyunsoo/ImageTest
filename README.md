# 이미지 비교 테스트 엔진 (PNG / JPG 대응)

## 1. 왜 만들었나 — 배경

자동화 테스트에서 화면 스크린샷을 비교할 때, **PNG는 잘 되는데 JPG는 자꾸 틀렸다고 나오는 문제**가 있습니다.

### 원인

| 포맷 | 압축 방식 | 저장 결과 |
|------|----------|----------|
| PNG  | 무손실   | 저장 전후 픽셀이 완전히 동일 |
| JPG  | 손실     | 저장할 때마다 픽셀이 조금씩 달라짐 |

```
같은 이미지를 JPG로 두 번 저장하면:

baseline.jpg  →  R:255 G:120 B:0
current.jpg   →  R:252 G:118 B:3   ← 사람 눈엔 똑같아 보이지만 픽셀값이 다름
```

PNG처럼 "픽셀이 완전히 같아야 통과" 기준을 JPG에 그대로 적용하면,
**변경이 없어도 FAIL이 계속 발생**합니다.

---

## 2. 무엇을 하는 프로젝트인가

JPG 이미지도 안정적으로 비교할 수 있는 **이미지 비교 엔진**과,
차량 클러스터 UI를 시뮬레이션한 **데모 테스트**를 제공합니다.

### 핵심 기능

#### ① 포맷 자동 감지 — 기준을 다르게 적용
```
PNG  → 엄격 비교  (SSIM ≥ 0.98,  diff < 0.1%)
JPG  → 지각 비교  (SSIM ≥ 0.95,  diff < 3.0%)
```
JPG는 압축 특성상 완전 일치 비교 대신 **시각적 유사도(SSIM)** 기준으로 판정합니다.

> **SSIM(Structural Similarity Index)** : 사람 눈 기준으로 이미지가 얼마나 비슷한지 측정하는 지표.
> 1.0 = 완전히 동일, 0 = 전혀 다름

#### ② ROI(관심 영역) 별도 검사
게이지 숫자, 팝업, 텔테일처럼 **작지만 중요한 영역**은
전체 이미지와 별도로 더 엄격하게 검사합니다.

```
전체 이미지: JPG 기준 적용 (관대)
ROI 영역:   PNG 기준 적용 (엄격) ← 포맷 무관
```

#### ③ 3단계 판정
| 판정 | 의미 |
|------|------|
| ✅ PASS | 동일하거나 허용 범위 내 차이 |
| ⚠️ SIMILAR PASS | 시각적으로 유사하지만 PASS 기준 약간 초과 (압축 아티팩트 등) |
| ❌ FAIL | 의미 있는 변경 감지 |

#### ④ Diff 이미지 자동 생성
변경된 픽셀을 빨간색으로 표시한 이미지를 생성합니다.

#### ⑤ HTML 리포트
카테고리별(게이지 / 팝업 / 텔테일)로 결과를 정리한 HTML 리포트를 생성합니다.

---

## 3. 파일 구조

```
ImageTest/
│
├── image_compare.py   ← 비교 엔진 (핵심 로직)
├── demo.py            ← 데모 실행 + HTML 리포트 생성
├── requirements.txt   ← Python 패키지 목록
├── run.sh             ← 한 번에 설치 + 실행하는 스크립트
│
└── demo_output/       ← 데모 실행 시 자동 생성되는 폴더
    ├── report.html    ← 결과 리포트 (브라우저로 열기)
    ├── g1_base.png    ← 게이지 테스트 이미지들
    ├── p1_base.jpg    ← 팝업 테스트 이미지들
    ├── t1_base.jpg    ← 텔테일 테스트 이미지들
    └── *_diff.png     ← 변경 영역 표시 이미지들
```

---

## 4. 설치 방법

### 사전 조건
- Python 3.9 이상

### 패키지 설치

```bash
pip install -r requirements.txt
```

설치되는 패키지:
| 패키지 | 용도 |
|--------|------|
| Pillow | 이미지 로드, 저장, 그리기 |
| numpy  | 픽셀 배열 연산 |
| scipy  | SSIM 계산용 슬라이딩 윈도우 |

---

## 5. 실행 방법

### 방법 A — 데모 한 번에 실행 (추천)

```bash
bash run.sh
```

자동으로:
1. 패키지 설치 확인
2. 데모 이미지 생성 (게이지 / 팝업 / 텔테일 시나리오)
3. `demo_output/report.html` 생성
4. 브라우저로 열기 시도

### 방법 B — 데모만 실행

```bash
python demo.py
```

실행하면 콘솔에 각 케이스 결과가 출력되고 `demo_output/report.html`이 생성됩니다.

### 방법 C — CLI로 직접 이미지 비교

```bash
# 기본 비교
python image_compare.py baseline.png current.jpg

# diff 이미지 저장
python image_compare.py baseline.png current.jpg --diff diff.png

# ROI(관심 영역) 지정
python image_compare.py baseline.png current.jpg \
    --diff diff.png \
    --roi 150,108,100,80,속도계숫자

# ROI 여러 개 지정
python image_compare.py baseline.png current.jpg \
    --roi 150,108,100,80,속도계 \
    --roi 0,250,400,48,텔테일
```

ROI 형식: `x좌표,y좌표,너비,높이,이름`

---

## 6. Python 코드에서 직접 사용

```python
from image_compare import ImageComparator, ROI

cmp = ImageComparator()

# 기본 비교
result = cmp.compare('baseline.png', 'current.jpg')
print(result.status)      # 'PASS' / 'SIMILAR_PASS' / 'FAIL'
print(result.ssim_score)  # 0~1 사이 실수
print(result.diff_pct)    # 달라진 픽셀 비율 (%)

# diff 이미지 저장 포함
result = cmp.compare(
    'baseline.png',
    'current.jpg',
    diff_output='diff.png',
)

# ROI 검사 포함
speed_roi    = ROI(name='속도계',  x=150, y=108, width=100, height=80)
telltale_roi = ROI(name='텔테일', x=0,   y=250, width=400, height=48)

result = cmp.compare(
    'baseline.png',
    'current.jpg',
    diff_output='diff.png',
    rois=[speed_roi, telltale_roi],
)

# ROI 결과 확인
for roi_result in result.roi_results:
    print(roi_result.name, roi_result.passed, roi_result.ssim)
```

---

## 7. 데모 테스트 케이스 목록

데모는 차량 클러스터 UI 이미지를 생성해서 15가지 시나리오를 검증합니다.

### 🎯 게이지 테스트 (5케이스)

| 케이스 | 설명 | 기대 결과 |
|--------|------|----------|
| G-1 | PNG 완전히 동일한 이미지 | ✅ PASS |
| G-2 | PNG 속도 변화 (80 → 120) + 게이지 색 변경 | ❌ FAIL |
| G-3 | JPG 동일 내용, 압축률만 다름 (Q=95 vs Q=70) | ✅ PASS |
| G-4 | JPG 미세 속도 변화 (80 → 90) + ROI 검사 | ❌ FAIL |
| G-5 | JPG 극단 압축 차이 (Q=95 vs Q=40) | ⚠️ SIMILAR PASS |

> **G-3 핵심 포인트**: 동일 이미지를 다른 압축률로 저장해도 JPG 모드에서는 PASS.
> PNG 기준이었다면 압축 아티팩트로 FAIL이 날 수 있는 케이스입니다.

### 💬 팝업 테스트 (5케이스)

| 케이스 | 설명 | 기대 결과 |
|--------|------|----------|
| P-1 | JPG 팝업 없음, 동일 | ✅ PASS |
| P-2 | JPG 팝업 없음 → warning 팝업 등장 | ❌ FAIL |
| P-3 | JPG warning 팝업 → error 팝업 (종류 변경) | ❌ FAIL |
| P-4 | JPG 동일 팝업 켜진 상태에서 비교 | ✅ PASS |
| P-5 | JPG 팝업 텍스트만 변경 (종류는 동일) | ❌ FAIL |

> **P-4 핵심 포인트**: 팝업이 켜진 상태가 baseline이면 current도 같으면 PASS.
> 팝업이 켜졌다고 무조건 FAIL이 되면 안 됩니다.

### ⚠️ 텔테일 테스트 (5케이스)

| 케이스 | 설명 | 기대 결과 |
|--------|------|----------|
| T-1 | JPG 텔테일 모두 off, 동일 | ✅ PASS |
| T-2 | JPG 텔테일 없음 → ENG + OIL 켜짐 | ❌ FAIL |
| T-3 | JPG 텔테일 없음 → BAT + DOOR + TEMP + SBT 켜짐 | ❌ FAIL |
| T-4 | JPG 동일 텔테일 켜진 상태에서 비교 | ✅ PASS |
| T-5 | JPG 텔테일 패턴 교체 (ENG → FUEL, 켜진 수는 동일) | ❌ FAIL |

> **T-5 핵심 포인트**: 켜진 경고등 수가 같아도 종류가 다르면 FAIL.
> "개수"가 아니라 "어떤 경고등인지"를 감지합니다.

---

## 8. 알고리즘 흐름

```
[입력: baseline 이미지, current 이미지]
         │
         ▼
[포맷 감지] — .jpg/.jpeg 포함 → JPG 모드 / 아니면 PNG 모드
         │
         ▼
[전처리] — 두 이미지 크기 통일 (LANCZOS 리사이즈)
         │
         ├──────────────────────┐
         ▼                      ▼
[전체 이미지 비교]          [ROI 별도 비교] (지정한 경우)
  • SSIM 계산                 • 각 ROI 잘라서 동일하게 비교
  • 픽셀 diff % 계산           • 항상 PNG 엄격 기준 적용
  • diff 이미지 저장
         │                      │
         └──────────┬───────────┘
                    ▼
              [최종 판정]
         ROI 실패 → FAIL
         SSIM ≥ 기준 AND diff < 기준 → PASS
         그 아래 범위 → SIMILAR PASS
         그 외 → FAIL
                    │
                    ▼
              [결과 반환]
         status / ssim_score / diff_pct
         diff_image_path / roi_results
```

---

## 9. 비교 기준 요약

| 모드 | PASS 기준 | SIMILAR PASS 기준 | 픽셀 허용 오차 |
|------|----------|--------------------|--------------|
| PNG  | SSIM ≥ 0.98, diff < 0.1% | SSIM ≥ 0.95, diff < 0.5% | ±2 |
| JPG  | SSIM ≥ 0.95, diff < 3.0% | SSIM ≥ 0.90, diff < 8.0% | ±15 |
| ROI  | 항상 PNG 기준 적용 | — | ±2 |

---

## 10. 고객 설명용 한 줄 요약

> "PNG는 무손실이라 픽셀 완전 일치 비교가 가능하지만, JPG는 손실 압축 특성상 같은 이미지라도 저장할 때마다 픽셀이 달라집니다.
> 그래서 JPG는 시각적 유사도(SSIM) 기반으로 비교하고, 속도 숫자·경고등·팝업 같은 핵심 영역은 포맷에 관계없이 별도로 엄격하게 검사합니다."
