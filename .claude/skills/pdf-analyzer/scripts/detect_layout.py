"""레이아웃 감지 — 1/2컬럼 판단, 폰트 스타일, 헤더/푸터 필터링, 텍스트 블록 추출"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import get_intermediate_dir


def detect_layout(pdf_path: str):
    import pdfplumber

    pdf_path = str(Path(pdf_path).resolve())
    output_dir = get_intermediate_dir()
    meta_path = output_dir / "layout_metadata.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다. extract_metadata.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    text_blocks = []
    font_names = Counter()
    font_sizes = []
    block_id = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            page_width = float(page.width)
            page_height = float(page.height)

            header_threshold = page_height * 0.05
            footer_threshold = page_height * 0.95

            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
                keep_blank_chars=False,
                extra_attrs=["fontname", "size"],
            )

            if not words:
                continue

            # 단어를 라인으로 그룹핑 (Y좌표 근접성)
            lines = []
            current_line = [words[0]]
            for w in words[1:]:
                if abs(float(w["top"]) - float(current_line[-1]["top"])) < 5:
                    current_line.append(w)
                else:
                    lines.append(current_line)
                    current_line = [w]
            lines.append(current_line)

            # 라인을 단락으로 그룹핑 (Y 간격)
            paragraphs = []
            current_para = [lines[0]]
            for line in lines[1:]:
                prev_bottom = max(float(w["bottom"]) for w in current_para[-1])
                curr_top = min(float(w["top"]) for w in line)
                gap = curr_top - prev_bottom

                avg_line_height = sum(
                    float(w["bottom"]) - float(w["top"]) for w in line
                ) / len(line)

                if gap > avg_line_height * 1.5:
                    paragraphs.append(current_para)
                    current_para = [line]
                else:
                    current_para.append(line)
            paragraphs.append(current_para)

            # 각 단락을 텍스트 블록으로 변환
            for para in paragraphs:
                all_words = [w for line in para for w in line]
                if not all_words:
                    continue

                x0 = min(float(w["x0"]) for w in all_words)
                y0 = min(float(w["top"]) for w in all_words)
                x1 = max(float(w["x1"]) for w in all_words)
                y1 = max(float(w["bottom"]) for w in all_words)
                text = " ".join(w["text"] for w in all_words)

                # 폰트 정보
                block_fonts = [w.get("fontname", "") for w in all_words if w.get("fontname")]
                block_sizes = [float(w.get("size", 10)) for w in all_words if w.get("size")]
                main_font = Counter(block_fonts).most_common(1)[0][0] if block_fonts else "Unknown"
                avg_size = sum(block_sizes) / len(block_sizes) if block_sizes else 10.0

                for fn in block_fonts:
                    font_names[fn] += 1
                font_sizes.extend(block_sizes)

                # 헤더/푸터 판단
                is_header_footer = y0 < header_threshold or y1 > footer_threshold

                # 컬럼 판단 (페이지 중심 기준)
                block_center_x = (x0 + x1) / 2
                column = 1 if block_center_x < page_width / 2 else 2

                # 전폭 판단
                block_width = x1 - x0
                is_full_width = block_width >= page_width * 0.6

                block_id += 1
                text_blocks.append({
                    "id": f"tb_{block_id:03d}",
                    "page": page_num,
                    "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    "column": 1 if is_full_width else column,
                    "font_size": round(avg_size, 1),
                    "font_name": main_font,
                    "is_header_footer": is_header_footer,
                    "is_full_width": is_full_width,
                    "text": text,
                })

    # 레이아웃 타입 판단: 2컬럼 여부
    non_hf_blocks = [b for b in text_blocks if not b["is_header_footer"] and not b["is_full_width"]]
    if non_hf_blocks:
        col2_count = sum(1 for b in non_hf_blocks if b["column"] == 2)
        ratio = col2_count / len(non_hf_blocks)
        layout_type = "2-column" if ratio > 0.25 else "1-column"
    else:
        layout_type = "1-column"

    # 폰트 스타일 판단
    serif_keywords = ["times", "serif", "roman", "garamond", "georgia", "cambria", "cmr", "computer modern"]
    most_common_font = font_names.most_common(1)[0][0].lower() if font_names else ""
    is_serif = any(kw in most_common_font for kw in serif_keywords)
    font_style = "serif" if is_serif else "sans-serif"
    target_font = "NotoSerifKR-Regular.otf" if is_serif else "NotoSansKR-Regular.otf"

    # 헤더/푸터 영역 정보
    page_size = metadata.get("page_sizes", [{}])[0] if metadata.get("page_sizes") else {}
    h = page_size.get("height", 842.0)
    header_footer_zones = {
        "header_y_threshold": round(h * 0.05, 1),
        "footer_y_threshold": round(h * 0.95, 1),
    }

    # 메타데이터 업데이트
    metadata["layout_type"] = layout_type
    metadata["font_style"] = font_style
    metadata["target_font"] = target_font
    metadata["header_footer_zones"] = header_footer_zones
    metadata["text_blocks"] = text_blocks

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"[완료] 레이아웃 감지 완료")
    print(f"  - 레이아웃: {layout_type}")
    print(f"  - 폰트 스타일: {font_style} → {target_font}")
    print(f"  - 텍스트 블록: {len(text_blocks)}개")
    hf_count = sum(1 for b in text_blocks if b["is_header_footer"])
    print(f"  - 헤더/푸터 블록: {hf_count}개")


def main():
    parser = argparse.ArgumentParser(description="PDF 레이아웃 감지")
    parser.add_argument("pdf_path", help="분석할 PDF 파일 경로")
    args = parser.parse_args()
    detect_layout(args.pdf_path)


if __name__ == "__main__":
    main()
