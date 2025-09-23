import uvicorn
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional

import pydantic_ai as pai
from pydantic_ai.models.function import FunctionModel
import wielder.infra.wollama as wol

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("OLLAMA_WARMUP", "0") == "1":
        base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.3:latest")
        t = threading.Thread(target=wol.warm_model, args=(base_url, model), daemon=True)
        t.start()
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
class NameRiffAgent:
    def riff(self, base: str, count: int, model: Optional[str] = None) -> List[str]:
        raise NotImplementedError


class DefaultNameRiffAgent(NameRiffAgent):
    def __init__(self, model: str = "llama3.3:latest", url: str = "http://127.0.0.1:11434/api/generate"):
        self.model = model
        self.url = url

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

            try:
                output = wol.generate(self.url, model_name, prompt_text, timeout=60)
            except Exception as e:
                output = f"Error calling Ollama: {e}"
            return pai.messages.ModelResponse(parts=[pai.messages.TextPart(content=output)])

        agent = pai.Agent(
            model=FunctionModel(function=ollama_fn_model, model_name=f"ollama:{self.model}"),
            system_prompt=(
                "You are a naming assistant. "
                f"Suggest exactly {count} creative, brandable domain names inspired by '{base}'. "
                "Return ONLY a plain list, one per line, no numbering, no bullets."
            ),
        )

        result = agent.run_sync(f"Base domain: {base}\nCount: {count}\nGenerate now.")
        text = str(getattr(result, "output", result)).strip()
        names = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        return names[:count]


_ollama_base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_ollama_model = os.getenv("OLLAMA_MODEL", "llama3.3:latest")
default_riff_agent: NameRiffAgent = DefaultNameRiffAgent(model=_ollama_model, url=f"{_ollama_base}/api/generate")


def get_riff_agent() -> NameRiffAgent:
    return default_riff_agent


@app.post("/riff-names", response_model=NamesResponse)
def riff_names(request: RiffRequest, agent: NameRiffAgent = Depends(get_riff_agent)):
    try:
        names = agent.riff(request.base, request.count, model=request.model)
        return NamesResponse(names=names)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Riff error: {e}")


@app.get("/health")
def health():
    """Lightweight health check with Ollama reachability info."""

    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.3:latest")
    reachable = wol.is_reachable(base_url, timeout=1.5)
    model_present = wol.model_present(base_url, model, timeout=2.0) if reachable else None

    return {
        "ok": True,
        "ollama": {"reachable": reachable, "model": model, "model_present": model_present},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
