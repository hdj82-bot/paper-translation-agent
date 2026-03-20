"""텍스트 블록 추출 및 읽기 순서 정렬, 시각 요소 영역 필터링"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def blocks_overlap(bbox1, bbox2, threshold=0.5):
    """두 bbox가 겹치는지 확인 (overlap ratio 기준)"""
    x0 = max(bbox1[0], bbox2[0])
    y0 = max(bbox1[1], bbox2[1])
    x1 = min(bbox1[2], bbox2[2])
    y1 = min(bbox1[3], bbox2[3])

    if x0 >= x1 or y0 >= y1:
        return False

    overlap_area = (x1 - x0) * (y1 - y0)
    block1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])

    if block1_area == 0:
        return False

    return (overlap_area / block1_area) > threshold


def extract_text_blocks(pdf_path: str):
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    meta_path = output_dir / "layout_metadata.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 시각 요소 영역 로드
    manifest_path = output_dir / "visual_manifest.json"
    visual_bboxes = []
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        visual_bboxes = [
            {"page": v["page"], "bbox": v["bbox"]}
            for v in manifest.get("visuals", [])
        ]

    text_blocks = metadata.get("text_blocks", [])
    layout_type = metadata.get("layout_type", "1-column")

    # 헤더/푸터 제외
    filtered_blocks = [b for b in text_blocks if not b.get("is_header_footer", False)]

    # 시각 요소 영역과 겹치는 블록 제외 (단, 캡션은 유지)
    clean_blocks = []
    for block in filtered_blocks:
        is_in_visual = False
        for vb in visual_bboxes:
            if block["page"] == vb["page"] and blocks_overlap(block["bbox"], vb["bbox"]):
                is_in_visual = True
                break

        if not is_in_visual:
            clean_blocks.append(block)

    # 읽기 순서 정렬
    if layout_type == "2-column":
        # 2컬럼: 전폭 요소는 그대로, 컬럼 요소는 좌→우, 각 컬럼 내 상→하
        def sort_key(block):
            page = block["page"]
            bbox = block["bbox"]
            if block.get("is_full_width", False):
                return (page, bbox[1], 0)
            else:
                column = block.get("column", 1)
                return (page, column, bbox[1])
    else:
        # 1컬럼: 페이지 순 → Y좌표 순
        def sort_key(block):
            return (block["page"], block["bbox"][1])

    clean_blocks.sort(key=sort_key)

    # ID 재부여
    for i, block in enumerate(clean_blocks):
        block["id"] = f"tb_{i + 1:03d}"

    # 메타데이터 업데이트
    metadata["text_blocks"] = clean_blocks

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"[완료] 텍스트 블록 정리 완료")
    print(f"  - 전체 블록: {len(text_blocks)}개")
    print(f"  - 필터링 후: {len(clean_blocks)}개")
    print(f"  - 제외된 블록: {len(text_blocks) - len(clean_blocks)}개 (헤더/푸터/시각 요소 영역)")


def main():
    parser = argparse.ArgumentParser(description="텍스트 블록 추출 및 정렬")
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    args = parser.parse_args()
    extract_text_blocks(args.pdf_path)


if __name__ == "__main__":
    main()
