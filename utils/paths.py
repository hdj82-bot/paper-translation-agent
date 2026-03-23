"""프로젝트 공통 경로 유틸리티"""

import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_poppler_path() -> str | None:
    """Poppler 바이너리 경로 반환. PATH에 없으면 tools/ 디렉토리에서 자동 탐색."""
    # 1. PATH에 이미 있으면 None 반환 (pdf2image가 알아서 찾음)
    if shutil.which("pdftoppm"):
        return None

    # 2. tools/ 디렉토리에서 탐색
    tools_dir = PROJECT_ROOT / "tools"
    if tools_dir.exists():
        for candidate in sorted(tools_dir.rglob("pdftoppm.exe")):
            return str(candidate.parent)
        for candidate in sorted(tools_dir.rglob("pdftoppm")):
            return str(candidate.parent)

    return None
