# SKILL.md — section-splitter

> 섹션 경계 기반 텍스트 블록 분할, 번역 청크 파일 생성

## 트리거

STEP 4 (섹션 분할 및 청크 생성) 시작 시 호출

## 전제 조건

- `output/intermediate/layout_metadata.json` 존재 (STEP 1 결과)
- `output/intermediate/visual_manifest.json` 존재 (STEP 2 결과)

## 스크립트

### extract_text_blocks.py
```bash
python .claude/skills/section-splitter/scripts/extract_text_blocks.py <pdf_path>
```
- **기능**: PDF에서 모든 텍스트 블록을 추출하고 읽기 순서로 정렬
- **컬럼 읽기 순서**: X좌표 기반 좌→우, 각 컬럼 내 Y좌표 기반 상→하 정렬
- **필터링**: 헤더/푸터 영역 텍스트 블록 제외 (`is_header_footer: true`)
- **시각 요소 영역 제외**: `visual_manifest.json`의 bbox와 겹치는 텍스트 블록 제외
- **출력**: `layout_metadata.json`의 `text_blocks` 업데이트

### split_by_section.py
```bash
python .claude/skills/section-splitter/scripts/split_by_section.py
```
- **기능**: `layout_metadata.json`의 섹션 정보와 텍스트 블록을 매칭하여 섹션별 청크 파일 생성
- **청크 파일 형식**: `output/intermediate/chunks/{NN}_{section_name}.json`
- **번역 제외 섹션**: References, Appendix는 청크 파일을 생성하되 `"translate": false` 표시
- **커버리지 검증**: 모든 텍스트 블록이 어떤 섹션에 할당되었는지 확인 (≥ 98%)
- **출력**: `output/intermediate/chunks/` 디렉토리에 섹션별 JSON 파일

## 출력 스키마

청크 파일 `{NN}_{section_name}.json`:
```json
{
  "chunk_id": "02_introduction",
  "section_name": "Introduction",
  "translate": true,
  "blocks": [
    {
      "id": "tb_005",
      "page": 1,
      "bbox": [x0, y0, x1, y1],
      "column": 1,
      "font_size": 10,
      "original_text": "..."
    }
  ]
}
```
