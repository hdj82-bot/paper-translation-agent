# SKILL.md — pdf-assembler

> 번역된 청크 + 크롭 이미지로 최종 한국어 PDF 조립

## 트리거

- STEP 6 (PDF 조립) 시작 시 호출
- STEP 7 부분 수정 시 `partial_reassemble.py` 호출

## 전제 조건

- `output/intermediate/layout_metadata.json` (레이아웃 정보)
- `output/intermediate/visual_manifest.json` (시각 요소 정보)
- `output/intermediate/chunks/*_translated.json` (번역 결과)
- `fonts/` 디렉토리에 한국어 폰트 파일 존재

## 스크립트

### embed_korean_font.py
```bash
python .claude/skills/pdf-assembler/scripts/embed_korean_font.py
```
- **기능**: 한국어 폰트 파일 준비 및 검증
- **폰트 매칭**: `layout_metadata.json`의 `font_style`에 따라:
  - `serif` → `NotoSerifKR-Regular.otf`
  - `sans-serif` → `NotoSansKR-Regular.otf`
- **폰트 부재 시**: Google Fonts에서 자동 다운로드 시도
- **출력**: 폰트 경로를 표준 출력으로 반환

### assemble_pdf.py
```bash
python .claude/skills/pdf-assembler/scripts/assemble_pdf.py <original_pdf_path>
```
- **기능**: 번역된 텍스트 + 크롭 이미지를 조합하여 최종 PDF 생성
- **레이아웃 전략**:
  - 원문 bbox를 기반으로 텍스트 배치
  - **영역 확장**: 번역문이 원문 영역을 초과하면 아래로 확장
  - **밀기**: 확장된 영역 아래의 모든 요소(텍스트, 시각 요소)를 함께 밀어냄
  - **페이지 브레이크**: 밀린 요소가 페이지를 초과하면 새 페이지 생성 (페이지 수 제한 없음)
- **제목 처리**: 한국어 번역 제목 + 아래에 원문 제목 병기, 저자 정보는 원문 유지
- **Abstract**: 원문 서식 (들여쓰기, 폰트 크기) 최대한 재현
- **각주**: 해당 페이지 하단에 배치, 본문이 밀리면 각주도 함께 이동
- **원문 유지 섹션**: References, Appendix는 원문 PDF에서 해당 페이지를 그대로 추출하여 삽입
- **시각 요소**: `visual_manifest.json`의 이미지를 원래 위치에 삽입 (밀기 오프셋 적용)
- **폰트 임베딩**: reportlab에 한국어 폰트 등록 및 임베딩
- **출력**: `output/translated/{filename}_translated.pdf`

### partial_reassemble.py
```bash
python .claude/skills/pdf-assembler/scripts/partial_reassemble.py --sections <section_ids>
```
- **기능**: 수정된 섹션만 재조립
- **동작**: 지정된 섹션의 `_translated.json`만 다시 읽어 해당 부분의 PDF 페이지를 재생성
- **출력**: `output/translated/{filename}_translated.pdf` 덮어쓰기
