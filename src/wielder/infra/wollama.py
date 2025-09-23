import requests
from typing import Optional
import time
import logging
import json

logger = logging.getLogger(__name__)


def is_reachable(base_url: str, timeout: float = 1.5) -> bool:
    try:
        r = requests.get(base_url, timeout=timeout)
        return 200 <= r.status_code < 500
    except Exception:
        return False


def model_present(base_url: str, model: str, timeout: float = 2.0) -> Optional[bool]:
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
        if not resp.ok:
            return None
        data = resp.json()
        models = [m.get("name") for m in data.get("models", [])]
        return model in models if model else None
    except Exception:
        return None


def warm_model(base_url: str, model: str, timeout: float = 15.0, keep_alive: str = "30m") -> None:
    """Best-effort warmup call; non-raising and non-blocking semantics by design."""
    # Quick probe to avoid long timeouts if server is down
    if not is_reachable(base_url, timeout=1.5):
        return
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": "Ready?", "stream": False, "keep_alive": keep_alive},
            timeout=timeout,
        )
        _ = resp.status_code  # ignore errors; this is a hint
    except Exception:
        pass
    finally:
        dt = (time.perf_counter() - t0) * 1000.0
        logger.debug("ollama.warm_model model=%s took %.1f ms", model, dt)


def generate(
    generate_url: str,
    model: str,
    prompt: str,
    *,
    stream: bool = False,
    keep_alive: str = "30m",
    timeout: float = 60.0,
    options: dict | None = None,
    stop_after_lines: int | None = None,
) -> str:
    """Call Ollama's /api/generate endpoint and return response text.

    Raises on HTTP/transport errors; caller may choose to handle.
    """
    body = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "keep_alive": keep_alive,
    }
    if options:
        body["options"] = options
    t0 = time.perf_counter()
    logger.debug(
        "ollama.generate POST %s model=%s stream=%s keep_alive=%s timeout=%s len(prompt)=%d",
        generate_url,
        model,
        stream,
        keep_alive,
        timeout,
        len(prompt or ""),
    )
    if stream:
        resp = requests.post(generate_url, json=body, timeout=timeout, stream=True)
        resp.raise_for_status()
        acc = ""
        last_eval_count = None
        last_eval_duration_ns = None
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                piece = obj.get("response", "")
                if piece:
                    acc += piece
                    if stop_after_lines:
                        non_empty = [ln for ln in acc.splitlines() if ln.strip()]
                        if len(non_empty) >= stop_after_lines:
                            break
                if obj.get("done"):
                    last_eval_count = obj.get("eval_count", last_eval_count)
                    last_eval_duration_ns = obj.get("eval_duration", last_eval_duration_ns)
                    break
        finally:
            try:
                resp.close()
            except Exception:
                pass
        dt = (time.perf_counter() - t0) * 1000.0
        if last_eval_count and last_eval_duration_ns:
            secs = float(last_eval_duration_ns) / 1e9
            if secs > 0:
                tps = float(last_eval_count) / secs
                logger.debug(
                    "ollama.generate streamed took %.1f ms, tokens/sec=%.1f (eval_count=%s, eval_duration_ms=%.1f)",
                    dt,
                    tps,
                    last_eval_count,
                    secs * 1000.0,
                )
            else:
                logger.debug("ollama.generate streamed took %.1f ms", dt)
        else:
            logger.debug("ollama.generate streamed took %.1f ms", dt)
        return acc
    else:
        resp = requests.post(generate_url, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        dt = (time.perf_counter() - t0) * 1000.0
        eval_count = data.get("eval_count")
        eval_dur_ns = data.get("eval_duration")
        if eval_count and eval_dur_ns:
            secs = float(eval_dur_ns) / 1e9
            if secs > 0:
                tps = float(eval_count) / secs
                logger.debug(
                    "ollama.generate status=%s took %.1f ms, tokens/sec=%.1f (eval_count=%s, eval_duration_ms=%.1f)",
                    resp.status_code,
                    dt,
                    tps,
                    eval_count,
                    secs * 1000.0,
                )
            else:
                logger.debug("ollama.generate status=%s took %.1f ms", resp.status_code, dt)
        else:
            logger.debug("ollama.generate status=%s took %.1f ms", resp.status_code, dt)
        return data.get("response", "")
