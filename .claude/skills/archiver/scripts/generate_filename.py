"""아카이브용 파일명 생성"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.paths import get_intermediate_dir


def sanitize_filename(title: str, max_length: int = 50) -> str:
    """파일명에 사용 가능한 형태로 변환"""
    sanitized = re.sub(r"[^\w\s-]", "", title)
    sanitized = re.sub(r"\s+", "_", sanitized.strip())
    sanitized = sanitized[:max_length].rstrip("_")
    return sanitized


def generate_filename():
    output_dir = get_intermediate_dir()
    meta_path = output_dir / "layout_metadata.json"

    if not meta_path.exists():
        print("[오류] layout_metadata.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 제목 추출 시도
    title = "untitled"

    # 1. 첫 번째 텍스트 블록 중 큰 폰트 사용 (제목일 가능성)
    text_blocks = metadata.get("text_blocks", [])
    if text_blocks:
        body_blocks = [b for b in text_blocks if not b.get("is_header_footer", False)]
        if body_blocks:
            avg_size = sum(b["font_size"] for b in body_blocks) / len(body_blocks)
            # 첫 페이지에서 평균보다 큰 폰트의 텍스트 찾기
            for block in body_blocks:
                if block["page"] == 1 and block["font_size"] > avg_size * 1.3:
                    title = block["text"].strip()
                    break
            else:
                # 첫 번째 비-헤더 블록 사용
                title = body_blocks[0]["text"][:100].strip()

    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = sanitize_filename(title)
    filename = f"{date_str}_{safe_title}_ko"

    # 파일명 저장
    archive_filename_path = output_dir / "archive_filename.txt"
    with open(archive_filename_path, "w", encoding="utf-8") as f:
        f.write(filename)

    # stdout으로 출력
    print(filename)


def main():
    generate_filename()


if __name__ == "__main__":
    main()
