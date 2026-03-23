"""FastAPI 웹서비스 — 논문 번역 에이전트"""

import asyncio
import json
from pathlib import Path

# .env 파일 자동 로드 (python-dotenv)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv 없으면 환경변수는 OS 설정에서 읽음

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.job_manager import create_job, get_job

# ──────────────────────────────────────────────
app = FastAPI(title="Paper Translation Agent", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ──────────────────────────────────────────────
# 메인 페이지
# ──────────────────────────────────────────────

@app.get("/")
async def index():
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(html_path))


# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────

@app.post("/api/jobs")
async def create_translation_job(file: UploadFile = File(...)):
    """PDF 파일을 업로드하고 번역 작업을 시작합니다."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(pdf_bytes) > 100 * 1024 * 1024:  # 100MB 제한
        raise HTTPException(status_code=413, detail="파일 크기가 100MB를 초과합니다.")

    job_id = create_job(pdf_bytes, file.filename)
    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """작업 상태를 반환합니다."""
    state = get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {
        "job_id": job_id,
        "status": state.status,
        "progress": state.progress,
        "step": state.step,
        "error": state.error,
        "result_ready": state.status == "completed",
    }


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    """SSE(Server-Sent Events) 스트림으로 진행상황을 실시간 전송합니다."""
    state = get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    async def event_generator():
        pos = 0
        while True:
            # 새 이벤트 전송
            while pos < len(state.events):
                event_data = json.dumps(state.events[pos], ensure_ascii=False)
                yield f"data: {event_data}\n\n"
                pos += 1

            if state.done:
                # 완료 이벤트 전송
                final = {
                    "step": state.step,
                    "message": state.error if state.status == "failed" else "완료",
                    "progress": state.progress,
                    "status": state.status,
                    "done": True,
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                break

            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/download")
async def download_result(job_id: str):
    """번역 완료된 PDF 파일을 다운로드합니다."""
    state = get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if state.status != "completed":
        raise HTTPException(status_code=400, detail="번역이 아직 완료되지 않았습니다.")
    if not state.result_pdf or not Path(state.result_pdf).exists():
        raise HTTPException(status_code=404, detail="번역 PDF 파일을 찾을 수 없습니다.")

    pdf_path = Path(state.result_pdf)
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
    )


# ──────────────────────────────────────────────
# 실행 진입점
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.main:app", host="0.0.0.0", port=8000, reload=False)
