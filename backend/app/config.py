import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class ConfigError(RuntimeError):
    """필수 설정이 없어 API를 시작할 수 없다."""


def _read_env_file(path: Path) -> dict[str, str]:
    # 새 패키지 없이 KEY=VALUE 줄만 읽는다. 값은 어디에도 출력하지 않는다.
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def get_anthropic_api_key(env_path: Path | None = None) -> str:
    # 없어도 서버는 시작한다. 호출하는 쪽이 503으로 응답한다. 값은 메시지에 넣지 않는다.
    value = os.environ.get("ANTHROPIC_API_KEY") or _read_env_file(env_path or ENV_PATH).get(
        "ANTHROPIC_API_KEY", ""
    )
    value = value.strip()
    if not value:
        raise ConfigError("ANTHROPIC_API_KEY 가 비어 있습니다.")
    return value


def get_session_secret(env_path: Path | None = None) -> str:
    # 환경변수가 우선이고, 없으면 backend/.env 를 본다. 비어 있으면 시작을 거부한다.
    value = os.environ.get("SESSION_SECRET") or _read_env_file(env_path or ENV_PATH).get(
        "SESSION_SECRET", ""
    )
    value = value.strip()
    if not value:
        raise ConfigError(
            "SESSION_SECRET 이 비어 있습니다. backend/.env 에 값을 넣어야 API를 시작합니다."
        )
    return value
