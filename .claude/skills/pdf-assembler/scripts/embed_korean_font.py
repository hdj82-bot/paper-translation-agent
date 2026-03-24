"""한국어 폰트 준비 및 검증"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import get_intermediate_dir

FONT_URLS = {
    "NotoSansKR-Regular.otf": "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
    "NotoSerifKR-Regular.otf": "https://github.com/google/fonts/raw/main/ofl/notoserifkr/NotoSerifKR%5Bwght%5D.ttf",
}


def extract_original_font(pdf_path: str, fonts_dir: Path) -> Path | None:
    """원문 PDF에 임베드된 본문 폰트를 추출하여 fonts/original/ 에 저장합니다."""
    try:
        from pypdf import PdfReader
        from pypdf.generic import IndirectObject
    except ImportError:
        return None

    original_dir = fonts_dir / "original"
    original_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(pdf_path)

    # 페이지별 폰트 사용 횟수 집계
    font_counts: dict[str, list] = {}  # base_font_name -> [count, font_obj]

    for page in reader.pages:
        try:
            resources = page.get("/Resources")
            if resources is None:
                continue
            if isinstance(resources, IndirectObject):
                resources = resources.get_object()

            fonts = resources.get("/Font", {})
            if isinstance(fonts, IndirectObject):
                fonts = fonts.get_object()

            for font_ref in fonts.values():
                font_obj = font_ref.get_object() if isinstance(font_ref, IndirectObject) else font_ref
                base_font = str(font_obj.get("/BaseFont", ""))
                if not base_font:
                    continue
                if base_font not in font_counts:
                    font_counts[base_font] = [0, font_obj]
                font_counts[base_font][0] += 1
        except Exception:
            continue

    if not font_counts:
        return None

    # 가장 많이 사용된 폰트 선택
    best_name, (_, best_font) = max(font_counts.items(), key=lambda x: x[1][0])

    try:
        descriptor = best_font.get("/FontDescriptor")
        if descriptor is None:
            return None
        if isinstance(descriptor, IndirectObject):
            descriptor = descriptor.get_object()

        for key, ext in [("/FontFile2", ".ttf"), ("/FontFile3", ".otf"), ("/FontFile", ".pfb")]:
            font_stream = descriptor.get(key)
            if not font_stream:
                continue
            if isinstance(font_stream, IndirectObject):
                font_stream = font_stream.get_object()

            font_data = font_stream.get_data()
            if len(font_data) < 1000:
                continue

            # 서브셋 prefix 제거: "ABCDEF+FontName" → "FontName"
            clean_name = best_name.lstrip("/")
            if "+" in clean_name:
                clean_name = clean_name.split("+", 1)[1]
            clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_name)

            out_path = original_dir / f"{clean_name}{ext}"
            with open(out_path, "wb") as f:
                f.write(font_data)

            print(f"[완료] 원문 폰트 추출: {clean_name}{ext} ({len(font_data):,} bytes)", file=sys.stderr)
            return out_path

    except Exception as e:
        print(f"[경고] 원문 폰트 파일 추출 실패: {e}", file=sys.stderr)

    return None


def embed_korean_font():
    fonts_dir = PROJECT_ROOT / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    meta_path = get_intermediate_dir() / "layout_metadata.json"

    target_font = "NotoSansKR-Regular.otf"
    metadata = {}
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        target_font = metadata.get("target_font", "NotoSansKR-Regular.otf")

    # 원문 PDF에서 폰트 추출 (없으면 조용히 건너뜀)
    source_pdf = metadata.get("source_file", "")
    if source_pdf and Path(source_pdf).exists():
        original_font_path = extract_original_font(source_pdf, fonts_dir)
        if original_font_path:
            metadata["original_font_path"] = str(original_font_path)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

    font_path = fonts_dir / target_font

    # 폰트 파일 존재 확인, 없으면 다운로드
    if not font_path.exists():
        # .ttf 확장자로도 확인
        ttf_path = font_path.with_suffix(".ttf")
        if ttf_path.exists():
            font_path = ttf_path
        else:
            url = FONT_URLS.get(target_font)
            if url:
                print(f"[정보] 폰트 다운로드 중: {target_font}", file=sys.stderr)
                try:
                    download_path = fonts_dir / target_font.replace(".otf", ".ttf")
                    urllib.request.urlretrieve(url, str(download_path))
                    font_path = download_path
                    print(f"[완료] 폰트 다운로드 완료: {font_path}", file=sys.stderr)
                except Exception as e:
                    print(f"[오류] 폰트 다운로드 실패: {e}", file=sys.stderr)
                    print(f"[안내] 다음 위치에 한국어 폰트 파일을 수동으로 배치해주세요:", file=sys.stderr)
                    print(f"  {font_path}", file=sys.stderr)
                    print(f"  Google Fonts에서 다운로드: https://fonts.google.com/noto/specimen/Noto+Sans+KR", file=sys.stderr)
                    sys.exit(1)
            else:
                # fonts 디렉토리에서 아무 한국어 폰트 찾기
                for ext in ["*.otf", "*.ttf"]:
                    found = list(fonts_dir.glob(ext))
                    if found:
                        font_path = found[0]
                        break
                else:
                    print(f"[오류] 한국어 폰트를 찾을 수 없습니다.", file=sys.stderr)
                    print(f"[안내] fonts/ 디렉토리에 Noto Sans KR 또는 Noto Serif KR 폰트를 배치해주세요.", file=sys.stderr)
                    sys.exit(1)

    # reportlab에서 폰트 등록 테스트
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_name = font_path.stem
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        print(f"[완료] 폰트 등록 성공: {font_name} ({font_path})", file=sys.stderr)
    except Exception as e:
        print(f"[경고] reportlab 폰트 등록 테스트 실패: {e}", file=sys.stderr)
        print(f"[정보] PDF 조립 시 다시 시도합니다.", file=sys.stderr)

    # 폰트 경로를 stdout으로 출력 (다른 스크립트에서 사용)
    print(str(font_path.resolve()))


def main():
    embed_korean_font()


if __name__ == "__main__":
    main()
