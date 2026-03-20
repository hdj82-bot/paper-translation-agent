"""섹션 헤딩 감지 — 논문 구조를 파악하여 섹션 목록 생성"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]

KNOWN_SECTIONS = [
    "abstract", "introduction", "related work", "background",
    "method", "methodology", "methods", "approach", "proposed method",
    "experimental", "experiments", "experiment", "experimental setup",
    "results", "result", "evaluation",
    "discussion", "analysis",
    "conclusion", "conclusions", "concluding remarks",
    "future work",
    "references", "bibliography",
    "appendix", "appendices", "supplementary", "supplementary material",
    "acknowledgment", "acknowledgments", "acknowledgement", "acknowledgements",
]

NO_TRANSLATE_SECTIONS = [
    "references", "bibliography", "appendix", "appendices",
    "supplementary", "supplementary material",
]

HEADING_NUMBER_PATTERN = re.compile(
    r"^(?:\d+\.?\s+|[IVX]+\.?\s+|[A-Z]\.?\s+)"
)


def detect_sections():
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    meta_path = output_dir / "layout_metadata.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다. detect_layout.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    text_blocks = metadata.get("text_blocks", [])
    if not text_blocks:
        print("[오류] 텍스트 블록이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 본문 평균 폰트 크기 계산 (헤더/푸터 제외)
    body_blocks = [b for b in text_blocks if not b.get("is_header_footer", False)]
    if not body_blocks:
        print("[오류] 본문 텍스트 블록이 없습니다.", file=sys.stderr)
        sys.exit(1)

    font_sizes = [b["font_size"] for b in body_blocks]
    avg_font_size = sum(font_sizes) / len(font_sizes)

    sections = []
    section_idx = 0

    for block in body_blocks:
        text = block["text"].strip()
        if not text or len(text) > 200:  # 너무 긴 텍스트는 헤딩이 아님
            continue

        is_heading = False
        clean_text = text

        # 번호 패턴 제거하여 이름 추출
        clean_text = HEADING_NUMBER_PATTERN.sub("", text).strip()

        # 기준 1: 알려진 섹션명 매칭
        text_lower = clean_text.lower()
        for known in KNOWN_SECTIONS:
            if text_lower == known or text_lower.startswith(known + ":") or text_lower.startswith(known + "."):
                is_heading = True
                break

        # 기준 2: 폰트 크기가 평균보다 큰 경우 + 짧은 텍스트
        if not is_heading and block["font_size"] > avg_font_size * 1.15 and len(text) < 80:
            # 번호 패턴이 있으면 헤딩일 가능성 높음
            if HEADING_NUMBER_PATTERN.match(text):
                is_heading = True
            # 대문자로 시작하고 짧은 텍스트
            elif text[0].isupper() and len(text.split()) <= 8:
                is_heading = True

        # 기준 3: 전체 대문자 텍스트 (ABSTRACT, INTRODUCTION 등)
        if not is_heading and text.isupper() and len(text) < 60 and len(text.split()) <= 6:
            clean_text = text.title()
            text_lower = clean_text.lower()
            for known in KNOWN_SECTIONS:
                if text_lower == known:
                    is_heading = True
                    break

        if is_heading:
            section_idx += 1
            section_name = clean_text.strip(":. ")

            # 표준화된 이름으로 chunk_id 생성
            safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", section_name.lower()).strip("_")
            chunk_id = f"{section_idx:02d}_{safe_name}"

            # 번역 여부 결정
            translate = True
            for no_trans in NO_TRANSLATE_SECTIONS:
                if text_lower.startswith(no_trans):
                    translate = False
                    break

            sections.append({
                "name": section_name,
                "pages": [block["page"]],
                "chunk_id": chunk_id,
                "translate": translate,
                "heading_block_id": block["id"],
            })

    # 각 섹션의 페이지 범위 계산 (다음 섹션 시작 페이지까지)
    for i, sec in enumerate(sections):
        start_page = sec["pages"][0]
        if i + 1 < len(sections):
            end_page = sections[i + 1]["pages"][0]
        else:
            end_page = metadata["pages"]
        sec["pages"] = list(range(start_page, end_page + 1))

    metadata["sections"] = sections

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"[완료] 섹션 감지 완료: {len(sections)}개 섹션")
    for sec in sections:
        status = "번역" if sec["translate"] else "원문 유지"
        pages = f"p.{sec['pages'][0]}" if len(sec["pages"]) == 1 else f"p.{sec['pages'][0]}-{sec['pages'][-1]}"
        print(f"  - [{status}] {sec['name']} ({pages})")


def main():
    parser = argparse.ArgumentParser(description="논문 섹션 헤딩 감지")
    parser.add_argument("pdf_path", nargs="?", help="PDF 파일 경로 (사용하지 않지만 호환성 위해 유지)")
    args = parser.parse_args()
    detect_sections()


if __name__ == "__main__":
    main()
