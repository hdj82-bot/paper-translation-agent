# SKILL.md — visual-extractor

> 그림·표·수식 블록 감지 및 크롭 이미지 저장

## 트리거

STEP 2 (시각 요소 추출) 시작 시 호출

## 스크립트

### crop_figures.py
```bash
python .claude/skills/visual-extractor/scripts/crop_figures.py <pdf_path>
```
- **기능**: Figure 영역을 감지하고 이미지로 크롭
- **감지 기준**: 캡션 텍스트 "Figure N:" 패턴 주변의 이미지/비텍스트 영역
- **전폭 감지**: bbox 너비 ≥ 페이지 60%이면 전폭 Figure로 표시
- **출력**: `output/intermediate/visuals/figures/fig_NNN.png`, `visual_manifest.json` 업데이트

### crop_tables.py
```bash
python .claude/skills/visual-extractor/scripts/crop_tables.py <pdf_path>
```
- **기능**: Table 영역을 감지하고 이미지로 크롭
- **감지 기준**: 캡션 텍스트 "Table N:" 패턴, pdfplumber의 테이블 감지 기능
- **테이블 구조 추출**: pdfplumber로 셀 데이터를 추출하여 `table_data` 필드에 저장 (번역 재구성 옵션 대비)
- **출력**: `output/intermediate/visuals/tables/tbl_NNN.png`, `visual_manifest.json` 업데이트

### extract_equations.py
```bash
python .claude/skills/visual-extractor/scripts/extract_equations.py <pdf_path>
```
- **기능**: 독립 수식 블록을 감지하고 이미지로 크롭
- **감지 기준**: 중앙 정렬된 텍스트 블록, 수식 번호 패턴 "(N)", 본문과 구분되는 여백
- **인라인 수식은 제외**: 본문 줄 내 수식은 크롭하지 않고 텍스트로 처리
- **출력**: `output/intermediate/visuals/equations/eq_NNN.png`, `visual_manifest.json` 업데이트

## 출력 스키마

`visual_manifest.json`:
```json
{
  "visuals": [
    {
      "id": "fig_001",
      "type": "figure" | "table" | "equation",
      "page": number,
      "bbox": [x0, y0, x1, y1],
      "is_full_width": boolean,
      "caption": string,
      "image_path": string,
      "translate_text": boolean,
      "table_data": null | array (테이블인 경우 셀 데이터)
    }
  ]
}
```
