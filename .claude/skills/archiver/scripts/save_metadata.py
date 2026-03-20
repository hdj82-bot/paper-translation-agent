"""번역 PDF 아카이빙 및 메타데이터 JSON 저장"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def save_metadata():
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    translated_dir = PROJECT_ROOT / "output" / "translated"
    archive_dir = PROJECT_ROOT / "output" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    meta_path = output_dir / "layout_metadata.json"
    filename_path = output_dir / "archive_filename.txt"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    if not filename_path.exists():
        print("[오류] archive_filename.txt가 없습니다. generate_filename.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    with open(filename_path, "r", encoding="utf-8") as f:
        archive_filename = f.read().strip()

    # 번역 PDF 찾기
    translated_pdfs = list(translated_dir.glob("*_translated.pdf"))
    if not translated_pdfs:
        print("[오류] 번역된 PDF 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    translated_pdf = translated_pdfs[0]

    # 아카이브로 복사
    archive_pdf_path = archive_dir / f"{archive_filename}.pdf"
    shutil.copy2(str(translated_pdf), str(archive_pdf_path))

    # 번역된 제목 추출 시도
    translated_title = "N/A"
    chunks_dir = output_dir / "chunks"
    # 첫 번째 번역 청크에서 제목 텍스트 찾기
    for chunk_file in sorted(chunks_dir.glob("*_translated.json")):
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunk = json.load(f)
        blocks = chunk.get("blocks", [])
        if blocks:
            translated_title = blocks[0].get("translated_text", "N/A")[:200]
            break

    # 섹션 목록 분류
    sections = metadata.get("sections", [])
    sections_translated = [s["name"] for s in sections if s.get("translate", True)]
    sections_preserved = [s["name"] for s in sections if not s.get("translate", True)]

    # 원문 제목 추출
    original_title = "N/A"
    text_blocks = metadata.get("text_blocks", [])
    body_blocks = [b for b in text_blocks if not b.get("is_header_footer", False)]
    if body_blocks:
        avg_size = sum(b["font_size"] for b in body_blocks) / len(body_blocks)
        for block in body_blocks:
            if block["page"] == 1 and block["font_size"] > avg_size * 1.3:
                original_title = block["text"].strip()
                break

    # 번역 PDF 페이지 수
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(archive_pdf_path))
        pages_translated = len(reader.pages)
    except Exception:
        pages_translated = -1

    # 메타데이터 JSON 생성
    meta = {
        "original_file": metadata.get("source_file", ""),
        "translated_file": str(archive_pdf_path),
        "translation_date": datetime.now().strftime("%Y-%m-%d"),
        "original_title": original_title,
        "translated_title": translated_title,
        "pages_original": metadata.get("pages", 0),
        "pages_translated": pages_translated,
        "sections_translated": sections_translated,
        "sections_preserved": sections_preserved,
    }

    meta_json_path = archive_dir / f"{archive_filename}_meta.json"
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[완료] 아카이빙 완료")
    print(f"  - PDF: {archive_pdf_path}")
    print(f"  - 메타데이터: {meta_json_path}")
    print(str(archive_pdf_path))


def main():
    save_metadata()


if __name__ == "__main__":
    main()
