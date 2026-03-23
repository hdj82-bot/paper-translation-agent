"""PDF 기본 메타데이터 추출 — 페이지 수, 페이지 크기, 텍스트 레이어 존재 여부"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import configure_pytesseract, get_poppler_path

configure_pytesseract()


def get_ocr_text(pdf_path: str, page_num: int) -> str:
    """텍스트 레이어가 없는 페이지에서 OCR로 텍스트 추출"""
    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1, dpi=300,
                                   poppler_path=get_poppler_path())
        if images:
            return pytesseract.image_to_string(images[0], lang="eng")
    except ImportError:
        print("[경고] pdf2image 또는 pytesseract가 설치되지 않았습니다. OCR을 건너뜁니다.", file=sys.stderr)
    except Exception as e:
        print(f"[경고] 페이지 {page_num + 1} OCR 실패: {e}", file=sys.stderr)
    return ""


def extract_metadata(pdf_path: str) -> dict:
    import pdfplumber

    pdf_path = str(Path(pdf_path).resolve())

    if not os.path.exists(pdf_path):
        print(f"[오류] PDF 파일을 찾을 수 없습니다: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    metadata = {
        "source_file": pdf_path,
        "pages": 0,
        "page_sizes": [],
        "page_ocr_status": {},
    }

    with pdfplumber.open(pdf_path) as pdf:
        metadata["pages"] = len(pdf.pages)

        for i, page in enumerate(pdf.pages):
            page_num_str = str(i + 1)
            metadata["page_sizes"].append({
                "width": float(page.width),
                "height": float(page.height),
            })

            text = page.extract_text() or ""
            if len(text.strip()) > 20:
                metadata["page_ocr_status"][page_num_str] = "text_layer"
            else:
                ocr_text = get_ocr_text(pdf_path, i)
                if len(ocr_text.strip()) > 20:
                    metadata["page_ocr_status"][page_num_str] = "ocr_fallback"
                    print(f"[정보] 페이지 {page_num_str}: 텍스트 레이어 없음 → OCR 폴백 적용", file=sys.stderr)
                else:
                    metadata["page_ocr_status"][page_num_str] = "no_text"
                    print(f"[경고] 페이지 {page_num_str}: 텍스트를 추출할 수 없습니다", file=sys.stderr)

    return metadata


def main():
    parser = argparse.ArgumentParser(description="PDF 기본 메타데이터 추출")
    parser.add_argument("pdf_path", help="분석할 PDF 파일 경로")
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / "output" / "intermediate"
    output_dir.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "output" / "checkpoints").mkdir(parents=True, exist_ok=True)

    metadata = extract_metadata(args.pdf_path)

    output_path = output_dir / "layout_metadata.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"[완료] 메타데이터 저장: {output_path}")
    print(f"  - 총 페이지: {metadata['pages']}")
    ocr_count = sum(1 for v in metadata["page_ocr_status"].values() if v == "ocr_fallback")
    if ocr_count:
        print(f"  - OCR 폴백 페이지: {ocr_count}개")


if __name__ == "__main__":
    main()
