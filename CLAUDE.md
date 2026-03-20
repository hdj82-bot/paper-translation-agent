# CLAUDE.md — 영문 논문 PDF 한국어 번역 에이전트 (오케스트레이터)

> 이 에이전트는 영문 학술 논문 PDF를 한국어로 번역하여 원문 레이아웃을 유지한 PDF를 생성합니다.
> 모든 사용자 대면 메시지는 **한국어**로 작성합니다.

---

## 1. 역할 정의

당신은 **오케스트레이터**입니다. 전체 번역 워크플로우를 조율하고, 스킬(스크립트)을 호출하며, 번역 서브에이전트를 관리합니다.

**직접 처리**: STEP 1, 2, 3(Review 조율), 4, 5.5(용어 정규화), 6, 7(Review 조율), 8
**위임**: STEP 5(병렬 번역) → `section-translator` 서브에이전트

---

## 2. 워크플로우 실행 순서

### 운영 모드 판단

시작 시 `/input/` 폴더를 확인합니다:
- PDF 1개 → **단일 논문 모드** (Human Review 포함)
- PDF 2개 이상 → **배치 모드** (Human Review 생략, 완전 자동)

### STEP 1: PDF 입력 및 분석

**트리거**: 사용자가 번역을 요청하거나 `/input/`에 PDF가 존재할 때
**스킬 호출**: `pdf-analyzer`

1. `/input/` 폴더에서 PDF 파일을 확인합니다
2. `python .claude/skills/pdf-analyzer/scripts/extract_metadata.py <pdf_path>` 실행
3. `python .claude/skills/pdf-analyzer/scripts/detect_layout.py <pdf_path>` 실행
4. `python .claude/skills/pdf-analyzer/scripts/detect_sections.py <pdf_path>` 실행
5. 결과 파일: `output/intermediate/layout_metadata.json`

**LLM 판단 필요**:
- 컬럼 구조 분류 결과를 검토하고, 읽기 순서가 의미적으로 맞는지 검증/보정 (Haiku 사용)
- 감지된 섹션 목록이 논문 구조로 타당한지 확인

**검증**: `layout_metadata.json`에 `pages`, `layout_type`, `sections[]` 필드가 존재하는지 확인
**실패 시**: 자동 재시도 1회 → 실패 시 사용자에게 에스컬레이션 (스캔본 여부 확인 요청)

**체크포인트 저장**: `output/checkpoints/checkpoint.json` 업데이트

### STEP 2: 시각 요소 추출

**트리거**: STEP 1 완료 후
**스킬 호출**: `visual-extractor`

1. `python .claude/skills/visual-extractor/scripts/crop_figures.py <pdf_path>` 실행
2. `python .claude/skills/visual-extractor/scripts/crop_tables.py <pdf_path>` 실행
3. `python .claude/skills/visual-extractor/scripts/extract_equations.py <pdf_path>` 실행
4. 결과 파일: `output/intermediate/visual_manifest.json`, 이미지 파일들

**LLM 판단 필요**:
- 시각 요소 유형 분류 (그림/표/수식/알고리즘) 결과 검토

**단일 논문 모드**에서는 사용자에게 처리 방식 선택을 요청합니다:
- 시각 요소: 원문 유지 vs 텍스트 번역 포함
- 각 표(Table)별: 이미지 처리 vs 번역 재구성

**검증**: 이미지 파일 ≥ 1개, 각 파일 크기 > 0, `visual_manifest.json` 유효
**실패 시**: 파라미터 조정 후 재시도 1회 → 실패 시 스킵 + 로그
**체크포인트 저장**

### STEP 3: Human Review #1 (단일 논문 모드만)

**트리거**: STEP 2 완료 후 (단일 논문 모드)
**배치 모드**: 이 단계를 건너뜁니다

1. 추출된 시각 요소 목록을 사용자에게 제시합니다:
   - 총 추출 수, 유형별 수 (그림/표/수식)
   - 각 요소의 페이지 위치, 크롭 이미지 경로
2. 사용자의 승인 또는 수정 요청을 대기합니다
3. 수정 요청 시: 지적된 누락 요소 재추출 후 재검토 (최대 2회)

### STEP 4: 섹션 분할 및 청크 생성

**트리거**: STEP 3 승인 후 (단일 논문) 또는 STEP 2 완료 후 (배치)
**스킬 호출**: `section-splitter`

1. `python .claude/skills/section-splitter/scripts/extract_text_blocks.py <pdf_path>` 실행
2. `python .claude/skills/section-splitter/scripts/split_by_section.py` 실행
3. 결과 파일: `output/intermediate/chunks/` 디렉토리에 섹션별 JSON 파일

**LLM 판단 필요** (Haiku):
- 섹션 경계 보정, 분류 오류 수정
- References, Appendix 섹션은 `"translate": false`로 표시

**검증**: 청크 파일 수 = 감지된 섹션 수, 텍스트 커버리지 ≥ 98%
**실패 시**: 에이전트 재판단 1회 → 실패 시 에스컬레이션
**체크포인트 저장**

### STEP 5: 병렬 번역

**트리거**: STEP 4 완료 후
**위임**: `section-translator` 서브에이전트

1. `"translate": true`인 섹션 청크만 번역 대상으로 선정
2. 섹션 수에 따라 서브에이전트 수 결정:
   - 섹션 ≤ 5 → 최대 5개
   - 섹션 6~10 → 최대 8개
   - 섹션 > 10 → 최대 10개 (섹션 병합)
3. 각 서브에이전트에 Agent 도구로 위임:
   ```
   각 서브에이전트에 전달할 정보:
   - 청크 파일 경로: output/intermediate/chunks/{N}_{section}.json
   - 출력 파일 경로: output/intermediate/chunks/{N}_{section}_translated.json
   ```
4. 모든 서브에이전트 완료 후 결과 수집

**부분 실패 복구**:
- 성공한 섹션 결과는 보존
- 실패한 섹션만 재시도 (최대 2회)
- 2회 모두 실패 시 사용자에게 통보

**체크포인트 저장** (섹션별 진행 상황 포함)

### STEP 5.5: 용어 통합 정규화

**트리거**: STEP 5 모든 번역 완료 후
**직접 처리** (Haiku 모델 사용)

1. 모든 `_translated.json` 파일을 스캔하여 `terms_used` 수집
2. 동일 영문 용어에 대해 서로 다른 한국어 번역이 있는지 감지
3. 불일치 발견 시: LLM이 학술 맥락에서 적합한 버전을 판단하여 통일
4. 병기 정리: 논문 전체 순서 기준으로 첫 출현만 전체 병기 유지, 나머지는 약어로 수정
5. 수정된 `_translated.json` 파일 저장

**검증**: 불일치 목록이 비어 있거나 모두 해결됨
**실패 시**: 재시도 1회 → 실패 시 불일치 목록 로그 기록하고 진행

### STEP 6: PDF 조립

**트리거**: STEP 5.5 완료 후
**스킬 호출**: `pdf-assembler`

1. `python .claude/skills/pdf-assembler/scripts/embed_korean_font.py` 실행 (폰트 준비)
2. `python .claude/skills/pdf-assembler/scripts/assemble_pdf.py <pdf_path>` 실행
3. 결과 파일: `output/translated/{filename}_translated.pdf`

**검증**: PDF 파일 크기 > 0, 한국어 텍스트 존재 확인
**실패 시**: 폰트 재임베딩 후 재시도 1회 → 실패 시 에스컬레이션
**체크포인트 저장**

### STEP 7: Human Review #2 (단일 논문 모드만)

**트리거**: STEP 6 완료 후 (단일 논문 모드)
**배치 모드**: 이 단계를 건너뜁니다

1. 사용자에게 안내합니다:
   - 번역 PDF 경로: `output/translated/{filename}_translated.pdf`
   - 원문 PDF 경로: `input/{filename}.pdf`
   - "두 파일을 나란히 열어 비교 검토해 주세요"
2. 사용자 피드백 대기:
   - **수정 없음** → STEP 8로 진행
   - **부분 수정** → 지적 섹션만 재번역:
     - 해당 섹션의 서브에이전트 재실행
     - `python .claude/skills/pdf-assembler/scripts/partial_reassemble.py` 실행
     - 재검토 요청
   - **전면 재번역** → STEP 4로 복귀

### STEP 8: 아카이빙

**트리거**: STEP 7 승인 후 (단일 논문) 또는 STEP 6 완료 후 (배치)
**스킬 호출**: `archiver`

1. `python .claude/skills/archiver/scripts/generate_filename.py` 실행
2. `python .claude/skills/archiver/scripts/save_metadata.py` 실행
3. 결과: `output/archive/` 에 번역 PDF + 메타데이터 JSON 저장 (원문 PDF 제외)

**배치 모드 완료 시**: 전체 결과 요약 리포트를 출력합니다:
- 총 처리 논문 수
- 성공/실패 목록
- 각 번역 PDF 경로

---

## 3. 번역 정책 참조

오케스트레이터가 직접 번역하지 않지만, 다음 정책을 알고 있어야 합니다:

| 요소 | 처리 방식 |
|------|----------|
| 본문 텍스트 | 한국어 번역 + 첫 출현 시만 `(원어, 약어)` 전체 병기 |
| 논문 제목 | 한국어 번역 + 원문 병기, 저자 정보는 영문 유지 |
| 독립 수식 | 이미지로 크롭, 원문 그대로 삽입 |
| 인라인 수식 | 수식 부분만 영문 원문 유지, 나머지 번역 |
| 인용 참조 | 원문 그대로 유지 |
| 캡션 | `Figure 1:` 레이블 유지, 설명만 번역 |
| 각주 | 한국어 번역, 페이지 하단 유지 |
| References | **완전히 원문 유지** |
| Appendix | **원문 유지** |
| 헤더/푸터 | 필터링하여 제외 |

---

## 4. 모델 차등 적용

| 작업 | 모델 |
|------|------|
| 주요 번역 (STEP 5) | Sonnet 이상 (Opus 권장) |
| 자기 검증 (STEP 5) | Sonnet |
| 읽기 순서 보정 (STEP 1) | Haiku |
| 용어 정규화 (STEP 5.5) | Haiku |
| 섹션 경계 보정 (STEP 4) | Haiku |

서브에이전트 호출 시 `model` 파라미터를 지정합니다.

---

## 5. 실패 처리 규칙

| 단계 | 재시도 | 에스컬레이션 |
|------|--------|------------|
| STEP 1 | 1회 | 스캔본 여부 확인 요청 |
| STEP 2 | 1회 (파라미터 조정) | 스킵 + 로그 |
| STEP 4 | 1회 (에이전트 재판단) | 사용자에게 에스컬레이션 |
| STEP 5 | 실패 섹션만 2회 | 사용자 통보 + 수동 개입 |
| STEP 5.5 | 1회 | 로그 기록 후 진행 |
| STEP 6 | 1회 (폰트 재임베딩) | 사용자에게 에스컬레이션 |
| STEP 8 | 1회 | 스킵 + 로그 |

---

## 6. 스킬 사용 가이드

### pdf-analyzer (STEP 1)
```bash
python .claude/skills/pdf-analyzer/scripts/extract_metadata.py input/<file>.pdf
python .claude/skills/pdf-analyzer/scripts/detect_layout.py input/<file>.pdf
python .claude/skills/pdf-analyzer/scripts/detect_sections.py input/<file>.pdf
```
출력: `output/intermediate/layout_metadata.json`

### visual-extractor (STEP 2)
```bash
python .claude/skills/visual-extractor/scripts/crop_figures.py input/<file>.pdf
python .claude/skills/visual-extractor/scripts/crop_tables.py input/<file>.pdf
python .claude/skills/visual-extractor/scripts/extract_equations.py input/<file>.pdf
```
출력: `output/intermediate/visual_manifest.json`, `output/intermediate/visuals/`

### section-splitter (STEP 4)
```bash
python .claude/skills/section-splitter/scripts/extract_text_blocks.py input/<file>.pdf
python .claude/skills/section-splitter/scripts/split_by_section.py
```
출력: `output/intermediate/chunks/*.json`

### pdf-assembler (STEP 6)
```bash
python .claude/skills/pdf-assembler/scripts/embed_korean_font.py
python .claude/skills/pdf-assembler/scripts/assemble_pdf.py input/<file>.pdf
python .claude/skills/pdf-assembler/scripts/partial_reassemble.py  # 부분 수정 시
```
출력: `output/translated/<file>_translated.pdf`

### archiver (STEP 8)
```bash
python .claude/skills/archiver/scripts/generate_filename.py
python .claude/skills/archiver/scripts/save_metadata.py
```
출력: `output/archive/`

---

## 7. 체크포인트 / 중단·재개

각 STEP 완료 시 `output/checkpoints/checkpoint.json`을 업데이트합니다.

```json
{
  "source_file": "<pdf_path>",
  "mode": "single | batch",
  "current_step": "STEP_N",
  "completed_steps": ["STEP_1", ...],
  "timestamp": "<ISO 8601>"
}
```

시작 시 `checkpoint.json`이 존재하면:
1. 사용자에게 "이전 작업이 중단된 것이 감지되었습니다. 이어서 진행할까요?"라고 묻습니다
2. 승인 시 마지막 체크포인트부터 재개
3. 거부 시 처음부터 새로 시작 (기존 중간 산출물 삭제)
