#!/usr/bin/env bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  이미지 비교 데모 설치 및 실행"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 의존성 설치 ───────────────────────────────────────────────
echo ""
echo "[1/2] 패키지 설치 확인..."
# 이미 설치된 경우 스킵, 없으면 venv 생성 후 설치
if python3 -c "import PIL, numpy, scipy" &> /dev/null; then
    echo "     패키지 이미 설치되어 있음 — 스킵"
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt --quiet
fi

# ── 데모 실행 ─────────────────────────────────────────────────
echo ""
echo "[2/2] 데모 실행..."
python3 demo.py

# ── 브라우저 열기 (WSL2 환경) ────────────────────────────────
REPORT="$(pwd)/demo_output/report.html"

echo ""
if command -v wslview &> /dev/null; then
    echo "브라우저로 여는 중..."
    wslview "$REPORT"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$REPORT"
else
    echo "리포트 경로: $REPORT"
    echo "Windows 탐색기에서 위 경로로 이동해 파일을 더블클릭하세요."
fi
