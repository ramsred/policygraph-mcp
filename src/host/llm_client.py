import os
import json
import httpx
from typing import Any, Dict, List


def _is_running_in_container() -> bool:
    """
    Best-effort detection:
    - /.dockerenv exists in Docker
    - /proc/1/cgroup contains docker/kubepods/containerd in many runtimes
    """
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "rt", encoding="utf-8") as f:
            cgroup = f.read()
        markers = ("docker", "kubepods", "containerd")
        return any(m in cgroup for m in markers)
    except Exception:
        return False


def _default_base_url() -> str:
    # If user explicitly set it, always honor.
    env = os.getenv("LLM_BASE_URL")
    if env:
        return env.rstrip("/")

    # Otherwise pick a sensible default depending on where we run.
    if _is_running_in_container():
        # docker-compose service DNS
        return "http://llm:8000/v1"
    # local dev: docker publishes vLLM on localhost:8008
    return "http://localhost:8008/v1"


class LLMClient:
    def __init__(self) -> None:
        self.base_url = _default_base_url().rstrip("/")
        self.model = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self.api_key = os.getenv("LLM_API_KEY")  # optional for local vLLM

        self._headers = {"Content-Type": "application/json"}
        if self.api_key:
            self._headers["Authorization"] = f"Bearer {self.api_key}"

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
        timeout_s: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Calls /v1/chat/completions and expects the assistant to output JSON only.
        Returns parsed JSON dict.

        NOTE: We still defensively extract the first {...} block if the model
        accidentally adds extra text.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        url = f"{self.base_url}/chat/completions"

        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(url, headers=self._headers, json=payload)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            raise RuntimeError(
                f"LLMClient failed to reach {url}.\n"
                f"Resolved base_url={self.base_url}, model={self.model}.\n"
                f"Fixes:\n"
                f"  - Local dev: export LLM_BASE_URL=http://localhost:8008/v1\n"
                f"  - Docker-compose: run host inside compose (service DNS 'llm' works)\n"
                f"Original error: {e}"
            ) from e

        content = data["choices"][0]["message"]["content"].strip()

        # Strict parse with fallback extraction
        try:
            out = json.loads(content)
            if not isinstance(out, dict):
                raise ValueError("Model output JSON must be an object (dict).")
            return out
        except Exception:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                out = json.loads(content[start : end + 1])
                if not isinstance(out, dict):
                    raise ValueError("Model output JSON must be an object (dict).")
                return out
            raise