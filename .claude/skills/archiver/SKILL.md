# SKILL.md — archiver

> 번역 완료 PDF를 날짜·제목 기반 파일명으로 아카이빙, 메타데이터 JSON 저장

## 트리거

STEP 8 (아카이빙) 시작 시 호출

## 전제 조건

- `output/translated/{filename}_translated.pdf` 존재
- `output/intermediate/layout_metadata.json` 존재

## 스크립트

### generate_filename.py
```bash
python .claude/skills/archiver/scripts/generate_filename.py
```
- **기능**: 아카이브용 파일명 생성
- **파일명 형식**: `YYYY-MM-DD_{sanitized_title}_ko.pdf`
  - 날짜: 번역 완료일
  - 제목: 논문 제목에서 특수문자 제거, 공백을 _로 치환, 최대 50자
- **출력**: 생성된 파일명을 표준 출력으로 반환

### save_metadata.py
```bash
python .claude/skills/archiver/scripts/save_metadata.py
```
- **기능**: 번역 PDF를 아카이브 폴더로 복사하고 메타데이터 JSON 저장
- **아카이브 경로**: `output/archive/{generated_filename}.pdf`
- **메타데이터 JSON**: `output/archive/{generated_filename}_meta.json`
  ```json
  {
    "original_file": "input/paper.pdf",
    "translated_file": "output/archive/2026-03-20_Attention_Is_All_You_Need_ko.pdf",
    "translation_date": "2026-03-20",
    "original_title": "Attention Is All You Need",
    "translated_title": "어텐션이 필요한 전부이다",
    "pages_original": 12,
    "pages_translated": 15,
    "sections_translated": ["Abstract", "Introduction", "Method", "Results", "Discussion", "Conclusion"],
    "sections_preserved": ["References", "Appendix"]
  }
  ```
- **원문 PDF는 복사하지 않음** (사용자가 이미 보유)
- **출력**: 아카이브 파일 경로를 표준 출력으로 반환
