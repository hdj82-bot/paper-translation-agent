"""번역된 텍스트 + 시각 요소로 최종 한국어 PDF 생성"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def wrap_text(text, font_name, font_size, max_width, canvas_obj):
    """텍스트를 주어진 너비에 맞게 줄바꿈"""
    from reportlab.lib.units import mm

    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        width = canvas_obj.stringWidth(test_line, font_name, font_size)
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    return lines


def assemble_pdf(original_pdf_path: str):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as canvas_module
    from pypdf import PdfReader, PdfWriter, PdfMerger
    import io

    original_pdf_path = str(Path(original_pdf_path).resolve())
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    translated_dir = PROJECT_ROOT / "output" / "translated"
    translated_dir.mkdir(parents=True, exist_ok=True)

    meta_path = output_dir / "layout_metadata.json"
    manifest_path = output_dir / "visual_manifest.json"
    chunks_dir = output_dir / "chunks"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    manifest = {"visuals": []}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    # 폰트 준비
    font_path = None
    fonts_dir = PROJECT_ROOT / "fonts"
    for ext in ["*.ttf", "*.otf"]:
        found = list(fonts_dir.glob(ext))
        if found:
            font_path = found[0]
            break

    if not font_path:
        print("[오류] 한국어 폰트를 찾을 수 없습니다. embed_korean_font.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    ko_font_name = font_path.stem
    try:
        pdfmetrics.registerFont(TTFont(ko_font_name, str(font_path)))
    except Exception as e:
        print(f"[오류] 폰트 등록 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # 번역된 청크 로드
    translated_chunks = {}
    preserved_chunks = {}

    for chunk_file in sorted(chunks_dir.glob("*_translated.json")):
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunk = json.load(f)
        translated_chunks[chunk["chunk_id"]] = chunk

    for chunk_file in sorted(chunks_dir.glob("*.json")):
        if "_translated" in chunk_file.name:
            continue
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunk = json.load(f)
        if not chunk.get("translate", True):
            preserved_chunks[chunk["chunk_id"]] = chunk

    # 페이지 크기
    page_sizes = metadata.get("page_sizes", [{"width": 612, "height": 792}])
    sections = metadata.get("sections", [])

    # 원문 유지 섹션의 페이지 번호 수집
    preserved_pages = set()
    for sec in sections:
        if not sec.get("translate", True):
            for p in sec.get("pages", []):
                preserved_pages.add(p)

    # 번역된 페이지의 블록을 페이지별로 그룹핑
    page_blocks = {}
    for chunk in translated_chunks.values():
        for block in chunk.get("blocks", []):
            page = block.get("page", 1)
            if page not in page_blocks:
                page_blocks[page] = []
            page_blocks[page].append(block)

    # 시각 요소를 페이지별로 그룹핑
    page_visuals = {}
    for visual in manifest.get("visuals", []):
        page = visual.get("page", 1)
        if page not in page_visuals:
            page_visuals[page] = []
        page_visuals[page].append(visual)

    # PDF 생성
    total_pages = metadata.get("pages", 1)
    output_filename = Path(original_pdf_path).stem + "_translated.pdf"
    output_path = translated_dir / output_filename

    # reportlab으로 번역 페이지 생성
    translated_pdf_buffer = io.BytesIO()
    first_page_size = page_sizes[0] if page_sizes else {"width": 612, "height": 792}
    c = canvas_module.Canvas(
        translated_pdf_buffer,
        pagesize=(first_page_size["width"], first_page_size["height"]),
    )

    translated_page_map = {}  # original_page -> translated_page_index

    for page_num in range(1, total_pages + 1):
        if page_num in preserved_pages:
            continue

        page_size = page_sizes[page_num - 1] if page_num <= len(page_sizes) else first_page_size
        pw = page_size["width"]
        ph = page_size["height"]
        c.setPageSize((pw, ph))

        blocks = page_blocks.get(page_num, [])
        visuals = page_visuals.get(page_num, [])
        # 컬럼별 y_offset 분리 (2컬럼 레이아웃 지원)
        y_offset_by_col = {1: 0, 2: 0}

        # 블록을 컬럼 우선, Y좌표 순으로 정렬 (읽기 순서 유지)
        layout_type = metadata.get("layout_type", "1-column")
        if layout_type == "2-column":
            blocks.sort(key=lambda b: (b.get("column", 1), b["bbox"][1]))
        else:
            blocks.sort(key=lambda b: b["bbox"][1])

        for block in blocks:
            bbox = block["bbox"]
            x0, y0_orig, x1, y1_orig = bbox

            # reportlab은 좌하단이 원점 (PDF 좌표 변환)
            text = block.get("translated_text", block.get("original_text", ""))
            if not text:
                continue

            font_size = block.get("font_size", 10)
            max_width = x1 - x0

            # 텍스트 줄바꿈
            lines = wrap_text(text, ko_font_name, font_size, max_width, c)
            line_height = font_size * 1.4

            # 원래 높이 vs 필요 높이
            original_height = y1_orig - y0_orig
            needed_height = len(lines) * line_height
            extra = max(0, needed_height - original_height)

            # reportlab Y좌표: 페이지 하단에서 위로
            col = block.get("column", 1)
            y_offset = y_offset_by_col.get(col, 0)
            y_start = ph - (y0_orig + y_offset) - font_size

            c.setFont(ko_font_name, font_size)
            for i, line in enumerate(lines):
                y_pos = y_start - (i * line_height)
                if y_pos < 30:  # 페이지 하단에 도달하면 새 페이지
                    c.showPage()
                    c.setPageSize((pw, ph))
                    c.setFont(ko_font_name, font_size)
                    y_pos = ph - 50
                    y_start = y_pos + (i * line_height)
                c.drawString(x0, y_pos, line)

            y_offset_by_col[col] = y_offset_by_col.get(col, 0) + extra

        # 시각 요소 삽입
        max_y_offset = max(y_offset_by_col.values()) if y_offset_by_col else 0
        for visual in visuals:
            img_path = PROJECT_ROOT / visual["image_path"]
            if not img_path.exists():
                continue

            vbbox = visual["bbox"]
            vx0 = vbbox[0]
            vy0 = vbbox[1] + max_y_offset
            vw = vbbox[2] - vbbox[0]
            vh = vbbox[3] - vbbox[1]

            # reportlab Y좌표 변환
            vy_rl = ph - vy0 - vh

            try:
                c.drawImage(str(img_path), vx0, vy_rl, width=vw, height=vh, preserveAspectRatio=True)
            except Exception as e:
                print(f"[경고] 이미지 삽입 실패 ({visual['id']}): {e}", file=sys.stderr)

        c.showPage()

    c.save()

    # 원문 유지 페이지와 번역 페이지 합치기
    translated_pdf_buffer.seek(0)
    translated_reader = PdfReader(translated_pdf_buffer)
    original_reader = PdfReader(original_pdf_path)

    writer = PdfWriter()
    translated_page_idx = 0

    for page_num in range(1, total_pages + 1):
        if page_num in preserved_pages:
            # 원문 페이지 그대로 사용
            writer.add_page(original_reader.pages[page_num - 1])
        else:
            # 번역 페이지 사용
            if translated_page_idx < len(translated_reader.pages):
                writer.add_page(translated_reader.pages[translated_page_idx])
                translated_page_idx += 1

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"[완료] 번역 PDF 생성: {output_path}")
    print(f"  - 총 페이지: {len(writer.pages)}")
    print(f"  - 번역 페이지: {translated_page_idx}")
    print(f"  - 원문 유지 페이지: {len(preserved_pages)}")


def main():
    parser = argparse.ArgumentParser(description="번역 PDF 조립")
    parser.add_argument("pdf_path", help="원문 PDF 파일 경로")
    args = parser.parse_args()
    assemble_pdf(args.pdf_path)


if __name__ == "__main__":
    main()
