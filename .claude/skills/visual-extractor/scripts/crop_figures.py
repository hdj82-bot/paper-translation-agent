"""Figure 영역 감지 및 이미지 크롭"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def crop_figures(pdf_path: str):
    import pdfplumber
    from pdf2image import convert_from_path
    from PIL import Image

    pdf_path = str(Path(pdf_path).resolve())
    output_dir = PROJECT_ROOT / "output" / "intermediate"
    visuals_dir = output_dir / "visuals" / "figures"
    visuals_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "visual_manifest.json"
    manifest = {"visuals": []}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    existing_ids = {v["id"] for v in manifest["visuals"]}
    fig_count = sum(1 for v in manifest["visuals"] if v["type"] == "figure")

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            page_width = float(page.width)
            page_height = float(page.height)

            # 캡션 텍스트로 Figure 위치 파악
            text = page.extract_text() or ""
            fig_captions = list(re.finditer(
                r"(Fig(?:ure)?\.?\s*\d+[.:]\s*[^\n]+)", text, re.IGNORECASE
            ))

            # 이미지 객체 수집
            images = page.images if hasattr(page, "images") else []

            if not images and not fig_captions:
                continue

            # 페이지를 이미지로 변환
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
            scale_x = img_width / page_width
            scale_y = img_height / page_height

            for img_obj in images:
                fig_count += 1
                fig_id = f"fig_{fig_count:03d}"

                if fig_id in existing_ids:
                    continue

                x0 = float(img_obj.get("x0", 0))
                y0 = float(img_obj.get("top", 0))
                x1 = float(img_obj.get("x1", page_width))
                y1 = float(img_obj.get("bottom", page_height))

                # 약간의 패딩 추가
                pad = 5
                crop_x0 = max(0, int((x0 - pad) * scale_x))
                crop_y0 = max(0, int((y0 - pad) * scale_y))
                crop_x1 = min(img_width, int((x1 + pad) * scale_x))
                crop_y1 = min(img_height, int((y1 + pad) * scale_y))

                if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
                    continue

                cropped = page_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))
                save_path = visuals_dir / f"{fig_id}.png"
                cropped.save(str(save_path), "PNG")

                is_full_width = (x1 - x0) >= page_width * 0.6

                # 캡션 매칭: 현재 fig_count 번호로 캡션 매칭 시도
                caption = ""
                for cap_match in fig_captions:
                    cap_text = cap_match.group(1).strip()
                    # Figure 번호 추출 (Fig 1, Figure 2, Fig. 3 등)
                    num_match = re.search(r"[Ff]ig(?:ure)?\.?\s*(\d+)", cap_text)
                    if num_match and int(num_match.group(1)) == fig_count:
                        caption = cap_text
                        break
                if not caption and fig_captions:
                    # 번호 매칭 실패 시 위치 기반으로 첫 미사용 캡션 사용
                    cap_idx = (fig_count - 1) % len(fig_captions)
                    caption = fig_captions[cap_idx].group(1).strip()

                manifest["visuals"].append({
                    "id": fig_id,
                    "type": "figure",
                    "page": page_num,
                    "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    "is_full_width": is_full_width,
                    "caption": caption,
                    "image_path": str(save_path.relative_to(PROJECT_ROOT)),
                    "translate_text": False,
                    "table_data": None,
                })

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    new_count = fig_count - sum(1 for v in manifest["visuals"] if v["type"] == "figure" and v["id"] in existing_ids)
    print(f"[완료] Figure 크롭 완료: {new_count}개 추출")


def main():
    parser = argparse.ArgumentParser(description="Figure 영역 감지 및 크롭")
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    args = parser.parse_args()
    crop_figures(args.pdf_path)


if __name__ == "__main__":
    main()
