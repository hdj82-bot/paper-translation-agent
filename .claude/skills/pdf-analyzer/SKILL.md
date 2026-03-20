# SKILL.md — pdf-analyzer

> PDF 구조 분석, 레이아웃 감지, 섹션 목록 추출

## 트리거

STEP 1 (PDF 입력 및 분석) 시작 시 호출

## 스크립트

### extract_metadata.py
```bash
python .claude/skills/pdf-analyzer/scripts/extract_metadata.py <pdf_path>
```
- **기능**: PDF에서 기본 메타데이터 추출 (페이지 수, 페이지 크기, 텍스트 레이어 존재 여부)
- **하이브리드 PDF 대응**: 각 페이지별로 텍스트 레이어 존재 여부를 판단하여 `page_ocr_status` 기록
- **텍스트 레이어 없는 페이지**: pytesseract로 OCR 수행 후 텍스트 추출
- **출력**: `output/intermediate/layout_metadata.json` (기초 메타데이터)

### detect_layout.py
```bash
python .claude/skills/pdf-analyzer/scripts/detect_layout.py <pdf_path>
```
- **기능**: 1컬럼/2컬럼 레이아웃 판단, 폰트 스타일 감지 (세리프/산세리프)
- **컬럼 분리**: X좌표 기반 휴리스틱으로 텍스트 블록을 좌/우 컬럼으로 분리
- **헤더/푸터 필터링**: 페이지 상단/하단 5% 영역의 텍스트 블록에 `is_header_footer: true` 표시
- **전폭 요소 감지**: bbox 너비 ≥ 페이지 너비 60%인 요소를 전폭으로 표시
- **출력**: `layout_metadata.json` 업데이트 (layout_type, font_style, header_footer_zones, text_blocks)

### detect_sections.py
```bash
python .claude/skills/pdf-analyzer/scripts/detect_sections.py <pdf_path>
```
- **기능**: 섹션 헤딩을 감지하여 섹션 목록 생성
- **감지 기준**: 폰트 크기가 본문보다 큰 텍스트, 번호 패턴 (1., 2., I., II.), 알려진 섹션명 매칭 (Abstract, Introduction, Method, Results, Discussion, Conclusion, References, Appendix)
- **번역 제외 표시**: References, Appendix 섹션은 `"translate": false` 표시
- **출력**: `layout_metadata.json` 업데이트 (sections[])

## 출력 스키마

`layout_metadata.json` 필수 필드:
- `source_file`: string
- `pages`: number
- `layout_type`: "1-column" | "2-column"
- `font_style`: "serif" | "sans-serif"
- `target_font`: string (매칭된 한국어 폰트 파일명)
- `page_ocr_status`: object (페이지별 "text_layer" | "ocr_fallback")
- `header_footer_zones`: object (header_y_threshold, footer_y_threshold)
- `sections`: array (name, pages, chunk_id, translate)
- `text_blocks`: array (id, page, bbox, column, font_size, font_name, is_header_footer, text)
