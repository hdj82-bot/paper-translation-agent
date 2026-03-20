"""한국어 폰트 준비 및 검증"""

import json
import os
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]

FONT_URLS = {
    "NotoSansKR-Regular.otf": "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
    "NotoSerifKR-Regular.otf": "https://github.com/google/fonts/raw/main/ofl/notoserifkr/NotoSerifKR%5Bwght%5D.ttf",
}


def embed_korean_font():
    fonts_dir = PROJECT_ROOT / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    meta_path = PROJECT_ROOT / "output" / "intermediate" / "layout_metadata.json"

    target_font = "NotoSansKR-Regular.otf"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        target_font = metadata.get("target_font", "NotoSansKR-Regular.otf")

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
