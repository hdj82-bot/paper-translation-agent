"""섹션 헤딩 감지 — 논문 구조를 파악하여 섹션 목록 생성"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import get_intermediate_dir

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


def _scan_pdf_for_missed_sections(pdf_path: str, avg_font_size: float, found_pages: set) -> list:
    """pdfplumber로 직접 스캔해 블록 그룹핑에서 누락된 섹션 헤딩 탐색."""
    missed = []
    try:
        import pdfplumber
    except ImportError:
        return missed

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                if page_num in found_pages:
                    continue  # 이미 감지된 페이지는 건너뜀

                words = page.extract_words(extra_attrs=["size"])
                if not words:
                    continue

                # 연속된 단어들을 라인으로 그룹핑
                lines = []
                current = [words[0]]
                for w in words[1:]:
                    if abs(float(w["top"]) - float(current[-1]["top"])) < 4:
                        current.append(w)
                    else:
                        lines.append(current)
                        current = [w]
                lines.append(current)

                for line in lines:
                    line_text = " ".join(w["text"] for w in line).strip()
                    if not line_text or len(line_text) > 80:
                        continue

                    sizes = [float(w.get("size", 10)) for w in line if w.get("size")]
                    avg_line_size = sum(sizes) / len(sizes) if sizes else avg_font_size

                    # 평균보다 큰 폰트 + 알려진 섹션명
                    if avg_line_size <= avg_font_size * 1.05:
                        continue

                    clean = HEADING_NUMBER_PATTERN.sub("", line_text).strip()
                    text_lower = clean.lower()

                    for known in KNOWN_SECTIONS:
                        if text_lower == known or text_lower.startswith(known + " ") or text_lower.startswith(known + ":"):
                            y0 = min(float(w["top"]) for w in line)
                            x0 = min(float(w["x0"]) for w in line)
                            x1 = max(float(w["x1"]) for w in line)
                            y1 = max(float(w["bottom"]) for w in line)
                            missed.append({
                                "name": clean.strip(":. "),
                                "page": page_num,
                                "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                                "text_lower": text_lower,
                            })
                            break
    except Exception as e:
        print(f"[경고] PDF 직접 스캔 실패: {e}", file=sys.stderr)

    return missed


def detect_sections():
    output_dir = get_intermediate_dir()
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

    # 2차 스캔: pdfplumber로 직접 누락된 섹션 탐색
    found_pages = {sec["pages"][0] for sec in sections}
    source_file = metadata.get("source_file", "")
    if source_file:
        missed = _scan_pdf_for_missed_sections(source_file, avg_font_size, found_pages)
        for m in missed:
            # 이미 감지된 섹션명 중복 방지
            already_found = any(
                s["name"].lower() == m["name"].lower() for s in sections
            )
            if already_found:
                continue

            section_idx += 1
            text_lower = m["text_lower"]
            safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", m["name"].lower()).strip("_")
            chunk_id = f"{section_idx:02d}_{safe_name}"

            translate = True
            for no_trans in NO_TRANSLATE_SECTIONS:
                if text_lower.startswith(no_trans):
                    translate = False
                    break

            sections.append({
                "name": m["name"],
                "pages": [m["page"]],
                "chunk_id": chunk_id,
                "translate": translate,
                "heading_block_id": None,
                "heading_bbox": m["bbox"],
            })
            print(f"  [2차 감지] {m['name']} (p.{m['page']})", file=sys.stderr)

        # 페이지 순으로 재정렬
        sections.sort(key=lambda s: s["pages"][0])
        # chunk_id 재부여
        for i, sec in enumerate(sections, 1):
            base = re.sub(r"^\d+_", "", sec["chunk_id"])
            sec["chunk_id"] = f"{i:02d}_{base}"

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
