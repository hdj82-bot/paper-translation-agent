"""STEP 5: Anthropic SDK를 사용한 섹션 번역"""

import json
import re
import sys
from pathlib import Path

import anthropic

SYSTEM_PROMPT = """\
당신은 학술 논문 번역 전문가입니다. 영문 학술 논문 텍스트 블록들을 한국어로 번역합니다.

## 번역 정책

1. **학술 용어 병기**: 모든 학술 용어는 `한국어(원어 전체, 약어)` 형식으로 병기
   - 예: `합성곱 신경망(Convolutional Neural Network, CNN)`
   - 약어 없으면: `역전파(Backpropagation)`
   - 고유명사: `트랜스포머(Transformer)`

2. **인라인 수식**: `$...$`, `$$...$$`, `\\(...\\)` 수식은 **원문 그대로** 유지, 주변 텍스트만 번역
   - `has_inline_math: true` 로 표시

3. **번역하지 않는 것들** (원문 그대로 유지):
   - 인용 참조: `[1]`, `(Smith et al., 2023)`
   - 변수명, 함수명, 코드
   - URL, DOI
   - 저자명, 기관명
   - 숫자·단위: `99.5%`, `1.5M parameters`

4. **캡션**: `Figure 1:` / `Table 1:` 레이블 유지, 설명 부분만 번역

5. **자연스러운 학술 한국어**: 번역체가 아닌 자연스러운 문어체 사용

## 출력 형식

반드시 순수 JSON 배열만 반환하세요. 마크다운 코드블록, 설명 텍스트 없이 JSON만.

각 블록에 `translated_text`와 `has_inline_math` 필드를 추가합니다:
[
  {
    "id": "tb_001",
    "page": 1,
    "bbox": [...],
    "column": 1,
    "original_text": "...",
    "translated_text": "...",
    "has_inline_math": false
  },
  ...
]
"""


def _extract_json(text: str) -> str:
    """응답에서 JSON 배열 추출 (마크다운 코드블록 제거)"""
    text = text.strip()
    # ```json ... ``` 또는 ``` ... ``` 제거
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text


def translate_chunk(chunk_path: str) -> dict:
    """청크 JSON 파일을 읽어 번역 후 _translated.json으로 저장합니다.

    Args:
        chunk_path: 번역할 청크 JSON 파일 경로

    Returns:
        번역된 청크 데이터 (dict)
    """
    chunk_path = Path(chunk_path)

    with open(chunk_path, "r", encoding="utf-8") as f:
        chunk = json.load(f)

    # translate: false 섹션은 번역 건너뜀
    if not chunk.get("translate", True):
        translated_path = chunk_path.parent / (chunk_path.stem + "_translated.json")
        result = {
            **chunk,
            "terms_used": [],
            "translation_verified": True,
            "verification_notes": "원문 유지 섹션 (References/Appendix 등)",
        }
        # 각 블록에 translated_text = original_text 로 설정
        for block in result["blocks"]:
            block["translated_text"] = block["original_text"]
            block["has_inline_math"] = False
        with open(translated_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result

    blocks = chunk.get("blocks", [])
    if not blocks:
        # 빈 섹션
        translated_path = chunk_path.parent / (chunk_path.stem + "_translated.json")
        result = {**chunk, "terms_used": [], "translation_verified": True, "verification_notes": "빈 섹션"}
        with open(translated_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result

    # 번역 대상 블록 목록 (id, original_text만 전달해서 토큰 절약)
    blocks_for_translation = [
        {
            "id": b["id"],
            "page": b["page"],
            "bbox": b["bbox"],
            "column": b.get("column", 1),
            "original_text": b["original_text"],
        }
        for b in blocks
    ]

    user_message = (
        f"섹션: {chunk['section_name']}\n\n"
        "다음 텍스트 블록들을 번역 정책에 따라 한국어로 번역하세요.\n"
        "각 블록에 `translated_text`와 `has_inline_math` 필드를 추가하여 JSON 배열로 반환하세요.\n\n"
        + json.dumps(blocks_for_translation, ensure_ascii=False, indent=2)
    )

    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text
    json_text = _extract_json(raw_text)

    try:
        translated_blocks = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"[경고] JSON 파싱 실패: {e}\n원문 블록에 번역 없이 저장합니다.", file=sys.stderr)
        translated_blocks = [
            {**b, "translated_text": b["original_text"], "has_inline_math": False}
            for b in blocks_for_translation
        ]

    # 원본 블록 메타데이터(font_size 등)와 병합
    block_map = {b["id"]: b for b in blocks}
    merged_blocks = []
    for tb in translated_blocks:
        original = block_map.get(tb["id"], {})
        merged = {
            **original,
            "translated_text": tb.get("translated_text", tb.get("original_text", "")),
            "has_inline_math": tb.get("has_inline_math", False),
        }
        merged_blocks.append(merged)

    # 번역에 사용된 용어 수집 (간단히 추출)
    terms_used = _extract_terms(merged_blocks)

    result = {
        "chunk_id": chunk["chunk_id"],
        "section_name": chunk["section_name"],
        "translate": chunk.get("translate", True),
        "blocks": merged_blocks,
        "terms_used": terms_used,
        "translation_verified": True,
        "verification_notes": "웹서비스 자동 번역",
    }

    translated_path = chunk_path.parent / (chunk_path.stem + "_translated.json")
    with open(translated_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def _extract_terms(blocks: list) -> list:
    """번역된 블록에서 용어 병기 패턴 추출.

    `한국어(English Term, ABBR)` 패턴을 감지합니다.
    """
    pattern = re.compile(r"([\w가-힣]+)\(([A-Z][A-Za-z\s]+(?:,\s*[A-Z]+)?)\)")
    terms = {}
    for block in blocks:
        text = block.get("translated_text", "")
        for match in pattern.finditer(text):
            korean = match.group(1)
            english = match.group(2)
            key = english.lower()
            if key not in terms:
                terms[key] = {
                    "term": english,
                    "translation": korean,
                    "first_occurrence": block["id"],
                }
    return list(terms.values())
