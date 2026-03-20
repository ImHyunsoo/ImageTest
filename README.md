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
차량 클러스터 UI(Tesla / Hyundai / Kia)를 시뮬레이션한 **데모 테스트**를 제공합니다.

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
게이지 숫자, 팝업, 텔테일처럼 **작지만 중요한 영역**은 전체 이미지와 별도로 더 엄격하게 검사합니다.

```
전체 이미지: JPG 기준 적용 (관대)
ROI 영역:   포맷에 맞는 엄격 기준 적용
```

#### ③ 색상 변화 감지 (HSV Hue diff)
경고등 색상 전환(녹색 → 주황/빨강 등)처럼 **컬러 변화**를 Hue 각도 차이로 감지합니다.

```python
ROI(name='엔진경고등', x=50, y=10, width=60, height=38, color_check=True)
# Hue 차이 ≥ 20° 이면 색상 변화로 FAIL
```

#### ④ OCR 텍스트 검증
숫자나 텍스트가 있는 영역을 **OCR로 직접 읽어 기대값과 비교**합니다.
SSIM만으로는 놓칠 수 있는 미세한 수치 변화도 정확하게 감지합니다.

```python
# 숫자 검증 (속도, 배터리 %, 주행 거리 등)
ROI(name='속도(OCR)', x=145, y=70, width=195, height=95, ocr_expected='80')

# 한국어 텍스트 검증 (팝업 메시지 등)
ROI(name='팝업텍스트(OCR)', x=56, y=220, width=370, height=35,
    ocr_lang='kor', ocr_threshold=160, ocr_expected='오일 교환 필요',
    ocr_match='contains')
```

| `ocr_lang` | 용도 | 필요 패키지 |
|------------|------|------------|
| `'num'` (기본) | 숫자 전용 (0-9 whitelist) | tesseract-ocr |
| `'kor'` | 한국어 | tesseract-ocr-kor |
| `'eng'` | 영어 | tesseract-ocr |

| `ocr_match` | 동작 |
|-------------|------|
| `'exact'` (기본) | 완전 일치 |
| `'contains'` | 기대값이 OCR 결과에 포함되면 PASS |

> 언어 데이터 미설치 시 OCR 결과는 `None`으로 표시되며, 판정에서 제외(FAIL로 처리 안 함)됩니다.

#### ⑤ Mask — 동적 UI 영역 제외
시계, 애니메이션처럼 **항상 바뀌는 영역**을 비교에서 제외합니다.

```python
Mask(name='시계', x=380, y=0, width=100, height=48)
```

diff 이미지에서 마스크 영역은 파란 오버레이로 표시됩니다.

#### ⑥ 3단계 판정
| 판정 | 의미 |
|------|------|
| ✅ PASS | 동일하거나 허용 범위 내 차이 |
| ⚠️ SIMILAR PASS | 시각적으로 유사하지만 PASS 기준 약간 초과 (압축 아티팩트 등) |
| ❌ FAIL | 의미 있는 변경 감지 |

#### ⑦ HTML 리포트
- **브랜드 탭 필터링**: Tesla / Hyundai / Kia 탭으로 전환
- **ROI 테이블**: SSIM / Diff / Hue / OCR 결과 한눈에 확인
- **크롭 썸네일**: ROI 영역을 확대한 before/after 이미지
- **ROI 오버레이**: baseline / current 이미지 위에 ROI 박스 시각화

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
    ├── tesla/         ← Tesla 테스트 이미지 + diff
    ├── hyundai/       ← Hyundai 테스트 이미지 + diff
    └── kia/           ← Kia 테스트 이미지 + diff
```

---

## 4. 설치 방법

### 사전 조건
- Python 3.9 이상
- tesseract-ocr (OCR 기능 사용 시)

### Python 패키지 설치

```bash
pip install -r requirements.txt
```

설치되는 패키지:
| 패키지 | 용도 |
|--------|------|
| Pillow | 이미지 로드, 저장, 그리기 |
| numpy  | 픽셀 배열 연산 |
| scipy  | SSIM 계산용 슬라이딩 윈도우 |
| pytesseract | OCR 텍스트 인식 |

### Tesseract 설치 (OCR 기능)

```bash
# 기본 (숫자·영어 OCR)
sudo apt-get install tesseract-ocr

# 한국어 OCR 추가 (팝업 텍스트 검증)
sudo apt-get install tesseract-ocr-kor
```

---

## 5. 실행 방법

### 방법 A — 데모 한 번에 실행 (추천)

```bash
bash run.sh
```

### 방법 B — 특정 브랜드만 실행

```bash
python demo.py --brand tesla    # Tesla만
python demo.py --brand hyundai  # Hyundai만
python demo.py --brand kia      # Kia만
python demo.py --brand all      # 전체 (기본값)
```

실행하면 콘솔에 각 케이스 결과가 출력되고 `demo_output/report.html`이 생성됩니다.

### 방법 C — CLI로 직접 이미지 비교

```bash
# 기본 비교
python image_compare.py baseline.png current.jpg

# diff 이미지 저장
python image_compare.py baseline.png current.jpg --diff diff.png

# ROI 지정 (속도 숫자 OCR 검증)
python image_compare.py baseline.png current.jpg \
    --roi 145,70,195,95,속도계,ocr=80

# ROI 여러 개 + 색상 감지 + 마스크
python image_compare.py baseline.png current.jpg \
    --roi 150,108,100,80,속도계 \
    --roi 50,10,60,38,경고등,color \
    --mask 380,0,100,48,시계
```

ROI 형식: `x,y,너비,높이,이름[,color][,ocr=기대값]`

---

## 6. Python 코드에서 직접 사용

```python
from image_compare import ImageComparator, ROI, Mask

cmp = ImageComparator()

# 기본 비교
result = cmp.compare('baseline.png', 'current.jpg')
print(result.status)      # 'PASS' / 'SIMILAR_PASS' / 'FAIL'
print(result.ssim_score)  # 0~1 사이 실수
print(result.diff_pct)    # 달라진 픽셀 비율 (%)

# ROI + OCR + 색상 감지 + 마스크 조합
result = cmp.compare(
    'baseline.png',
    'current.jpg',
    diff_output='diff.png',
    rois=[
        ROI(name='속도(OCR)',   x=145, y=70,  width=195, height=95,
            ocr_expected='80'),
        ROI(name='경고등',      x=50,  y=10,  width=60,  height=38,
            color_check=True),
        ROI(name='팝업텍스트', x=56,  y=220, width=370, height=35,
            ocr_lang='kor', ocr_threshold=160,
            ocr_expected='오일 교환 필요', ocr_match='contains'),
    ],
    masks=[
        Mask(name='시계', x=380, y=0, width=100, height=48),
    ],
)

# ROI 결과 확인
for roi_result in result.roi_results:
    print(roi_result.name, roi_result.passed)
    if roi_result.ocr_text is not None:
        print(f'  OCR: {roi_result.ocr_text!r} (기대: {roi_result.ocr_expected!r})')
```

---

## 7. 데모 테스트 케이스 목록

데모는 Tesla / Hyundai / Kia 클러스터 UI를 생성해서 브랜드별 17가지 시나리오를 검증합니다.
모든 테스트에 **속도 OCR 검증**이 포함되며, 팝업 테스트에는 **한국어 팝업 텍스트 OCR**도 추가됩니다.

### 🎯 게이지 테스트 (7케이스)

| 케이스 | 설명 | 기대 결과 | OCR |
|--------|------|----------|-----|
| G-1 | PNG 완전히 동일한 이미지 | ✅ PASS | 속도=80 확인 |
| G-2 | PNG 속도 변화 (80 → 120) | ❌ FAIL | 속도 불일치 감지 |
| G-3 | JPG 동일 내용, 압축률만 다름 (Q=95 vs Q=70) | ✅ PASS | 압축 후에도 속도=60 인식 |
| G-4 | JPG 미세 속도 변화 (80 → 90) | ❌ FAIL | ROI + OCR 모두 감지 |
| G-5 | JPG 극단 압축 차이 (Q=95 vs Q=20) | ⚠️ SIMILAR PASS | ROI·OCR 검사 없음 (포맷 허용 오차 전용) |
| G-6 | JPG OCR 속도 검증 — 동일 (80 → 80) | ✅ PASS | OCR PASS |
| G-7 | JPG OCR 속도 검증 — 변경 (80 → 60) | ❌ FAIL | OCR FAIL |

> **G-4 핵심 포인트**: 전체 SSIM은 0.98로 높지만 속도 ROI와 OCR이 80≠90을 잡아냄.

### 💬 팝업 테스트 (5케이스)

| 케이스 | 설명 | 기대 결과 | OCR |
|--------|------|----------|-----|
| P-1 | JPG 팝업 없음, 동일 | ✅ PASS | 팝업 없음 확인 |
| P-2 | JPG 팝업 없음 → warning 팝업 등장 | ❌ FAIL | 팝업 텍스트 내용 확인 |
| P-3 | JPG warning → error 팝업 (종류 변경) | ❌ FAIL | 변경된 텍스트 확인 |
| P-4 | JPG 동일 팝업 켜진 상태에서 비교 | ✅ PASS | 팝업 텍스트 동일 확인 |
| P-5 | JPG 팝업 텍스트만 변경 (종류는 동일, 오일 → 타이어) | ❌ FAIL | **OCR이 핵심 — SSIM은 구조 유사로 놓칠 수 있음** |

> **P-5 핵심 포인트**: 팝업 타입(warning)과 레이아웃이 같아서 SSIM 단독으로는 감지가 어렵지만,
> OCR이 "오일 교환 필요" ≠ "타이어 공기압 부족"을 정확히 잡아냄.

### ⚠️ 텔테일 테스트 (5케이스)

| 케이스 | 설명 | 기대 결과 | OCR |
|--------|------|----------|-----|
| T-1 | JPG 텔테일 모두 off, 동일 | ✅ PASS | 속도=80 확인 |
| T-2 | JPG 텔테일 없음 → ENG + OIL 켜짐 | ❌ FAIL | 속도=80 확인 |
| T-3 | JPG 텔테일 없음 → BAT + DOOR + TEMP + SBT 켜짐 | ❌ FAIL | 속도=80 확인 |
| T-4 | JPG 동일 텔테일 켜진 상태에서 비교 | ✅ PASS | 속도=80 확인 |
| T-5 | JPG 텔테일 패턴 교체 (ENG → FUEL, 켜진 수는 동일) | ❌ FAIL | 속도=80 확인 |

> **T-5 핵심 포인트**: 켜진 경고등 수가 같아도 종류가 다르면 FAIL.

---

## 8. 알고리즘 흐름

```
[입력: baseline 이미지, current 이미지]
         │
         ▼
[포맷 감지] — .jpg/.jpeg 포함 → JPG 모드 / 아니면 PNG 모드
         │
         ▼
[전처리] — 두 이미지 크기 통일 + Mask 영역을 baseline으로 대체
         │
         ├──────────────────────┐
         ▼                      ▼
[전체 이미지 비교]          [ROI 별도 검사] (지정한 경우)
  • SSIM 계산                 각 ROI마다:
  • 픽셀 diff % 계산           • SSIM + diff 계산 (포맷 엄격 기준)
  • diff 이미지 저장           • color_check → HSV Hue diff
                               • ocr_expected → OCR 텍스트 읽기 + 비교
         │                      │
         └──────────┬───────────┘
                    ▼
              [최종 판정]
         ROI 실패 (SSIM·diff·색상·OCR 중 하나라도) → FAIL
         SSIM ≥ 기준 AND diff < 기준 → PASS
         그 아래 범위 → SIMILAR PASS
         그 외 → FAIL
```

---

## 9. 비교 기준 요약

| 모드 | PASS 기준 | SIMILAR PASS 기준 | 픽셀 허용 오차 |
|------|----------|--------------------|--------------|
| PNG  | SSIM ≥ 0.98, diff < 0.1% | SSIM ≥ 0.95, diff < 0.5% | ±2 |
| JPG  | SSIM ≥ 0.95, diff < 3.0% | SSIM ≥ 0.90, diff < 8.0% | ±15 |
| ROI strict (PNG) | SSIM ≥ 0.98, diff < 0.1% | — | ±2 |
| ROI strict (JPG) | SSIM ≥ 0.96, diff < 1.5% | — | ±15 |
| ROI non-strict | 포맷 기본 기준 적용 | — | — |

---

## 10. 고객 설명용 한 줄 요약

> "PNG는 무손실이라 픽셀 완전 일치 비교가 가능하지만, JPG는 손실 압축 특성상 같은 이미지라도 저장할 때마다 픽셀이 달라집니다.
> 그래서 JPG는 시각적 유사도(SSIM) 기반으로 비교하고, 속도 숫자·경고등·팝업처럼 핵심 영역은 포맷에 관계없이 별도로 엄격하게 검사하며,
> OCR로 텍스트/숫자 값을 직접 읽어 기대값과 일치하는지도 확인합니다."
