"""번역 작업 관리 — 파이프라인 실행 및 상태 추적"""

import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 전역 작업 저장소
_jobs: dict[str, "JobState"] = {}
_lock = threading.Lock()


@dataclass
class JobState:
    job_id: str
    status: str = "pending"   # pending | running | completed | failed
    progress: int = 0          # 0–100
    step: str = ""
    events: list[dict] = field(default_factory=list)
    result_pdf: str | None = None
    error: str | None = None
    done: bool = False


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def create_job(pdf_bytes: bytes, original_filename: str) -> str:
    """PDF 업로드 후 번역 작업 생성 및 백그라운드 시작"""
    job_id = uuid.uuid4().hex[:12]

    # 입력 PDF 저장 — JOB_DIR 격리를 위해 {job_id}.pdf 로 저장
    input_dir = PROJECT_ROOT / "input"
    input_dir.mkdir(exist_ok=True)
    pdf_path = input_dir / f"{job_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    state = JobState(job_id=job_id)
    with _lock:
        _jobs[job_id] = state

    thread = threading.Thread(target=_run_job, args=(job_id, str(pdf_path)), daemon=True)
    thread.start()

    return job_id


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


# ──────────────────────────────────────────────
# 내부 파이프라인 실행
# ──────────────────────────────────────────────

def _emit(state: JobState, step: str, message: str, progress: int):
    state.step = step
    state.progress = progress
    event = {"step": step, "message": message, "progress": progress}
    state.events.append(event)


def _run_script(state: JobState, script_rel: str, *args: str) -> bool:
    """프로젝트 루트 기준으로 Python 스크립트를 실행합니다.

    JOB_DIR 환경변수를 설정하여 중간 산출물을 격리합니다.
    반환: 성공 여부
    """
    env = {**os.environ, "JOB_DIR": state.job_id}
    cmd = [sys.executable, str(PROJECT_ROOT / script_rel), *args]
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "알 수 없는 오류").strip()
        _emit(state, "오류", f"{script_rel} 실패: {err[:300]}", state.progress)
        return False
    return True


def _run_job(job_id: str, pdf_path: str):
    state = _jobs[job_id]
    state.status = "running"

    try:
        _pipeline(state, pdf_path)
    except Exception as exc:
        tb = traceback.format_exc()
        state.status = "failed"
        state.error = str(exc)
        _emit(state, "오류", f"예기치 않은 오류: {exc}\n{tb[:500]}", state.progress)
    finally:
        state.done = True


def _pipeline(state: JobState, pdf_path: str):
    # ── STEP 1: PDF 분석 ──────────────────────────────
    _emit(state, "STEP 1", "PDF 메타데이터·레이아웃·섹션 분석 중…", 5)

    for script in [
        "extract_metadata.py",
        "detect_layout.py",
        "detect_sections.py",
    ]:
        ok = _run_script(state, f".claude/skills/pdf-analyzer/scripts/{script}", pdf_path)
        if not ok:
            state.status = "failed"
            state.error = f"STEP 1 실패: {script}"
            return

    _emit(state, "STEP 1", "PDF 분석 완료", 15)

    # ── STEP 2: 시각 요소 추출 ────────────────────────
    _emit(state, "STEP 2", "Figure·Table·수식 이미지 추출 중…", 18)

    for script in ["crop_figures.py", "crop_tables.py", "extract_equations.py"]:
        ok = _run_script(state, f".claude/skills/visual-extractor/scripts/{script}", pdf_path)
        if not ok:
            # 시각 요소 추출 실패는 경고만 (스킵 가능)
            _emit(state, "STEP 2", f"경고: {script} 일부 실패 (계속 진행)", state.progress)

    _emit(state, "STEP 2", "시각 요소 추출 완료", 25)

    # ── STEP 4: 섹션 분할 ────────────────────────────
    _emit(state, "STEP 4", "섹션별 텍스트 청크 분할 중…", 28)

    ok = _run_script(state, ".claude/skills/section-splitter/scripts/extract_text_blocks.py", pdf_path)
    if not ok:
        state.status = "failed"
        state.error = "STEP 4 실패: extract_text_blocks.py"
        return

    ok = _run_script(state, ".claude/skills/section-splitter/scripts/split_by_section.py")
    if not ok:
        state.status = "failed"
        state.error = "STEP 4 실패: split_by_section.py"
        return

    _emit(state, "STEP 4", "섹션 분할 완료", 35)

    # ── STEP 5: 번역 ─────────────────────────────────
    chunks_dir = PROJECT_ROOT / "output" / "intermediate" / state.job_id / "chunks"
    chunk_files = sorted(chunks_dir.glob("*.json"))

    # *_translated.json 파일 제외 (재시작 복구용)
    chunk_files = [f for f in chunk_files if not f.stem.endswith("_translated")]

    if not chunk_files:
        state.status = "failed"
        state.error = "STEP 4 결과 청크 파일이 없습니다."
        return

    _emit(state, "STEP 5", f"번역 시작 — 총 {len(chunk_files)}개 섹션", 38)

    # translator 모듈을 PROJECT_ROOT 기준으로 임포트
    sys.path.insert(0, str(PROJECT_ROOT))
    from web.translator import translate_chunk

    translate_count = 0
    for i, chunk_file in enumerate(chunk_files):
        progress = 38 + int(42 * (i / len(chunk_files)))
        _emit(state, "STEP 5", f"번역 중: {chunk_file.stem} ({i+1}/{len(chunk_files)})", progress)
        try:
            translate_chunk(str(chunk_file))
            translate_count += 1
        except Exception as exc:
            _emit(state, "STEP 5", f"경고: {chunk_file.stem} 번역 실패 ({exc}), 건너뜀", progress)

    if translate_count == 0:
        state.status = "failed"
        state.error = "STEP 5 실패: 모든 섹션 번역에 실패했습니다."
        return

    _emit(state, "STEP 5", f"번역 완료 ({translate_count}/{len(chunk_files)}개 섹션)", 82)

    # ── STEP 6: PDF 조립 ─────────────────────────────
    _emit(state, "STEP 6", "한국어 폰트 준비 중…", 84)

    ok = _run_script(state, ".claude/skills/pdf-assembler/scripts/embed_korean_font.py")
    if not ok:
        _emit(state, "STEP 6", "경고: 폰트 임베딩 실패, 기본 폰트로 계속 진행", 84)

    _emit(state, "STEP 6", "번역 PDF 조립 중…", 86)

    ok = _run_script(state, ".claude/skills/pdf-assembler/scripts/assemble_pdf.py", pdf_path)
    if not ok:
        state.status = "failed"
        state.error = "STEP 6 실패: assemble_pdf.py"
        return

    # 번역 PDF 경로 확인
    pdf_stem = Path(pdf_path).stem
    translated_pdf = PROJECT_ROOT / "output" / "translated" / f"{pdf_stem}_translated.pdf"

    if not translated_pdf.exists():
        state.status = "failed"
        state.error = f"번역 PDF가 생성되지 않았습니다: {translated_pdf}"
        return

    _emit(state, "STEP 6", "PDF 조립 완료", 93)

    # ── STEP 8: 아카이빙 ─────────────────────────────
    _emit(state, "STEP 8", "결과물 아카이빙 중…", 95)

    _run_script(state, ".claude/skills/archiver/scripts/generate_filename.py")
    _run_script(state, ".claude/skills/archiver/scripts/save_metadata.py")

    _emit(state, "완료", "번역이 완료되었습니다. 파일을 다운로드하세요.", 100)

    state.result_pdf = str(translated_pdf)
    state.status = "completed"
