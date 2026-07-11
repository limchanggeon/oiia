"""k-skill CLI subprocess 어댑터 — 도구 담당 팀원 통합 지점.

계약 (이것만 지키면 FastAPI 쪽 수정 없이 연결된다):
    $ echo '{"origin":"서울","dest":"부산", ...}' | k-skill run <skill-name> --json
    → stdout에 JSON 한 덩어리 출력, 성공 시 exit code 0

- 바이너리 경로는 KSKILL_BIN 환경변수 (기본 "k-skill", PATH에서 탐색)
- 스킬 무수정 원칙: 이 어댑터는 스킬 출력에 손대지 않고 그대로 반환한다
- 호출 측(run_tool)이 실패 시 cache → mock으로 폴백하므로
  여기서는 실패를 예외로 올리기만 하면 된다
"""
import json
import subprocess
from typing import Any, Dict

from ..config import settings


class KSkillError(RuntimeError):
    pass


def run_skill(skill: str, payload: Dict[str, Any], timeout: float = 15.0) -> Any:
    try:
        proc = subprocess.run(
            [settings.kskill_bin, "run", skill, "--json"],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise KSkillError(f"k-skill 바이너리를 찾을 수 없습니다: {settings.kskill_bin}")
    except subprocess.TimeoutExpired:
        raise KSkillError(f"k-skill 타임아웃 ({skill}, {timeout}s)")

    if proc.returncode != 0:
        raise KSkillError(f"k-skill 실패 ({skill}, exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise KSkillError(f"k-skill 출력이 JSON이 아닙니다 ({skill}): {proc.stdout.strip()[:200]}")
