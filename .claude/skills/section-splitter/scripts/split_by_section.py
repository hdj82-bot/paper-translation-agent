"""섹션별 청크 파일 생성"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def split_by_section():
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    meta_path = output_dir / "layout_metadata.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    sections = metadata.get("sections", [])
    text_blocks = metadata.get("text_blocks", [])

    if not sections:
        print("[오류] 섹션 정보가 없습니다. detect_sections.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    if not text_blocks:
        print("[오류] 텍스트 블록이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 섹션 헤딩 블록 ID로 경계 파악
    heading_block_ids = []
    for sec in sections:
        hid = sec.get("heading_block_id")
        if hid:
            heading_block_ids.append(hid)

    # 각 섹션에 블록 할당
    chunk_files = []
    total_assigned = 0

    for sec_idx, section in enumerate(sections):
        heading_id = section.get("heading_block_id")
        section_pages = set(section.get("pages", []))

        # 다음 섹션의 헤딩 블록 ID 찾기
        next_heading_id = None
        if sec_idx + 1 < len(sections):
            next_heading_id = sections[sec_idx + 1].get("heading_block_id")

        # 이 섹션에 속하는 블록 수집
        section_blocks = []
        in_section = False

        for block in text_blocks:
            # 헤딩 블록부터 시작
            if block["id"] == heading_id:
                in_section = True

            # 다음 섹션 헤딩 블록이면 중단
            if next_heading_id and block["id"] == next_heading_id:
                break

            if in_section:
                section_blocks.append({
                    "id": block["id"],
                    "page": block["page"],
                    "bbox": block["bbox"],
                    "column": block.get("column", 1),
                    "font_size": block.get("font_size", 10),
                    "original_text": block["text"],
                })

        # 헤딩 블록이 없는 경우 (첫 번째 섹션 등) 페이지 기반 할당
        if not section_blocks and not heading_id:
            for block in text_blocks:
                if block["page"] in section_pages:
                    already_assigned = any(
                        block["id"] in [b["id"] for b in cf_blocks]
                        for cf_blocks in [[] for _ in chunk_files]
                    )
                    if not already_assigned:
                        section_blocks.append({
                            "id": block["id"],
                            "page": block["page"],
                            "bbox": block["bbox"],
                            "column": block.get("column", 1),
                            "font_size": block.get("font_size", 10),
                            "original_text": block["text"],
                        })

        chunk = {
            "chunk_id": section["chunk_id"],
            "section_name": section["name"],
            "translate": section.get("translate", True),
            "blocks": section_blocks,
        }

        chunk_path = chunks_dir / f"{section['chunk_id']}.json"
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=2)

        chunk_files.append(chunk_path)
        total_assigned += len(section_blocks)

    # 커버리지 검증
    total_blocks = len(text_blocks)
    coverage = (total_assigned / total_blocks * 100) if total_blocks > 0 else 0

    print(f"[완료] 섹션별 청크 파일 생성 완료")
    print(f"  - 생성된 청크: {len(chunk_files)}개")
    print(f"  - 텍스트 블록 커버리지: {coverage:.1f}% ({total_assigned}/{total_blocks})")

    if coverage < 98:
        print(f"  [경고] 커버리지가 98% 미만입니다. 일부 텍스트 블록이 할당되지 않았을 수 있습니다.", file=sys.stderr)

    for chunk_path in chunk_files:
        with open(chunk_path, "r", encoding="utf-8") as f:
            chunk = json.load(f)
        status = "번역" if chunk["translate"] else "원문 유지"
        print(f"  - [{status}] {chunk['section_name']}: {len(chunk['blocks'])}개 블록")


def main():
    split_by_section()


if __name__ == "__main__":
    main()
