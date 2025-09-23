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

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hardcoded warmup: block startup until model is warm to avoid slow first request
    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.8b")
    wol.warm_model(base_url, model)
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
OLLAMA_OPTIONS: dict = {
    "num_predict": 32,
    "temperature": 0.4,
    "top_p": 0.85,
    "top_k": 50,
}
_cpu_threads = os.cpu_count() or 1
if _cpu_threads > 0:
    OLLAMA_OPTIONS["num_thread"] = _cpu_threads
class NameRiffAgent:
    def riff(self, base: str, count: int, model: Optional[str] = None) -> List[str]:
        raise NotImplementedError


class DefaultNameRiffAgent(NameRiffAgent):
    def __init__(self, model: str = "qwen2.5:1.8b", url: str = "http://127.0.0.1:11434/api/generate", options: dict | None = None):
        self.model = model
        self.url = url
        self.options = dict(options or OLLAMA_OPTIONS)

    def riff(self, base: str, count: int, model: Optional[str] = None) -> List[str]:
        model_name = (model or self.model)

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
                output = wol.generate(
                    self.url,
                    model_name,
                    prompt_text,
                    timeout=60,
                    options=self.options,
                    stream=True,
                    stop_after_lines=count,
                )
            except Exception as e:
                output = f"Error calling Ollama: {e}"
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
_ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.8b")
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
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.8b")
    reachable = wol.is_reachable(base_url, timeout=1.5)
    model_present = wol.model_present(base_url, model, timeout=2.0) if reachable else None

    return {
        "ok": True,
        "ollama": {"reachable": reachable, "model": model, "model_present": model_present},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
