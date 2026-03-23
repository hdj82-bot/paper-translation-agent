"""Table 영역 감지 및 이미지 크롭, 셀 데이터 추출"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import get_intermediate_dir, get_poppler_path


def crop_tables(pdf_path: str):
    import pdfplumber
    from pdf2image import convert_from_path

    poppler_path = get_poppler_path()

    pdf_path = str(Path(pdf_path).resolve())
    output_dir = get_intermediate_dir()
    visuals_dir = output_dir / "visuals" / "tables"
    visuals_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "visual_manifest.json"
    manifest = {"visuals": []}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    existing_ids = {v["id"] for v in manifest["visuals"]}
    tbl_count = sum(1 for v in manifest["visuals"] if v["type"] == "table")

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            page_width = float(page.width)
            page_height = float(page.height)

            tables = page.find_tables()
            if not tables:
                continue

            try:
                page_images = convert_from_path(
                    pdf_path, first_page=page_num, last_page=page_num, dpi=200,
                    poppler_path=poppler_path
                )
            except Exception as e:
                print(f"[경고] 페이지 {page_num} 이미지 변환 실패: {e}", file=sys.stderr)
                continue

            if not page_images:
                continue

            page_img = page_images[0]
            img_width, img_height = page_img.size
            scale_x = img_width / page_width
            scale_y = img_height / page_height

            # 캡션 검색
            text = page.extract_text() or ""
            tbl_captions = list(re.finditer(
                r"(Table\s*\d+[.:]\s*[^\n]+)", text, re.IGNORECASE
            ))

            for table in tables:
                tbl_count += 1
                tbl_id = f"tbl_{tbl_count:03d}"

                if tbl_id in existing_ids:
                    continue

                bbox = table.bbox
                x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

                pad = 5
                crop_x0 = max(0, int((x0 - pad) * scale_x))
                crop_y0 = max(0, int((y0 - pad) * scale_y))
                crop_x1 = min(img_width, int((x1 + pad) * scale_x))
                crop_y1 = min(img_height, int((y1 + pad) * scale_y))

                if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
                    continue

                cropped = page_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))
                save_path = visuals_dir / f"{tbl_id}.png"
                cropped.save(str(save_path), "PNG")

                # 셀 데이터 추출
                try:
                    table_data = table.extract()
                except Exception:
                    table_data = None

                is_full_width = (x1 - x0) >= page_width * 0.6

                caption = ""
                for cap_match in tbl_captions:
                    caption = cap_match.group(1).strip()
                    break

                manifest["visuals"].append({
                    "id": tbl_id,
                    "type": "table",
                    "page": page_num,
                    "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    "is_full_width": is_full_width,
                    "caption": caption,
                    "image_path": str(save_path.relative_to(PROJECT_ROOT)),
                    "translate_text": False,
                    "table_data": table_data,
                })

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    new_count = tbl_count - sum(1 for v in manifest["visuals"] if v["type"] == "table" and v["id"] in existing_ids)
    print(f"[완료] Table 크롭 완료: {new_count}개 추출")


def main():
    parser = argparse.ArgumentParser(description="Table 영역 감지 및 크롭")
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    args = parser.parse_args()
    crop_tables(args.pdf_path)


if __name__ == "__main__":
    main()
