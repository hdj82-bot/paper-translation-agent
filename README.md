# paper-translation-agent

영문 학술 논문 PDF를 한국어로 번역하는 **Claude Code 멀티에이전트 시스템**.
원문 레이아웃(2컬럼, 수식, 그림, 표)을 최대한 유지한 한국어 PDF를 자동 생성합니다.

---

## 시스템 요구 사항

| 항목 | 버전 | 설치 방법 |
|------|------|----------|
| Python | 3.11+ | [python.org](https://python.org) |
| Claude Code | 최신 | `npm install -g @anthropic-ai/claude-code` |
| Poppler | 24.08+ | 아래 참고 |
| Tesseract | 5.4+ | 아래 참고 (스캔 PDF만 필요) |

---

## 설치

### 1. 저장소 클론

```bash
git clone https://github.com/hdj82-bot/paper-translation-agent
cd paper-translation-agent
```

### 2. Python 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. Poppler 설치

**Windows:**
```
winget install oschwartz10612.poppler
```
또는 [릴리스 페이지](https://github.com/oschwartz10612/poppler-windows/releases)에서 zip 다운로드 후 `tools/` 에 압축 해제.
→ `tools/` 하위에 `pdftoppm.exe`가 있으면 자동 감지됩니다.

**macOS:**
```bash
brew install poppler
```

**Linux:**
```bash
apt install poppler-utils
```

### 4. Tesseract 설치 (선택 — 스캔 PDF 처리 시 필요)

**Windows:**
```
winget install UB-Mannheim.TesseractOCR
```
또는 [다운로드 페이지](https://github.com/UB-Mannheim/tesseract/releases)에서 설치.
→ `C:\Program Files\Tesseract-OCR\` 기본 경로로 설치하면 자동 감지됩니다.

**macOS:**
```bash
brew install tesseract tesseract-lang
```

---

## 사용 방법

### 단일 논문 번역 (인터랙티브 모드)

1. 번역할 PDF 파일을 `input/` 폴더에 복사합니다
2. 프로젝트 루트에서 Claude Code 실행:

```bash
claude
```

3. Claude가 8단계 파이프라인을 안내하며 번역합니다:
   - STEP 3: 추출된 시각 요소 검토 요청
   - STEP 7: 번역 결과 검토 요청

4. 결과물: `output/translated/{파일명}_translated.pdf`

### 다수 논문 배치 번역 (자동 모드)

1. 번역할 PDF 파일들을 모두 `input/` 폴더에 복사합니다 (2개 이상)
2. Claude Code 실행:

```bash
claude
```

3. Human Review 없이 완전 자동으로 처리됩니다
4. 결과물: `output/archive/` 에 논문별 PDF + 메타데이터 JSON

---

## 번역 정책

| 요소 | 처리 방식 |
|------|----------|
| 본문 텍스트 | 한국어 번역 + `용어(English, ABBR)` 병기 |
| 논문 제목 | 한국어 번역 + 원문 병기 |
| 독립 수식 | 이미지 크롭 (원문 유지) |
| 인라인 수식 | 수식 원문 유지, 주변 텍스트만 번역 |
| 인용 참조 | `[1]`, `(Author, 2023)` 원문 유지 |
| References | **완전 원문 유지** |
| Appendix | **원문 유지** |

---

## 아키텍처

```
오케스트레이터 (CLAUDE.md)
├── pdf-analyzer       → 메타데이터, 레이아웃, 섹션 감지
├── visual-extractor   → Figure/Table/수식 이미지 크롭
├── section-splitter   → 섹션별 텍스트 청크 분할
├── section-translator → 섹션별 병렬 번역 (서브에이전트)
├── pdf-assembler      → 번역 텍스트 + 이미지로 PDF 조립
└── archiver           → 결과물 저장
```

**체크포인트**: 각 STEP 완료 시 `output/checkpoints/checkpoint.json` 자동 저장.
중단 후 재시작 시 이어서 진행 가능.

---

## 디렉터리 구조

```
paper-translation-agent/
├── CLAUDE.md                        # 오케스트레이터 프롬프트
├── requirements.txt
├── utils/
│   └── paths.py                     # Poppler/Tesseract 자동 감지, JOB_DIR 지원
├── input/                           # 번역할 PDF 파일 위치
├── output/
│   ├── intermediate/                # 중간 산출물 (자동 생성)
│   ├── translated/                  # 번역 완료 PDF
│   ├── archive/                     # 최종 아카이브
│   └── checkpoints/                 # 체크포인트
├── fonts/                           # 한국어 폰트 (자동 다운로드)
├── tools/                           # 외부 바이너리 (Poppler 등, gitignore)
└── .claude/
    ├── agents/
    │   └── section-translator/      # 번역 전담 서브에이전트
    └── skills/
        ├── pdf-analyzer/
        ├── visual-extractor/
        ├── section-splitter/
        ├── pdf-assembler/
        └── archiver/
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `JOB_DIR` | 배치 모드 시 논문별 중간 디렉터리 | (없음, `output/intermediate/` 사용) |

---

## 라이선스

MIT
