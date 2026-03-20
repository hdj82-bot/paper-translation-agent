"""부분 재조립 — 수정된 섹션만 PDF 재생성"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def partial_reassemble(section_ids: list):
    """지정된 섹션만 재번역 결과를 반영하여 PDF 재조립"""
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    translated_dir = PROJECT_ROOT / "output" / "translated"
    meta_path = output_dir / "layout_metadata.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 수정된 섹션 확인
    chunks_dir = output_dir / "chunks"
    modified_sections = []

    for sid in section_ids:
        translated_path = chunks_dir / f"{sid}_translated.json"
        if translated_path.exists():
            modified_sections.append(sid)
            print(f"[정보] 수정된 섹션 감지: {sid}")
        else:
            print(f"[경고] 번역 파일을 찾을 수 없습니다: {sid}", file=sys.stderr)

    if not modified_sections:
        print("[오류] 수정된 섹션이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 전체 재조립 (assemble_pdf.py와 동일한 로직 사용)
    # 간단한 구현: 원문 PDF 경로를 찾아 assemble_pdf 호출
    source_file = metadata.get("source_file", "")
    if not source_file or not Path(source_file).exists():
        # input/ 디렉토리에서 찾기
        input_dir = PROJECT_ROOT / "input"
        pdfs = list(input_dir.glob("*.pdf"))
        if pdfs:
            source_file = str(pdfs[0])
        else:
            print("[오류] 원문 PDF 파일을 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)

    print(f"[정보] 전체 PDF 재조립 시작 (수정 섹션: {', '.join(modified_sections)})")

    # assemble_pdf 모듈 호출
    sys.path.insert(0, str(Path(__file__).parent))
    from assemble_pdf import assemble_pdf
    assemble_pdf(source_file)

    print(f"[완료] 부분 재조립 완료")


def main():
    parser = argparse.ArgumentParser(description="부분 섹션 재조립")
    parser.add_argument(
        "--sections",
        required=True,
        help="재조립할 섹션 ID (쉼표 구분, 예: 02_introduction,04_results)"
    )
    args = parser.parse_args()

    section_ids = [s.strip() for s in args.sections.split(",") if s.strip()]
    partial_reassemble(section_ids)


if __name__ == "__main__":
    main()
