import json
import re

import anthropic
from fastapi import HTTPException

from app.config import ConfigError, get_anthropic_api_key

# AI 제안 API(suggest, breakdown)가 같이 쓴다. DB를 열지 않는다.
MODEL = "claude-haiku-5-5"

FAILED = "제안 실패"
OFF = "AI 기능 꺼짐"
BUSY = "AI가 지금 바쁩니다. 잠시 뒤에 다시 시도하세요."

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def extract_json(text: str) -> object:
    # 앞뒤에 ``` 표시가 붙어 오면 안의 내용을 분리해서 읽는다. 읽지 못하면 ValueError.
    m = _FENCE.search(text)
    raw = m.group(1) if m else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("JSON 아님") from None


def ask_model(system: str, message: str, max_tokens: int) -> str:
    # 모델의 답 글자(content[0].text)를 돌려준다. 못 받으면 HTTPException(502 또는 503).
    try:
        api_key = get_anthropic_api_key()
    except ConfigError:
        raise HTTPException(status_code=503, detail=OFF) from None

    try:
        response = make_client(api_key).messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            thinking={"type": "disabled"},
            system=system,
            messages=[{"role": "user", "content": message}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail=OFF) from None
    except (
        anthropic.RateLimitError,
        anthropic.OverloadedError,
        anthropic.ServiceUnavailableError,
        anthropic.APIConnectionError,  # 시간 초과 포함
    ):
        raise HTTPException(status_code=503, detail=BUSY) from None
    except anthropic.APIError:
        raise HTTPException(status_code=502, detail=FAILED) from None

    # 잘린 답은 쓰지 않는다.
    if response.stop_reason == "max_tokens" or not response.content:
        raise HTTPException(status_code=502, detail=FAILED)
    text = getattr(response.content[0], "text", None)
    if not isinstance(text, str):
        raise HTTPException(status_code=502, detail=FAILED)
    return text
