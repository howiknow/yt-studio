#!/bin/zsh
# 예린이의 부동산 뽀개기 — 제작 스튜디오 실행기.
# 파인더에서 더블클릭하면: 환경 자동 준비 → 서버 실행 → 브라우저가 열립니다.
# 이 창은 서버 로그입니다 — 닫으면 스튜디오도 꺼져요. (문제 생기면 이 창을 캡처해 팀 채팅에!)

set -e
cd "$(dirname "$0")"

echo "🏠 예린이의 부동산 뽀개기 — 제작 스튜디오"
echo "───────────────────────────────────────"

# 1) 파이썬 가상환경 (처음 한 번만 만들어짐, 이후엔 바로 통과)
if [ ! -x .venv/bin/python ]; then
  echo "• 처음 실행이네요 — 파이썬 환경을 준비합니다 (1~2분, 한 번만)"
  PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
  "$PY" -m venv .venv
  ./.venv/bin/python -m pip install --quiet --upgrade pip
fi
# 의존성 점검 — 핵심 패키지가 이미 있으면 즉시 통과 (pull로 새 의존성이 생겼을 때만 설치)
if ! ./.venv/bin/python -c "import fastapi, uvicorn, PIL, yaml, pydantic" 2>/dev/null; then
  echo "• 새 의존성 설치 중…"
  ./.venv/bin/python -m pip install --quiet -e . || ./.venv/bin/python -m pip install -e .
fi

# 2) 필수 도구 점검 — 없으면 설치 방법을 알려주고 계속 진행
command -v ffmpeg >/dev/null || echo "⚠️  ffmpeg 없음 → 터미널에서: brew install ffmpeg"
command -v pdftoppm >/dev/null || echo "⚠️  poppler 없음 → 터미널에서: brew install poppler"
command -v node >/dev/null || echo "⚠️  node 없음 → 터미널에서: brew install node (로드뷰 캡처에 필요)"
[ -d "/Applications/Keynote.app" ] || echo "⚠️  Keynote 없음 → App Store에서 설치 (무료, 슬라이드 변환에 필요)"
grep -q "TYPECAST_API_KEY=." .env 2>/dev/null || \
  echo "⚠️  .env에 TYPECAST_API_KEY가 비어 있음 → 팀 공유 키를 넣어야 예린 목소리가 나옵니다"

# 3) 이미 실행 중이면 새로 띄우지 않고 브라우저만 연다 (중복 더블클릭 안전)
if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:8787/api/realestate/syncinfo"; then
  echo "• 스튜디오가 이미 켜져 있어요 — 브라우저만 엽니다"
  open "http://127.0.0.1:8787/realestate"
  echo "  (완전히 새로 시작하고 싶으면: 기존 스튜디오 터미널 창을 닫고 다시 더블클릭)"
  read -s -k '?이 창은 닫아도 됩니다 — 아무 키나 누르세요' || true
  exit 0
fi

# 4) 서버 실행 + 브라우저 오픈
echo "• 스튜디오 시작 → http://127.0.0.1:8787/realestate"
( sleep 2 && open "http://127.0.0.1:8787/realestate" ) &
exec ./.venv/bin/python cli.py ui
