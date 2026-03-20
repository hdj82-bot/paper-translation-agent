"""독립 수식 블록 감지 및 이미지 크롭"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def extract_equations(pdf_path: str):
    from pdf2image import convert_from_path

    pdf_path = str(Path(pdf_path).resolve())
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    visuals_dir = output_dir / "visuals" / "equations"
    visuals_dir.mkdir(parents=True, exist_ok=True)

    meta_path = output_dir / "layout_metadata.json"
    manifest_path = output_dir / "visual_manifest.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    manifest = {"visuals": []}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    existing_ids = {v["id"] for v in manifest["visuals"]}
    eq_count = sum(1 for v in manifest["visuals"] if v["type"] == "equation")

    text_blocks = metadata.get("text_blocks", [])
    page_sizes = metadata.get("page_sizes", [])

    if not text_blocks:
        print("[정보] 텍스트 블록이 없어 수식 감지를 건너뜁니다.")
        return

    # 본문 평균 폰트 크기 계산
    body_blocks = [b for b in text_blocks if not b.get("is_header_footer", False)]
    avg_font_size = sum(b["font_size"] for b in body_blocks) / len(body_blocks) if body_blocks else 10

    # 수식 번호 패턴
    eq_num_pattern = re.compile(r"\(\d+\)\s*$")

    # 독립 수식 블록 후보 감지
    equation_candidates = []

    for i, block in enumerate(body_blocks):
        text = block["text"].strip()
        page_num = block["page"]

        if not text:
            continue

        page_size = page_sizes[page_num - 1] if page_num <= len(page_sizes) else {"width": 612, "height": 792}
        page_width = page_size["width"]
        page_center = page_width / 2

        bbox = block["bbox"]
        block_center_x = (bbox[0] + bbox[2]) / 2
        block_width = bbox[2] - bbox[0]

        # 기준: 수식 블록 감지
        is_equation = False

        # 1. 수식 번호 패턴이 있는 경우
        if eq_num_pattern.search(text):
            # 짧은 텍스트 (수식은 보통 짧음)
            if len(text) < 100:
                is_equation = True

        # 2. 중앙 정렬 + 좁은 블록
        if not is_equation and abs(block_center_x - page_center) < page_width * 0.15:
            if block_width < page_width * 0.5 and len(text) < 80:
                # 위아래 간격 확인
                prev_bottom = body_blocks[i - 1]["bbox"][3] if i > 0 else 0
                next_top = body_blocks[i + 1]["bbox"][1] if i + 1 < len(body_blocks) else page_size["height"]
                gap_above = bbox[1] - prev_bottom
                gap_below = next_top - bbox[3]

                avg_line_height = avg_font_size * 1.5
                if gap_above > avg_line_height * 1.2 and gap_below > avg_line_height * 1.2:
                    is_equation = True

        if is_equation:
            equation_candidates.append(block)

    if not equation_candidates:
        print("[정보] 독립 수식 블록이 감지되지 않았습니다.")
        return

    # 페이지별로 그룹핑하여 크롭
    pages_needed = set(b["page"] for b in equation_candidates)

    for page_num in pages_needed:
        try:
            page_images = convert_from_path(
                pdf_path, first_page=page_num, last_page=page_num, dpi=200
            )
        except Exception as e:
            print(f"[경고] 페이지 {page_num} 이미지 변환 실패: {e}", file=sys.stderr)
            continue

        if not page_images:
            continue

        page_img = page_images[0]
        img_width, img_height = page_img.size
        page_size = page_sizes[page_num - 1] if page_num <= len(page_sizes) else {"width": 612, "height": 792}
        scale_x = img_width / page_size["width"]
        scale_y = img_height / page_size["height"]

        for block in equation_candidates:
            if block["page"] != page_num:
                continue

            eq_count += 1
            eq_id = f"eq_{eq_count:03d}"

            if eq_id in existing_ids:
                continue

            bbox = block["bbox"]
            pad = 10
            crop_x0 = max(0, int((bbox[0] - pad) * scale_x))
            crop_y0 = max(0, int((bbox[1] - pad) * scale_y))
            crop_x1 = min(img_width, int((bbox[2] + pad) * scale_x))
            crop_y1 = min(img_height, int((bbox[3] + pad) * scale_y))

            if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
                continue

            cropped = page_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))
            save_path = visuals_dir / f"{eq_id}.png"
            cropped.save(str(save_path), "PNG")

            manifest["visuals"].append({
                "id": eq_id,
                "type": "equation",
                "page": page_num,
                "bbox": [round(bbox[0], 2), round(bbox[1], 2), round(bbox[2], 2), round(bbox[3], 2)],
                "is_full_width": False,
                "caption": "",
                "image_path": str(save_path.relative_to(PROJECT_ROOT)),
                "translate_text": False,
                "table_data": None,
            })

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[완료] 수식 크롭 완료: {eq_count}개 추출")


def main():
    parser = argparse.ArgumentParser(description="독립 수식 블록 감지 및 크롭")
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    args = parser.parse_args()
    extract_equations(args.pdf_path)


if __name__ == "__main__":
    main()
