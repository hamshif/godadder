import uvicorn
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Response
from pydantic import BaseModel, Field
from typing import List, Optional

import pydantic_ai as pai
from pydantic_ai.models.function import FunctionModel
import time
import logging
import wielder.infra.wollama as wol
import requests

logger = logging.getLogger(__name__)

# POLICY: Ollama fail-fast
# ---------------------------------
# This service’s only model backend is Ollama. We intentionally fail
# application startup if Ollama is unreachable (except when running
# under pytest where FastAPI lifespan is not required for unit tests).
# Rationale: running without the model leads to misleading behavior
# and hidden errors. If future requirements change, update this policy
# deliberately and audit all callers/tests that rely on fail-fast.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enforce Ollama reachability at startup (except under pytest).
    # This app depends solely on Ollama; fail-fast if unavailable.
    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    do_warmup = os.getenv("OLLAMA_WARMUP", "0") == "1"

    if not os.getenv("PYTEST_CURRENT_TEST"):
        if not wol.is_reachable(base_url, timeout=2.0):
            logger.error("Ollama not reachable at %s — aborting startup", base_url)
            raise RuntimeError(f"Ollama not reachable at {base_url}")
        present = wol.model_present(base_url, model, timeout=2.5)
        if present is False:
            logger.warning("Ollama model not present at startup: %s", model)

    def _warmup():
        try:
            wol.warm_model(base_url, model)
        except Exception:
            # Never fail startup because of warmup
            logger.debug("Warmup encountered an error; continuing startup.", exc_info=True)

    if do_warmup and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            t = threading.Thread(target=_warmup, daemon=True)
            t.start()
        except Exception:
            logger.debug("Failed to start warmup thread; continuing.", exc_info=True)
    yield


app = FastAPI(
    title="Name Riffer",
    description="Riff startup domain names via PydanticAI + Ollama.",
    version="1.0.0",
    lifespan=lifespan,
)
class RiffRequest(BaseModel):
    base: str
    count: int = Field(ge=1, le=50)
    model: Optional[str] = None


class NamesResponse(BaseModel):
    names: List[str]
 
# WET hardcoded generation options for quick tweaking during development
# Tuned for higher creativity with acceptable latency. Per-request we
# compute `num_predict` dynamically from `count` (see `riff`).
OLLAMA_OPTIONS: dict = {
    "temperature": 0.8,
    "top_p": 0.9,
    "top_k": 100,
}
_cpu_threads = os.cpu_count() or 1
if _cpu_threads > 0:
    OLLAMA_OPTIONS["num_thread"] = _cpu_threads
class NameRiffAgent:
    def riff(self, base: str, count: int, model: Optional[str] = None) -> List[str]:
        raise NotImplementedError


class DefaultNameRiffAgent(NameRiffAgent):
    def __init__(self, model: str = "qwen2.5:0.5b", url: str = "http://127.0.0.1:11434/api/generate", options: dict | None = None):
        self.model = model
        self.url = url
        self.options = dict(options or OLLAMA_OPTIONS)

    def riff(self, base: str, count: int, model: Optional[str] = None) -> List[str]:
        model_name = (model or self.model)

        def compute_num_predict(n: int) -> int:
            # Budget ~8 tokens per name line; clamp to [64, 256]
            return max(64, min(256, 8 * max(1, int(n))))

        def ollama_fn_model(messages, agent_info) -> pai.messages.ModelResponse:
            sys_text, user_text = [], []
            for m in messages:
                for p in getattr(m, "parts", []):
                    cls = p.__class__.__name__
                    content = getattr(p, "content", "")
                    if cls == "SystemPromptPart":
                        sys_text.append(content)
                    elif cls == "UserPromptPart":
                        if isinstance(content, str):
                            user_text.append(content)
                        else:
                            user_text.extend([x for x in content if isinstance(x, str)])
            prompt_text = "\n\n".join([t for t in ("\n\n".join(sys_text), "\n\n".join(user_text)) if t])

            t0 = time.perf_counter()
            try:
                npredict = compute_num_predict(count)
                effective_options = {**self.options, "num_predict": npredict}
                logger.debug(
                    "riff: preparing ollama.generate model=%s num_predict=%d options={temperature=%s, top_p=%s, top_k=%s, num_thread=%s}",
                    model_name,
                    npredict,
                    effective_options.get("temperature"),
                    effective_options.get("top_p"),
                    effective_options.get("top_k"),
                    effective_options.get("num_thread"),
                )
                output = wol.generate(
                    self.url,
                    model_name,
                    prompt_text,
                    timeout=60,
                    options=effective_options,
                    stream=True,
                    stop_after_lines=count,
                )
            except requests.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 404:
                    logger.error("Ollama model not found during generate: model=%s url=%s", model_name, self.url)
                    raise HTTPException(status_code=502, detail=f"Ollama model not found: {model_name}")
                logger.exception("Ollama HTTP error during generate: %s", e)
                raise HTTPException(status_code=502, detail="Ollama HTTP error")
            except requests.RequestException as e:
                logger.exception("Ollama request error during generate: %s", e)
                raise HTTPException(status_code=502, detail="Ollama request error")
            except Exception as e:
                logger.exception("Unexpected error during Ollama generate: %s", e)
                raise HTTPException(status_code=502, detail=f"Ollama error: {e}")
            finally:
                dt = (time.perf_counter() - t0) * 1000.0
                logger.debug("riff: ollama.generate took %.1f ms", dt)
            return pai.messages.ModelResponse(parts=[pai.messages.TextPart(content=output)])

        agent = pai.Agent(
            model=FunctionModel(function=ollama_fn_model, model_name=f"ollama:{self.model}"),
            system_prompt=(
                "You are a naming assistant. "
                f"Suggest exactly {count} creative, brandable domain names inspired by '{base}'. "
                "Return ONLY a plain list, one per line, no numbering, no bullets."
            ),
        )

        t1 = time.perf_counter()
        result = agent.run_sync(f"Base domain: {base}\nCount: {count}\nGenerate now.")
        dt = (time.perf_counter() - t1) * 1000.0
        logger.debug("riff: agent.run_sync total %.1f ms", dt)
        text = str(getattr(result, "output", result)).strip()
        names = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        return names[:count]


_ollama_base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
default_riff_agent: NameRiffAgent = DefaultNameRiffAgent(model=_ollama_model, url=f"{_ollama_base}/api/generate", options=OLLAMA_OPTIONS)


def get_riff_agent() -> NameRiffAgent:
    return default_riff_agent


@app.post("/riff-names", response_model=NamesResponse)
def riff_names(request: RiffRequest, response: Response, agent: NameRiffAgent = Depends(get_riff_agent)):
    timing = os.getenv("RIFF_TIMING", "0") == "1"
    t0 = time.perf_counter() if timing else None
    try:
        names = agent.riff(request.base, request.count, model=request.model)
        if timing and t0 is not None:
            dt = (time.perf_counter() - t0) * 1000.0
            response.headers["X-Riff-Server-Ms"] = f"{dt:.1f}"
        return NamesResponse(names=names)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Riff error: {e}")


@app.get("/health")
def health():
    """Lightweight health check with Ollama reachability info."""

    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    reachable = wol.is_reachable(base_url, timeout=1.5)
    model_present = wol.model_present(base_url, model, timeout=2.0) if reachable else None

    return {
        "ok": True,
        "ollama": {"reachable": reachable, "model": model, "model_present": model_present},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
