"""프로젝트 공통 경로 유틸리티"""

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Tesseract 기본 설치 경로 (Windows)
_TESSERACT_DEFAULT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def get_poppler_path() -> str | None:
    """Poppler 바이너리 경로 반환. PATH에 없으면 tools/ 디렉토리에서 자동 탐색."""
    if shutil.which("pdftoppm"):
        return None

    tools_dir = PROJECT_ROOT / "tools"
    if tools_dir.exists():
        for candidate in sorted(tools_dir.rglob("pdftoppm.exe")):
            return str(candidate.parent)
        for candidate in sorted(tools_dir.rglob("pdftoppm")):
            return str(candidate.parent)

    return None


def get_tesseract_path() -> str | None:
    """Tesseract 실행 파일 경로 반환. PATH에 없으면 기본 설치 경로에서 탐색."""
    if shutil.which("tesseract"):
        return None  # PATH에 있으면 pytesseract가 알아서 찾음

    for path in _TESSERACT_DEFAULT_PATHS:
        if Path(path).exists():
            return path

    return None


def configure_pytesseract():
    """pytesseract가 Tesseract를 찾을 수 있도록 경로 설정."""
    try:
        import pytesseract
        path = get_tesseract_path()
        if path:
            pytesseract.pytesseract.tesseract_cmd = path
    except ImportError:
        pass
