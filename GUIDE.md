# 고객 가이드 — 이미지 비교 테스트 엔진

> Tesla / Hyundai / Kia 차량 클러스터 UI 자동 검증 솔루션

---

## STEP 0. 왜 이 도구가 필요한가?

자동화 테스트에서 화면 스크린샷을 비교할 때 흔히 발생하는 문제가 있습니다.

| 상황 | 원인 |
|------|------|
| PNG 비교는 잘 되는데 JPG는 변경이 없어도 FAIL이 난다 | JPG는 손실 압축 — 저장할 때마다 픽셀값이 미세하게 달라짐 |
| 속도 숫자가 바뀌었는데 PASS가 나온다 | 전체 SSIM 기준만으로는 작은 숫자 변화를 놓칠 수 있음 |
| 팝업 메시지 내용이 바뀌었는데 PASS가 나온다 | 팝업 레이아웃·색상이 같으면 SSIM 단독으로는 구분 어려움 |

이 도구는 **포맷별 비교 전략 + 영역(ROI) 별도 검사 + OCR + 색상 감지**를 조합해
위 세 가지 문제를 모두 해결합니다.

---

## STEP 1. 설치

### 사전 조건
- Python 3.9 이상
- (선택) tesseract-ocr — 숫자·한국어 OCR 기능 사용 시

### 패키지 설치

```bash
git clone <repo-url> && cd ImageTest

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### OCR 엔진 설치 (선택)

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-kor
```

> OCR 없이도 SSIM·Hue 비교는 정상 동작합니다.
> OCR 미설치 시 OCR 컬럼은 N/A로 표시되며 판정에서 제외됩니다.

---

## STEP 2. 첫 번째 실행

```bash
python demo.py
```

Tesla / Hyundai / Kia 3개 브랜드 × 17개 케이스(총 45개)가 실행되고
`demo_output/report.html` 리포트가 생성됩니다.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [TESLA]  Tesla  Model S/3/X/Y
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [ 속도 표시 테스트 ]
    G-1. PNG 동일
       → PASS  SSIM=1.0000  diff=0.000%
    G-2. PNG 속도 변화 (80 → 120)
       → FAIL  SSIM=0.9234  diff=5.234%
          ❌ [속도(OCR)]  OCR base='80' curr='120'

  [ 팝업 테스트 ]
    P-5. JPG 팝업 텍스트 변경 (오일 → 타이어)
       → FAIL
          ❌ [팝업텍스트(OCR)]  '오일 교환 필요...' ≠ '타이어 공기압 부족'
```

### 특정 브랜드만 실행

```bash
python demo.py --brand tesla
python demo.py --brand hyundai
python demo.py --brand kia
```

### 브라우저로 리포트 열기

```bash
# WSL 환경
wslview demo_output/report.html

# 일반 Linux
xdg-open demo_output/report.html
```

---

## STEP 3. HTML 리포트 읽는 법

### 3-1. 상단 요약 카드

리포트를 열면 가장 먼저 보이는 요약 카드입니다.

```
┌──────┬─────────┬──────┬──────┬────────┐
│ PASS │ SIMILAR │ FAIL │ 전체 │ 합격률 │
│  25  │    8    │  12  │  45  │  73%   │
└──────┴─────────┴──────┴──────┴────────┘
```

- **상단 탭** (Tesla / Hyundai / Kia)을 클릭하면 브랜드별 통계로 실시간 전환됩니다.
- **합격률**: PASS + SIMILAR PASS 합산 기준입니다.

### 3-2. 테스트 추이 (2회 이상 실행 시 자동 표시)

실행할 때마다 결과가 자동으로 누적되어 추이를 보여줍니다.

| 실행 시간 | PASS | SIMILAR | FAIL | 합격률 |
|----------|------|---------|------|--------|
| 2026-03-19 09:10 | 22 | 8 | 15 | 67% |
| 2026-03-20 10:30 ← 현재 | 25 | 8 | 12 | **73%** |

> 개선이 있으면 합격률이 올라가는 것을 한눈에 확인할 수 있습니다.

### 3-3. 케이스 카드 — 각 열의 의미

| 열 | 의미 | `—` 표시 조건 |
|----|------|--------------|
| SSIM | 구조적 유사도 (1.0 = 완전 동일) | — |
| Diff | 변경된 픽셀 비율 (%) | — |
| Hue | 색상 차이 (도°) — 경고등 색상 변화 감지 | 색상 감지 OFF 영역 |
| OCR 기대 | baseline 이미지에서 OCR로 읽은 텍스트 | OCR OFF 영역 |
| OCR 실제 | current 이미지에서 OCR로 읽은 텍스트 | OCR OFF 영역 |
| OCR | baseline == current 일치 여부 ✅ / ❌ | OCR OFF 영역 |

> **`—` 는 버그가 아닙니다.** 해당 ROI에 색상 감지 / OCR이 설정되어 있지 않은 것이 정상입니다.

### 3-4. 이미지 클릭 → 확대 보기

모든 이미지를 클릭하면 라이트박스로 크게 볼 수 있습니다. **ESC**로 닫습니다.

---

## STEP 4. 핵심 기능 — 세 가지 포인트

### 포인트 ① ROI — 중요한 영역은 더 엄격하게

전체 이미지와 핵심 영역을 **따로 다른 기준으로** 검사합니다.

```
전체 이미지:  JPG 기준 (관대)  — 압축 아티팩트 허용
속도 ROI:     포맷 엄격 기준 + OCR 비교
팝업 ROI:     포맷 엄격 기준 + 한국어 OCR 비교
텔테일 ROI:   포맷 엄격 기준 + Hue 색상 변화 감지
```

**실제 시연 케이스 — G-4**: JPG 미세 속도 변화 (80 → 90 km/h)

> 전체 SSIM = 0.982 — 사람 눈으로는 거의 차이가 없습니다.
> 그러나 속도 ROI의 OCR이 `80` ≠ `90` 을 감지해서 FAIL을 냅니다.
> **SSIM만 쓰면 이 케이스는 놓칩니다.**

### 포인트 ② OCR — 기대값을 하드코딩하지 않음

```
기존 방식:  expected_speed = 80   # 코드에 직접 입력
이 도구:    baseline 이미지에서 자동으로 읽음 → 그 값이 기준
```

```
baseline OCR = "80"   (자동 추출)
current  OCR = "120"
80 ≠ 120  →  FAIL
```

> 기준값을 코드에 하드코딩할 필요가 없습니다.
> baseline 이미지를 교체하면 기준값이 자동으로 바뀝니다.

**실제 시연 케이스 — P-5**: 팝업 텍스트만 변경

> 팝업 레이아웃·색상·위치가 완전히 동일합니다. 텍스트만 다릅니다.
> SSIM 단독으로는 구분이 어렵지만 OCR이 정확히 잡아냅니다.

```
baseline:  "오일 교환 필요 주행 5,000km 초과"
current:   "타이어 공기압 부족 앞 우측 타이어 확인"
→  FAIL
```

### 포인트 ③ Hue — 경고등 색상이 바뀌면 감지

```
텔테일 OFF:       Hue diff = 0°     → PASS
ENG + OIL 켜짐:  Hue diff ≈ 36°    → FAIL (임계값 20° 초과)
여러 경고등:      Hue diff ≈ 66°    → FAIL
```

**실제 시연 케이스 — T-5**: 텔테일 패턴 교체 (ENG → FUEL)

> 켜진 경고등 수는 똑같이 1개입니다.
> 하지만 종류가 다르기 때문에 Hue 차이 38°로 FAIL이 납니다.

---

## STEP 5. 실무 연동

### 방법 A. YAML 설정 파일 (비개발자 권장)

파이썬 코드를 수정하지 않고 YAML 파일만 편집해서 테스트를 정의합니다.

```bash
python demo.py --config my_tests.yaml
```

```yaml
# my_tests.yaml
cases:
  - name: "오일 경고 팝업 검증"
    brand: hyundai
    baseline: screenshots/normal.jpg
    current:  screenshots/oil_warning.jpg
    expected: FAIL
    rois:
      - name:      팝업텍스트
        x:         40
        y:         205
        width:     390
        height:    60
        ocr:       true
        ocr_lang:  kor+eng

  - name: "속도 표시 정상 확인"
    brand: tesla
    baseline: screenshots/speed_base.png
    current:  screenshots/speed_now.png
    expected: PASS
    use_brand_rois: true   # 브랜드 표준 ROI 4개 자동 포함
```

`tests_sample.yaml` 파일을 복사해서 경로만 수정하면 됩니다.

### 방법 B. CI/CD 파이프라인 연동

```bash
# JUnit XML 함께 출력 — Jenkins, GitHub Actions, GitLab CI 등에서 읽힘
python demo.py --junit results.xml
python demo.py --config my_tests.yaml --junit results.xml
```

생성된 XML 예시:

```xml
<testsuites name="클러스터 이미지 비교" tests="45" failures="12">
  <testsuite name="tesla" tests="15" failures="4">
    <testcase name="속도 표시 테스트 > PNG 속도 변화 (80 → 120)">
      <failure message="핵심 영역(ROI) 변경 감지">
        SSIM=0.9234, diff=5.234%
        ROI [속도(OCR)]: OCR base='80' curr='120'
      </failure>
    </testcase>
  </testsuite>
</testsuites>
```

### 방법 C. ROI 좌표 모를 때 — Picker 도구

```bash
# WSL GUI 환경 (sudo apt-get install python3-tk 필요)
python roi_picker.py screenshot.png
python roi_picker.py screenshot.png --scale 2   # 작은 이미지 2배 확대
```

| 조작 | 동작 |
|------|------|
| 마우스 드래그 | ROI 사각형 그리기 |
| Enter / Space | 현재 ROI 확정 (이름 입력 팝업) |
| Backspace | 마지막 ROI 취소 |
| Esc / Q | 종료 후 좌표 코드 출력 |

종료 시 Python / YAML / CLI 형식 코드를 자동으로 출력합니다.

```
# ── Python (ROI 객체 목록) ─────────────────────
ROI(name='속도 표시', x=158, y=52, width=164, height=120, strict=True),

# ── YAML / JSON 설정 ──────────────────────────
rois:
  - name:   '속도 표시'
    x:      158
    y:      52
    width:  164
    height: 120
    strict: true
```

---

## STEP 6. 새 브랜드 추가 방법

실제 클러스터 스크린샷을 기준으로 좌표를 측정하면 됩니다.

#### 1) roi_picker.py로 좌표 선택

```bash
python roi_picker.py actual_cluster_screenshot.png --scale 2
# → 텔테일 바, 속도, 배터리, 팝업 4개 영역 선택
```

#### 2) demo.py에 브랜드 ROI 등록

```python
BRAND_ROIS['bmw'] = [
    ROI(name='텔테일 표시줄', x=0,   y=0,   width=480, height=48, strict=True, color_check=True),
    ROI(name='속도 표시',     x=160, y=55,  width=160, height=115, strict=True),
    ROI(name='배터리',        x=320, y=55,  width=155, height=135, strict=False),
    ROI(name='팝업 영역',     x=0,   y=210, width=480, height=60,  strict=True),
]
```

#### 3) YAML 파일로 실제 스크린샷 비교

```bash
python demo.py --config bmw_tests.yaml
```

---

## 자주 묻는 질문

**Q. SIMILAR PASS는 뭔가요?**
> JPG 극단 압축(Q=20 수준)처럼 눈으로는 같지만 PASS 기준을 약간 초과하는 경우입니다. 실제 UI 변경과는 다른 압축 아티팩트입니다.

**Q. OCR이 완벽하지 않으면 오탐이 나지 않나요?**
> baseline과 current에 동일한 OCR이 적용됩니다. 같은 이미지면 항상 같은 결과가 나오기 때문에 오탐이 없습니다. OCR이 `"5,O00km"` 으로 잘못 읽어도 양쪽이 똑같이 잘못 읽으므로 PASS입니다.

**Q. 실제 캡처 화면으로 바로 쓸 수 있나요?**
> `tests_sample.yaml`에 실제 스크린샷 경로를 지정하고 `python demo.py --config tests.yaml` 을 실행하면 됩니다. 생성 이미지 없이 실제 파일을 바로 비교합니다.

**Q. 히스토리 파일은 어디에 있나요?**
> `demo_output/.history.json`에 자동 저장됩니다 (최대 20회 유지). 리포트를 새로 생성할 때마다 자동으로 추이가 업데이트됩니다.

**Q. PNG와 JPG를 교차 비교할 수 있나요?**
> 가능합니다. 둘 중 하나라도 JPG면 자동으로 JPG 모드(지각적 유사도 기준)로 전환됩니다.

---

## 비교 기준 요약

| 모드 | PASS 기준 | SIMILAR PASS | 픽셀 허용 오차 |
|------|-----------|-------------|--------------|
| PNG  | SSIM ≥ 0.98, diff < 0.1% | SSIM ≥ 0.95, diff < 0.5% | ±2 |
| JPG  | SSIM ≥ 0.95, diff < 3.0% | SSIM ≥ 0.90, diff < 8.0% | ±15 |
| ROI strict (PNG) | SSIM ≥ 0.98, diff < 0.1% | — | ±2 |
| ROI strict (JPG) | SSIM ≥ 0.96, diff < 1.5% | — | ±15 |
| Hue 색상 변화 | — | — | 20° 초과 시 FAIL |

---

## 한 줄 요약

> **PNG는 픽셀 완전 일치, JPG는 시각적 유사도 — 포맷에 따라 기준을 자동 선택하고,
> 속도·팝업·경고등처럼 중요한 영역은 OCR·색상 감지로 이중 검증합니다.**
