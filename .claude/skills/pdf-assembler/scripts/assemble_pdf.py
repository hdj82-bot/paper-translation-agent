"""번역된 텍스트 + 시각 요소로 최종 한국어 PDF 생성"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import get_intermediate_dir


def assemble_pdf(original_pdf_path: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, HRFlowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pypdf import PdfReader, PdfWriter
    import io

    original_pdf_path = str(Path(original_pdf_path).resolve())
    output_dir = get_intermediate_dir()
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

    # 원문 폰트 등록 (추출된 경우)
    orig_font_name = None
    orig_font_path_str = metadata.get("original_font_path", "")
    if orig_font_path_str:
        orig_path = Path(orig_font_path_str)
        if orig_path.exists():
            try:
                orig_font_name = orig_path.stem
                pdfmetrics.registerFont(TTFont(orig_font_name, str(orig_path)))
                print(f"[정보] 원문 폰트 등록: {orig_font_name}", file=sys.stderr)
            except Exception as e:
                print(f"[경고] 원문 폰트 등록 실패 ({e}), 한국어 폰트만 사용", file=sys.stderr)
                orig_font_name = None

    # 번역된 청크 로드 — 페이지 순서대로 블록 수집
    all_blocks = []  # [{"page": int, "text": str, "font_size": float, ...}]

    for chunk_file in sorted(chunks_dir.glob("*_translated.json")):
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunk = json.load(f)
        for block in chunk.get("blocks", []):
            text = block.get("translated_text") or block.get("original_text", "")
            if text and text.strip():
                all_blocks.append({
                    "page": block.get("page", 1),
                    "y": block.get("bbox", [0, 0, 0, 0])[1],
                    "text": text.strip(),
                    "font_size": block.get("font_size", 10),
                    "column": block.get("column", 1),
                })

    # 원문 유지 섹션의 페이지 번호
    preserved_pages = set()
    for sec in metadata.get("sections", []):
        if not sec.get("translate", True):
            for p in sec.get("pages", []):
                preserved_pages.add(p)

    # 시각 요소를 페이지별로 그룹핑
    page_visuals = {}
    for visual in manifest.get("visuals", []):
        page = visual.get("page", 1)
        if page not in page_visuals:
            page_visuals[page] = []
        page_visuals[page].append(visual)

    # 블록을 페이지·컬럼·y좌표 순으로 정렬
    all_blocks.sort(key=lambda b: (b["page"], b["column"], b["y"]))

    # reportlab 스타일 설정
    PAGE_W, PAGE_H = A4  # 595 x 842 pt
    MARGIN = 25 * mm
    CONTENT_W = PAGE_W - 2 * MARGIN

    _style_cache: dict = {}

    def pick_style(font_size: float, is_heading: bool = False):
        """원문 폰트 크기를 그대로 사용하는 동적 스타일 반환"""
        fs = max(6.0, round(font_size, 1))
        key = (fs, is_heading)
        if key not in _style_cache:
            leading = fs * 1.45
            space_before = fs * 0.6 if is_heading else 0
            space_after = fs * 0.35
            _style_cache[key] = ParagraphStyle(
                f"Ko_{fs}{'_h' if is_heading else ''}",
                fontName=ko_font_name,
                fontSize=fs,
                leading=leading,
                spaceBefore=space_before,
                spaceAfter=space_after,
                wordWrap="CJK",
                alignment=TA_LEFT,
            )
        return _style_cache[key]

    # flowable 목록 생성
    story = []
    total_pages = metadata.get("pages", 1)
    current_page = 0

    for block in all_blocks:
        page = block["page"]
        if page in preserved_pages:
            continue

        # 페이지 구분선
        if page != current_page:
            if current_page > 0:
                story.append(HRFlowable(width="100%", thickness=0.3, color="grey", spaceAfter=4))
            current_page = page

            # 해당 페이지 시각 요소 삽입 (페이지 첫 블록 앞에)
            for visual in page_visuals.get(page, []):
                img_path = PROJECT_ROOT / visual["image_path"]
                if img_path.exists():
                    try:
                        vbbox = visual["bbox"]
                        vw = vbbox[2] - vbbox[0]
                        vh = vbbox[3] - vbbox[1]
                        # 이미지 크기를 콘텐츠 영역에 맞게 조정
                        scale = min(CONTENT_W / max(vw, 1), 200 / max(vh, 1))
                        img = Image(str(img_path), width=vw * scale, height=vh * scale)
                        story.append(img)
                        story.append(Spacer(1, 4))
                    except Exception as e:
                        print(f"[경고] 이미지 삽입 실패 ({visual['id']}): {e}", file=sys.stderr)

        text = block["text"]
        font_size = block["font_size"]
        is_heading = font_size >= 13
        style = pick_style(font_size, is_heading)
        # XML 특수문자 이스케이프
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        try:
            para = Paragraph(safe_text, style)
            story.append(para)
        except Exception as e:
            print(f"[경고] 단락 생성 실패: {e}", file=sys.stderr)
            story.append(Paragraph("[렌더링 오류]", normal_style))

    if not story:
        story.append(Paragraph("번역된 내용이 없습니다.", normal_style))

    # 번역 페이지 PDF 생성
    translated_pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        translated_pdf_buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    doc.build(story)

    # 원문 유지 페이지와 번역 페이지 합치기
    translated_pdf_buffer.seek(0)
    translated_reader = PdfReader(translated_pdf_buffer)
    original_reader = PdfReader(original_pdf_path)

    writer = PdfWriter()

    # 번역 페이지를 앞에, 원문 유지 페이지를 뒤에 추가
    for page in translated_reader.pages:
        writer.add_page(page)

    for page_num in preserved_pages:
        if page_num - 1 < len(original_reader.pages):
            writer.add_page(original_reader.pages[page_num - 1])

    output_filename = Path(original_pdf_path).stem + "_translated.pdf"
    output_path = translated_dir / output_filename

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"[완료] 번역 PDF 생성: {output_path}")
    print(f"  - 총 페이지: {len(writer.pages)}")
    print(f"  - 번역 블록 수: {len(all_blocks)}")
    print(f"  - 원문 유지 페이지: {len(preserved_pages)}")


def main():
    parser = argparse.ArgumentParser(description="번역 PDF 조립")
    parser.add_argument("pdf_path", help="원문 PDF 파일 경로")
    args = parser.parse_args()
    assemble_pdf(args.pdf_path)


if __name__ == "__main__":
    main()
