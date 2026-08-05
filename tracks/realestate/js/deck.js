// 예린이의 부동산 뽀개기 — 데이터 주도 매물 브리핑 덱 생성기 (방송 그래픽판).
// Usage: node deck.js <spec.json> <out.pptx>
// spec: episode.py의 build_spec() 산출물. slides[] 순서대로 렌더한다.
//
// 설계 원칙 (문서용 PPT가 아니라 "영상에 얹는 그래픽"):
//  1. 한 화면 한 메시지 — 문장 대신 숫자·키워드
//  2. 거대 타이포 — 모바일 시청 기준, 숫자 96~120pt / 헤드 48~60pt / 본문 20pt+
//  3. 하단 안전영역(SAFE_Y) 아래로는 아무것도 두지 않는다 — 렌더가 자막을 굽는 자리
//  4. 이미지는 풀블리드 또는 화면 절반 이상 — 잘린 썸네일 금지
//  5. 흰 배경 카드·번호 동그라미 같은 PPT 클리셰 금지
const pptxgen = require('pptxgenjs');
const fs = require('fs');

const [specPath, outPath] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf-8'));

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.33 x 7.5 in
const W = 13.33, H = 7.5;
const SAFE_Y = 5.78;   // 이 아래는 자막 영역 — 핵심 요소 배치 금지
const M = 0.86;        // 좌우 기본 여백

// ── 테마 ────────────────────────────────────────────────────────────────────
// DECK_THEME 환경변수로 선택 (기본 broadcast). 색·폰트·이미지 처리 방식이 바뀐다.
const THEMES = {
  // ① 방송 그래픽 — 딥 잉크 + 캐럿 오렌지, 이미지 풀블리드
  broadcast: {
    bg: '14161A', panel: '1E222A', accent: 'FF6600', accent2: 'FF9364',
    fg: 'FFFFFF', dim: 'A8ADB6', line: '2E333C',
    font: 'Apple SD Gothic Neo', headFont: 'Apple SD Gothic Neo',
    light: false, bleed: true, chipRadius: 0.25, headSize: 46, numSize: 62,
  },
  // ② 매거진 에디토리얼 — 아이보리 지면 + 명조 헤드, 이미지는 여백 두고 앉힘
  magazine: {
    bg: 'F5F1EA', panel: 'EAE3D8', accent: '1F4B3F', accent2: '4E7A6B',
    fg: '1A1A18', dim: '6E675C', line: 'D9D0C2',
    font: 'Apple SD Gothic Neo', headFont: 'AppleMyungjo',
    light: true, bleed: false, chipRadius: 0.05, headSize: 44, numSize: 58,
  },
  // ③ 뉴스 브리핑 — 화이트 + 딥블루, 상단 컬러바, 데이터 강조
  news: {
    bg: 'FFFFFF', panel: 'F1F4F9', accent: '0B3D91', accent2: 'D62828',
    fg: '10141C', dim: '5A6172', line: 'D9DEE8',
    font: 'Apple SD Gothic Neo', headFont: 'Apple SD Gothic Neo',
    light: true, bleed: true, chipRadius: 0.05, headSize: 48, numSize: 66,
    topBar: true,
  },
  // ④ 네온 나이트 — 딥 네이비 + 시안/라임, 초대형 숫자
  neon: {
    bg: '0A0F1F', panel: '141B33', accent: '00E5A0', accent2: '35C2FF',
    fg: 'F2F6FF', dim: '8A94B0', line: '25304F',
    font: 'Apple SD Gothic Neo', headFont: 'Apple SD Gothic Neo',
    light: false, bleed: true, chipRadius: 0.25, headSize: 46, numSize: 70,
  },
};
const T = THEMES[process.env.DECK_THEME] || THEMES.broadcast;

const INK = T.bg, INK2 = T.panel, BRAND = T.accent, BRAND_L = T.accent2,
      WHITE = T.fg, DIM = T.dim, LINE = T.line;
const KR = T.font, KRH = T.headFont;
const ON_IMG = T.light ? 'FFFFFF' : T.fg;   // 이미지 위 글자는 항상 흰색

// ── 공통 파츠 ───────────────────────────────────────────────────────────────
const rect = (s, o) => s.addShape('rect', { line: { type: 'none' }, ...o });

const SCRIM = require('path').resolve(__dirname, '../../../data/assets/realestate/_ui/scrim.png');

/** 이미지 위 가독성 확보용 스크림 — 알파 그라데이션 PNG (사각형을 겹치면 계단이 보인다) */
function scrim(s, topY = 0) {
  s.addImage({ path: SCRIM, x: 0, y: topY, w: W, h: H - topY });
}

/** 글자 수에 따라 폰트를 줄여 한 줄에 담는다 (오버플로 방지) */
function fitSize(text, base, perChar = 1.9, min = 26) {
  const over = Math.max(0, String(text).length - 7);
  return Math.max(min, Math.round(base - over * perChar));
}
/** 좌상단 카테고리 칩 */
function kicker(s, text, color = BRAND) {
  const w = Math.max(1.5, text.length * 0.19 + 0.6);
  s.addShape('roundRect', { x: M, y: 0.62, w, h: 0.5, rectRadius: 0.25, fill: { color }, line: { type: 'none' } });
  s.addText(text, { x: M, y: 0.62, w, h: 0.5, align: 'center', valign: 'middle', margin: 0,
    fontFace: KR, fontSize: 15, bold: true, color: 'FFFFFF', charSpacing: -0.3 });
}
/** 잉크 배경 + 상단 킥커 + 큰 헤드라인 (텍스트 슬라이드 공통 헤더) */
function head(s, kick, headline) {
  s.background = { color: INK };
  s.addText(kick, { x: M, y: 0.72, w: 10, h: 0.42, margin: 0,
    fontFace: KR, fontSize: 16, bold: true, color: BRAND, charSpacing: 0.6 });
  s.addText(headline, { x: M, y: 1.22, w: W - M * 2, h: 1.0, margin: 0,
    fontFace: KRH, fontSize: T.headSize, bold: true, color: WHITE, charSpacing: -1.2 });
  if (T.topBar) rect(s, { x: 0, y: 0, w: W, h: 0.12, fill: { color: BRAND } });
}
/** 안전영역 바로 위에 놓는 한 줄 강조 (오렌지 좌측 바 + 텍스트) */
function footline(s, text, y = 4.98) {
  rect(s, { x: M, y, w: 0.09, h: 0.66, fill: { color: BRAND } });
  s.addText(text, { x: M + 0.32, y: y - 0.04, w: W - M * 2 - 0.4, h: 0.74, valign: 'middle', margin: 0,
    fontFace: KR, fontSize: 20, color: 'E6E8EC', charSpacing: -0.4 });
}

// ── 슬라이드 렌더러 ─────────────────────────────────────────────────────────
const R = {
  /* 커버 — 풀블리드 + 거대 단지명 */
  cover(p) {
    const s = pres.addSlide();
    s.background = { color: INK };
    if (T.bleed) {
      if (p.image) s.addImage({ path: p.image, x: 0, y: 0, w: W, h: H, sizing: { type: 'cover', w: W, h: H } });
      scrim(s);
      if (T.topBar) rect(s, { x: 0, y: 0, w: W, h: 0.12, fill: { color: BRAND } });
      kicker(s, '예린이의 부동산 뽀개기');
      s.addText(p.name, { x: M, y: 3.42, w: W - M * 2, h: 1.5, margin: 0,
        fontFace: KRH, fontSize: 62, bold: true, color: 'FFFFFF', charSpacing: -2 });
      s.addText(p.subtitle, { x: M, y: 4.98, w: W - M * 2, h: 0.6, margin: 0,
        fontFace: KR, fontSize: 21, color: 'D5D8DD', charSpacing: -0.4 });
    } else {
      // 매거진: 지면 위에 사진을 얹고 타이포는 여백에
      if (p.image) s.addImage({ path: p.image, x: 6.0, y: 0.9, w: W - 6.0 - M, h: 5.5,
        sizing: { type: 'cover', w: W - 6.0 - M, h: 5.5 } });
      s.addText('예린이의 부동산 뽀개기', { x: M, y: 0.95, w: 4.6, h: 0.4, margin: 0,
        fontFace: KR, fontSize: 15, bold: true, color: BRAND, charSpacing: 1.2 });
      rect(s, { x: M, y: 1.5, w: 1.4, h: 0.05, fill: { color: BRAND } });
      s.addText(p.name, { x: M, y: 2.0, w: 4.9, h: 2.4, margin: 0,
        fontFace: KRH, fontSize: 50, bold: true, color: WHITE, charSpacing: -1.6,
        lineSpacingMultiple: 1.08 });
      s.addText(p.subtitle.replace(/  ·  /g, '\n'), { x: M, y: 4.5, w: 4.7, h: 1.2, margin: 0,
        fontFace: KR, fontSize: 16, color: DIM, charSpacing: -0.3, lineSpacingMultiple: 1.3 });
    }
  },

  /* 결론 — 거대 숫자 3분할 + 한 줄 평 */
  summary(p) {
    const s = pres.addSlide();
    head(s, '오늘의 결론', '먼저 숫자 세 개만 보세요');
    const cards = p.cards.slice(0, 3);
    const colW = (W - M * 2) / cards.length;
    cards.forEach((c, i) => {
      const x = M + i * colW;
      const big = String(c.big).replace(/^월\s*/, '');
      s.addText(big, { x: x + 0.06, y: 2.55, w: colW - 0.3, h: 1.3, margin: 0,
        fontFace: KR, fontSize: fitSize(big, T.numSize), bold: true,
        color: i === 0 ? BRAND : WHITE, charSpacing: -2 });
      const label = (c.small || '').split('\n')[0];
      s.addText(label, { x: x + 0.08, y: 3.9, w: colW - 0.35, h: 0.5, margin: 0,
        fontFace: KR, fontSize: 17, color: DIM, charSpacing: -0.3 });
    });
    footline(s, p.oneliner.replace(/^"|"$/g, ''));
  },

  /* 지도 — 우측 풀높이 이미지 + 좌측 텍스트 패널 (겹침 없음) */
  map(p) {
    const s = pres.addSlide();
    s.background = { color: INK };
    const imgX = 5.9;
    s.addImage({ path: p.image, x: imgX, y: 0, w: W - imgX, h: H, sizing: { type: 'cover', w: W - imgX, h: H } });
    rect(s, { x: 0, y: 0, w: imgX, h: H, fill: { color: INK } });          // 텍스트 패널 바탕
    rect(s, { x: imgX - 0.02, y: 0, w: 0.04, h: H, fill: { color: BRAND } }); // 경계 액센트
    s.addText(p.title, { x: M, y: 0.95, w: imgX - M - 0.45, h: 1.6, margin: 0,
      fontFace: KR, fontSize: fitSize(p.title, 42, 1.15, 26), bold: true, color: WHITE,
      charSpacing: -1.2, lineSpacingMultiple: 1.05 });
    let y = 2.72;
    for (const [h1, b] of p.items.slice(0, 3)) {
      s.addText(h1, { x: M, y, w: imgX - M - 0.5, h: 0.4, margin: 0,
        fontFace: KR, fontSize: 17, bold: true, color: BRAND, charSpacing: -0.2 });
      s.addText(b, { x: M, y: y + 0.42, w: imgX - M - 0.55, h: 0.72, margin: 0,
        fontFace: KR, fontSize: 18, color: 'D5D8DD', charSpacing: -0.4, lineSpacingMultiple: 1.15 });
      y += 1.22;
    }
  },

  /* 로드뷰·내부 — 풀블리드 + 하단 헤드라인 */
  photo(p) {
    const s = pres.addSlide();
    s.background = { color: INK };
    if (!T.bleed) {
      s.addImage({ path: p.image, x: M, y: 1.55, w: W - M * 2, h: 3.9,
        sizing: { type: 'cover', w: W - M * 2, h: 3.9 } });
      s.addText(p.chip.replace(/\s+/g, ' '), { x: M, y: 0.8, w: 6, h: 0.4, margin: 0,
        fontFace: KR, fontSize: 15, bold: true, color: BRAND, charSpacing: 1.1 });
      s.addText(p.head, { x: M, y: 5.62, w: W - M * 2, h: 0.7, margin: 0,
        fontFace: KRH, fontSize: fitSize(p.head, 34, 0.5, 24), bold: true, color: WHITE, charSpacing: -0.8 });
      return;
    }
    s.addImage({ path: p.image, x: 0, y: 0, w: W, h: H, sizing: { type: 'cover', w: W, h: H } });
    scrim(s);
    if (T.topBar) rect(s, { x: 0, y: 0, w: W, h: 0.12, fill: { color: BRAND } });
    kicker(s, p.chip.replace(/\s+/g, ' '));
    s.addText(p.head, { x: M, y: 4.12, w: W - M * 2, h: 0.95, margin: 0,
      fontFace: KRH, fontSize: fitSize(p.head, 42, 0.55, 28), bold: true, color: 'FFFFFF', charSpacing: -1.2 });
    s.addText(p.body.split('(')[0].trim(), { x: M, y: 5.08, w: W - M * 2, h: 0.6, margin: 0,
      fontFace: KR, fontSize: 19, color: 'D5D8DD', charSpacing: -0.4 });
  },

  /* 개요 — 좌측 이미지 블리드 + 우측 키/값 */
  overview(p) {
    const s = pres.addSlide();
    s.background = { color: INK };
    const imgW = 5.6;
    if (p.image) s.addImage({ path: p.image, x: 0, y: 0, w: imgW, h: H, sizing: { type: 'cover', w: imgW, h: H } });
    rect(s, { x: imgW, y: 0, w: W - imgW, h: H, fill: { color: INK } });
    rect(s, { x: imgW, y: 0, w: 0.04, h: H, fill: { color: BRAND } });
    const x = imgW + 0.7;
    s.addText('단지 개요', { x, y: 0.9, w: W - x - 0.6, h: 0.8, margin: 0,
      fontFace: KR, fontSize: 40, bold: true, color: WHITE, charSpacing: -1.2 });
    let y = 2.05;
    for (const [k, v] of p.rows.slice(0, 6)) {
      s.addText(k, { x, y, w: 1.9, h: 0.5, valign: 'middle', margin: 0,
        fontFace: KR, fontSize: 16, bold: true, color: BRAND, charSpacing: -0.2 });
      s.addText(String(v), { x: x + 1.95, y, w: W - x - 2.5, h: 0.5, valign: 'middle', margin: 0,
        fontFace: KR, fontSize: 19, color: WHITE, charSpacing: -0.4 });
      y += 0.62;
      if (y > SAFE_Y - 0.6) break;
    }
  },

  /* 가격 — 거대 숫자 2분할 */
  price(p) {
    const s = pres.addSlide();
    head(s, '비용', '그래서, 얼마냐면요');
    const half = (W - M * 2) / 2;
    [['보증금', p.deposit, BRAND], ['월 임대료', p.rent, WHITE]].forEach(([label, val, col], i) => {
      const x = M + i * half;
      if (i) rect(s, { x: x - 0.02, y: 2.66, w: 0.02, h: 1.9, fill: { color: LINE } });
      s.addText(label, { x: x + 0.06, y: 2.62, w: half - 0.4, h: 0.45, margin: 0,
        fontFace: KR, fontSize: 18, bold: true, color: DIM, charSpacing: -0.2 });
      s.addText(String(val).replace(/\s*~$/, ''), { x: x + 0.04, y: 3.08, w: half - 0.3, h: 1.35, margin: 0,
        fontFace: KR, fontSize: fitSize(String(val), 66, 3.2, 34), bold: true, color: col, charSpacing: -2.4 });
    });
    footline(s, '보증금을 올리면 월세를 낮추는 전환형 — 자격·조건은 최신 모집공고문 기준');
  },

  /* 평점 — 게이지 바 (별점 표·설명문 없이 점수만; 설명은 내레이션이 한다) */
  rating(p) {
    const s = pres.addSlide();
    head(s, '예린이의 평가', `뽀개기 총점  ${p.total.toFixed(1)} / 5.0`);
    s.addText(p.comment.replace(/^"|"$/g, ''), { x: M, y: 2.24, w: W - M * 2, h: 0.5, margin: 0,
      fontFace: KR, fontSize: 18, color: DIM, charSpacing: -0.4 });
    const barX = 4.6, barW = W - barX - M - 1.15;
    let y = 3.02;
    for (const [name, score] of p.rows.slice(0, 5)) {
      s.addText(name, { x: M, y: y - 0.08, w: 3.5, h: 0.5, valign: 'middle', margin: 0,
        fontFace: KR, fontSize: 20, bold: true, color: WHITE, charSpacing: -0.4 });
      rect(s, { x: barX, y: y + 0.06, w: barW, h: 0.28, fill: { color: INK2 } });
      rect(s, { x: barX, y: y + 0.06, w: barW * (score / 5), h: 0.28,
        fill: { color: score >= 4.5 ? BRAND : BRAND_L } });
      s.addText(score.toFixed(1), { x: barX + barW + 0.25, y: y - 0.08, w: 0.9, h: 0.5,
        valign: 'middle', margin: 0, fontFace: KR, fontSize: 24, bold: true, color: WHITE });
      y += 0.56;
    }
  },

  /* 총평 — 좌(오렌지) / 우(잉크) 색면 대비 */
  verdict(p) {
    const s = pres.addSlide();
    s.background = { color: INK };
    const half = W / 2;
    rect(s, { x: 0, y: 0, w: half, h: SAFE_Y + 0.4, fill: { color: BRAND } });
    rect(s, { x: half, y: 0, w: half, h: SAFE_Y + 0.4, fill: { color: INK2 } });
    const col = (x, label, items, labelColor, textColor) => {
      s.addText(label, { x: x + 0.7, y: 0.86, w: half - 1.3, h: 0.6, margin: 0,
        fontFace: KR, fontSize: 30, bold: true, color: labelColor, charSpacing: -1 });
      let y = 1.86;
      for (const t of items.slice(0, 4)) {
        rect(s, { x: x + 0.7, y: y + 0.16, w: 0.16, h: 0.16, fill: { color: labelColor } });
        s.addText(t, { x: x + 1.0, y, w: half - 1.75, h: 0.86, margin: 0,
          fontFace: KR, fontSize: 18, color: textColor, charSpacing: -0.4, lineSpacingMultiple: 1.12 });
        y += 0.92;
      }
    };
    col(0, '이건 좋았다', p.pros, '2A1200', 'FFF0E4');
    col(half, '이건 따져보자', p.cons, BRAND, 'D5D8DD');
    s.addText(p.closing.replace(/^"|"$/g, ''), { x: M, y: SAFE_Y - 0.55, w: W - M * 2, h: 0.7, align: 'center', margin: 0,
      fontFace: KR, fontSize: 22, bold: true, color: WHITE, charSpacing: -0.6 });
  },
};

for (const slide of spec.slides) R[slide.type](slide);
pres.writeFile({ fileName: outPath }).then(() => console.log('deck written', outPath, spec.slides.length, 'slides'));
