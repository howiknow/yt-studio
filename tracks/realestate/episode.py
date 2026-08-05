"""부동산 — 에피소드 원커맨드 오케스트레이터.

candidate + 수집 에셋 → ① 뽀개기 덱(pptx) → ② 슬라이드 PNG → ③ 대본+facts →
④ produce 렌더까지 한 번에. cli.py `re-episode`가 호출한다.

- 덱 생성: tracks/realestate/js/deck.js (pptxgenjs, spec JSON 주도)
- 슬라이드 변환: Keynote(AppleScript)로 pptx→pdf → pdftoppm PNG. macOS 전용 —
  Keynote가 없으면 CaptureError로 안내한다. (LibreOffice 설치 시 soffice 폴백 여지)
- 대본: 슬라이드 타입별 한국어 템플릿. 수치는 {{fact:key}} 토큰만 사용 (규칙 5-3).
- 평점: 공개 데이터 기반 휴리스틱 초안 — 발행 전 사람 검토 전제.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

from core.schemas import FactSheet

from tracks.realestate.assets import CaptureError, JS_DIR, _node, collect_assets
from tracks.realestate.parser import Candidate, build_fact_sheet


# ---------------------------------------------------------------------------
# 평점 휴리스틱 (초안 — 사람 검토 전제)
# ---------------------------------------------------------------------------

def build_ratings(c: Candidate) -> dict:
    dist = c.station_distance_m()
    rows: list[tuple[str, float, str]] = []

    if dist is None:
        transit = 3.5
        rows.append(("교통·역세권", transit, "역거리 정보 없음 — 공고문에서 확인 필요"))
    elif dist <= 250:
        transit = 5.0
        rows.append(("교통·역세권", transit, f"출구 {dist}m 초역세권. 만점 아니면 반칙"))
    elif dist <= 450:
        transit = 4.5
        rows.append(("교통·역세권", transit, f"출구 {dist}m — 도보 5분 안쪽 역세권"))
    else:
        transit = 4.0
        rows.append(("교통·역세권", transit, f"출구 {dist}m — 도보권이긴 한 거리"))

    rent = c.rent_low_won or 0
    if rent and rent <= 100_000:
        price = 4.5
        rows.append(("가격 부담", price, "최저 월세 10만원 이하 — 진입장벽 낮은 편"))
    elif rent and rent <= 250_000:
        price = 4.0
        rows.append(("가격 부담", price, "월세 부담 무난한 구간"))
    else:
        price = 3.5
        rows.append(("가격 부담", price, "타입별 임대료 편차 큼 — 공고문 필독"))

    space = 4.0 if (c.video and c.video.relevant) else 3.5
    rows.append(("내부·공간", space,
                 "공식 투어 영상으로 내부 확인 가능" if space == 4.0
                 else "내부는 공고문 평면도 기준 — 소형 타입 위주 예상"))

    infra = 4.5 if (dist is not None and dist <= 300) else 4.0
    rows.append(("생활 인프라", infra, "역세권 상권이 곧 생활권" if infra == 4.5 else "역 주변 상권 이용"))

    quiet = 2.5 if (dist is not None and dist <= 250) else 3.5
    rows.append(("조용한 주거환경", quiet,
                 "역전 번화가 한복판 — 소음 감안" if quiet == 2.5 else "역과 적당한 거리 — 무난"))

    total = round(sum(r[1] for r in rows) / len(rows) * 2) / 2
    return {"rows": rows, "total": total}


# ---------------------------------------------------------------------------
# 덱 스펙 + 슬라이드별 내레이션
# ---------------------------------------------------------------------------

def _fmt_man(won: int) -> str:
    """48000000 → '4,800만원'."""
    man = won // 10_000
    return f"{man:,}만원"


def build_spec_and_script(c: Candidate, assets: dict, ratings: dict) -> tuple[dict, list[str], dict]:
    """덱 spec(slides[]) + 슬라이드별 내레이션 + facts(json용)를 함께 만든다.

    슬라이드 순서와 내레이션 순서는 항상 1:1 — produce의 씬 매핑 전제.
    """
    rv, maps, frames = assets.get("roadview", {}), assets.get("maps", {}), assets.get("tour_frames", [])
    dist = c.station_distance_m()
    facts: dict[str, str | int | float] = dict(build_fact_sheet(c).facts)
    if c.deposit_low_won:
        facts["deposit_fmt"] = _fmt_man(c.deposit_low_won)
    if c.rent_low_won:
        facts["rent_fmt"] = _fmt_man(c.rent_low_won)
    if c.total_units:
        facts["units_fmt"] = f"{c.total_units}세대"
    if dist is not None:
        facts["dist_fmt"] = f"{dist}미터"

    hero = rv.get("tower") or rv.get("front") or maps.get("close")
    slides: list[dict] = []
    lines: list[str] = []

    # 1. 커버
    sub_bits = [c.address, "청년안심주택"]
    if c.total_units:
        sub_bits.append(f"총 {c.total_units}세대")
    if c.video and c.video.relevant:
        sub_bits.append("공식 투어 영상 있음")
    slides.append({"type": "cover", "image": hero, "name": c.name,
                   "subtitle": "  ·  ".join(sub_bits),
                   "footer": "데이터: 서울시 청년안심주택 · 카카오맵 로드뷰 · 공식 홈페이지"})
    lines.append("안녕하세요 예린이에요. 청약은 아는 만큼 붙는다, 오늘 뽀갤 매물은 {{fact:complex_name}}입니다.")

    # 2. 결론 카드
    cards = []
    if dist is not None:
        cards.append({"big": f"{dist}m", "small": "지하철 출구까지\n실측 직선거리"})
    if c.rent_low_won:
        cards.append({"big": f"월 { _fmt_man(c.rent_low_won) }~", "small": f"월 임대료 최저 기준\n보증금 {_fmt_man(c.deposit_low_won or 0)}~"})
    if c.total_units:
        cards.append({"big": f"{c.total_units}세대", "small": "단지 규모"})
    cards.append({"big": "영상 있음" if (c.video and c.video.relevant) else "청년안심주택",
                  "small": "공식 홈페이지에\n단지 투어 영상" if (c.video and c.video.relevant) else "만 19~39세\n무주택 청년 대상"})
    slides.append({"type": "summary", "cards": cards[:4],
                   "oneliner": f'"{c.gu or c.address}에서 이 조건이면 공고 알림 걸어둘 가치가 충분합니다. 타입별 조건은 공고문으로 꼭 확인하세요."'})
    lines.append("결론부터 정리할게요. 역까지 {{fact:dist_fmt}}, 월세 {{fact:rent_fmt}}부터 시작하는 {{fact:units_fmt}} 청년안심주택입니다."
                 if (dist is not None and c.rent_low_won and c.total_units)
                 else "결론부터 정리할게요. 핵심 조건은 화면의 카드 네 장으로 요약됩니다.")

    # 3. 위치 (광역 지도)
    if maps.get("wide"):
        slides.append({"type": "map", "title": "서울 어디쯤이냐면요", "image": maps["wide"],
                       "credit": "빨간 원이 오늘의 매물 위치 (지도: 카카오맵)",
                       "items": [["행정구역", f"{c.gu} — {c.address}"],
                                 ["대중교통", c.subway or "지하철 정보는 공고문 확인"],
                                 ["체크", "출퇴근 동선을 지도에서 먼저 그려보세요"]]})
        lines.append("위치부터 볼게요. 지도의 빨간 원, {{fact:address}}입니다. {{fact:subway_desc}} 조건이에요.")

    # 4. 역세권 (근접 지도)
    if maps.get("close"):
        slides.append({"type": "map", "title": "역세권, 진짜인지 확인해봤습니다", "image": maps["close"],
                       "credit": "지도: 카카오맵",
                       "items": [["지하철", c.subway or "-"],
                                 ["생활권", "지도 한 화면 안의 편의시설을 확인하세요"],
                                 ["체크", "낮과 밤의 거리 분위기는 로드뷰로 이어서 봅니다"]]})
        lines.append("지도를 당겨보면 이렇게 역이 코앞입니다. 주변 편의시설도 한 화면 안에 다 들어와요.")

    # 5~. 로드뷰
    rv_meta = [("front", "로드뷰 ①  단지 앞", "단지 앞 거리 모습입니다.", "포장 상태와 상가, 보행 환경을 확인하세요."),
               ("tower", "로드뷰 ②  단지 외관", "고개를 들면 이렇게 보입니다.", "외관 마감과 저층부 구성을 확인할 수 있어요."),
               ("street", "로드뷰 ③  주변 거리", "단지 반대편 거리입니다.", "생활 소음과 동네 분위기를 가늠해보세요.")]
    for key, chip_label, head, body in rv_meta:
        if rv.get(key):
            slides.append({"type": "photo", "image": rv[key], "chip": chip_label, "head": head, "body": body + "  (카카오맵 로드뷰)"})
            lines.append({"front": "이제 로드뷰로 직접 가볼게요. 단지 앞 거리, 포장 상태와 상가 분위기를 그대로 보여드립니다.",
                          "tower": "고개를 들어 외관을 보면 이렇습니다. 저층부 상가에 상부 주거, 전형적인 역세권 구성이죠.",
                          "street": "단지 주변 거리도 한 바퀴 돌아봤어요. 동네 분위기는 이 정도입니다."}[key])

    # 내부 프레임 (공식 투어 영상 캡처)
    for i, fr in enumerate(frames[:4], 1):
        slides.append({"type": "photo", "image": fr, "chip": f"내부 {'①②③④'[i-1]}  투어 영상",
                       "head": "공식 투어 영상에서 캡처한 내부입니다.",
                       "body": "로드뷰가 못 보는 안쪽을 여기서 채웁니다.  (출처: 공식 둘러보기 영상)"})
        lines.append("공식 투어 영상에서 내부를 캡처했어요. 마감과 구조를 직접 확인해보세요." if i == 1
                     else "이어서 내부 다른 공간입니다. 사진으로 못 담는 디테일은 영상 원본을 확인하세요.")

    # 개요
    rows = [["단지명", c.name], ["주소", c.address], ["유형", "청년안심주택 (임대)"]]
    if c.total_units:
        rows.append(["세대수", f"총 {c.total_units}세대"])
    if c.subway:
        rows.append(["교통", c.subway[:28]])
    if c.phone:
        rows.append(["입주 문의", c.phone])
    slides.append({"type": "overview", "image": hero, "credit": "이미지: 카카오맵 로드뷰", "rows": rows[:7]})
    lines.append("단지 개요 정리합니다. {{fact:address}}, 청년안심주택이고, 문의처는 화면 오른쪽 표를 참고하세요.")

    # 가격
    if c.deposit_low_won and c.rent_low_won:
        slides.append({"type": "price", "deposit": f"{_fmt_man(c.deposit_low_won)} ~", "rent": f"{_fmt_man(c.rent_low_won)} ~"})
        lines.append("가격 갑니다. 보증금 최저 {{fact:deposit_fmt}}부터, 월 임대료 {{fact:rent_fmt}}부터. 보증금을 올리면 월세를 낮추는 전환형입니다.")

    # 평점
    slides.append({"type": "rating", "rows": [list(r) for r in ratings["rows"]], "total": ratings["total"],
                   "comment": '"숫자는 참고, 계약 전 공고문과 현장이 진짜입니다"'})
    lines.append(f"예린이의 뽀개기 평점입니다. 총점 {str(ratings['total']).replace('.', '쩜')}점. 항목별 점수는 화면을 참고하세요.")

    # 총평
    pros, cons = [], []
    if dist is not None and dist <= 300:
        pros.append(f"출구까지 {dist}m 진짜 역세권")
        cons.append("역전 번화가 — 저녁 소음 감안")
    if c.rent_low_won and c.rent_low_won <= 150_000:
        pros.append(f"월세 {_fmt_man(c.rent_low_won)}~ 부담 없는 임대료")
    if c.video and c.video.relevant:
        pros.append("공식 투어 영상으로 내부 미리 확인")
    if c.total_units and c.total_units >= 300:
        pros.append(f"{c.total_units}세대 대단지 관리 안정감")
    else:
        cons.append("소규모 단지 — 공실 나올 때만 기회")
    cons += ["소형 타입 위주 — 면적 기대치 조정", "임대료·전환 조건은 타입별 편차 큼 — 공고문 필독"]
    slides.append({"type": "verdict", "pros": pros[:4] or ["핵심 장점은 공고문 확인 후 업데이트"], "cons": cons[:4],
                   "closing": '"오늘 매물, 조건 맞는 분은 공고 알림부터 걸어두세요."',
                   "footer": f"문의 {c.phone or '공고문 참조'}   |   데이터: 서울시 청년안심주택 · 카카오맵"})
    lines.append("정리하면, 조건이 맞는 분에게는 충분히 노려볼 매물입니다. 다음 매물도 예린이가 뽀개드릴게요. 구독과 댓글 부탁드려요.")

    assert len(slides) == len(lines), f"slides {len(slides)} != lines {len(lines)}"
    return {"slides": slides}, lines, facts


# ---------------------------------------------------------------------------
# 덱 → 슬라이드 PNG
# ---------------------------------------------------------------------------

# 렌더 엔진 — overlay(PIL 직접 렌더, 기본) / deck(pptx→Keynote, macOS 전용)
DECK_ENGINE = os.environ.get("RE_DECK_ENGINE", "overlay")


def build_deck(spec: dict, out_pptx: pathlib.Path) -> pathlib.Path:
    out_pptx = out_pptx.resolve()
    spec_path = out_pptx.with_suffix(".spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    _node("deck.js", str(spec_path), str(out_pptx), timeout=120)
    return out_pptx


def deck_to_slides(pptx: pathlib.Path, out_dir: pathlib.Path, dpi: int = 150) -> list[pathlib.Path]:
    """pptx → (Keynote) pdf → (pdftoppm) 슬라이드 PNG. 파일명 숫자 = 씬 번호."""
    pptx, out_dir = pptx.resolve(), out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pptx.with_suffix(".pdf")
    script = f'''
tell application "Keynote"
    activate
    set doc to open (POSIX file "{pptx}")
    delay 4
    export doc to (POSIX file "{pdf}") as PDF
    close doc saving no
end tell'''
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=180)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise CaptureError("pptx→pdf 변환 실패 — macOS Keynote 필요 (또는 LibreOffice 설치 후 이 함수에 soffice 경로 추가)") from e
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), str(pdf), str(out_dir / "s")], check=True, capture_output=True)
    pages = sorted(out_dir.glob("s-*.png"))
    for i, p in enumerate(pages, 1):
        p.rename(out_dir / f"{i}.png")
    return sorted(out_dir.glob("[0-9]*.png"), key=lambda p: int(p.stem))


# ---------------------------------------------------------------------------
# 원커맨드
# ---------------------------------------------------------------------------

def make_episode(c: Candidate, out_root: pathlib.Path = pathlib.Path("data/assets/produce"),
                 skip_assets: bool = False) -> dict:
    """스카우트된 후보 하나 → 덱 → 슬라이드 → 대본 → 렌더 준비물 일체 생성.

    반환: {"slug", "script", "images_dir", "deck"} — cli가 produce로 넘긴다.
    """
    slug = f"re-{c.home_code or re.sub(r'[^0-9A-Za-z가-힣]', '', c.name)}"
    ep_dir = (out_root / slug).resolve()
    ep_dir.mkdir(parents=True, exist_ok=True)

    assets_json = pathlib.Path("data/assets/realestate") / (c.home_code or slug) / "assets.json"
    if not skip_assets or not assets_json.exists():
        assets = collect_assets(c)
    else:
        assets = json.loads(assets_json.read_text(encoding="utf-8"))

    ratings = build_ratings(c)
    spec, lines, facts = build_spec_and_script(c, assets, ratings)

    images_dir = ep_dir / "slides"
    if DECK_ENGINE == "overlay":
        # 오버레이 엔진: PIL로 바로 PNG를 그린다 (Keynote 불필요, 표현 제약 없음)
        from tracks.realestate.overlay import render_spec

        deck = ep_dir / f"{slug}.spec.json"
        for old in images_dir.glob("*.png"):
            old.unlink()
        pages = render_spec(spec, images_dir)
    else:
        deck = build_deck(spec, ep_dir / f"{slug}.pptx")
        pages = deck_to_slides(deck, images_dir)
    if len(pages) != len(lines):
        raise CaptureError(f"슬라이드 {len(pages)}장 ≠ 대본 {len(lines)}행 — spec 불일치")

    script_path = pathlib.Path("data/scripts") / f"{slug}.txt"
    new_text = "\n".join(lines) + "\n"
    script_unchanged = script_path.exists() and script_path.read_text(encoding="utf-8") == new_text
    script_path.write_text(new_text, encoding="utf-8")
    script_path.with_suffix(".facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"slug": slug, "script": str(script_path), "images_dir": str(images_dir),
            "deck": str(deck), "n_slides": len(pages),
            "script_unchanged": script_unchanged}
