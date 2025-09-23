import uvicorn
import os
import threading
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional

# Fail-fast if PydanticAI is not installed/available
import pydantic_ai as pai

# --- FastAPI Application Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if os.getenv("OLLAMA_WARMUP", "0") == "1":
        t = threading.Thread(target=warm_ollama_model, daemon=True)
        t.start()
    yield
    # Shutdown (no-op for now)


app = FastAPI(
    title="Name Riffer",
    description="Riff startup domain names via PydanticAI + Ollama.",
    version="1.0.0",
    lifespan=lifespan,
)


# --- 4b. Riff Startup Names Endpoint ---
class RiffRequest(BaseModel):
    base: str
    count: int = Field(ge=1, le=50)
    model: Optional[str] = None  # optional override per request


class NamesResponse(BaseModel):
    names: List[str]


# --- 4c. Name Riffing Agent (DI) ---
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
            # Build a simple prompt from system + user parts
            sys_text, user_text = [], []
            for m in messages:
                for p in getattr(m, "parts", []):
                    # duck-type on class names to avoid tight coupling
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

            body = {"model": model_name, "prompt": prompt_text, "stream": False, "keep_alive": "30m"}
            try:
                resp = requests.post(self.url, json=body, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                output = data.get("response", "")
            except Exception as e:
                output = f"Error calling Ollama: {e}"
            return pai.messages.ModelResponse(parts=[pai.messages.TextPart(content=output)])

        agent = pai.Agent(
            model=pai.models.function.FunctionModel(function=ollama_fn_model, model_name=f"ollama:{self.model}"),
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


default_riff_agent: NameRiffAgent = DefaultNameRiffAgent()


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
    reachable = False
    model_present = None
    try:
        r = requests.get(base_url, timeout=1.5)
        reachable = (200 <= r.status_code < 500)
    except Exception:
        reachable = False

    if reachable:
        try:
            tags = requests.get(f"{base_url}/api/tags", timeout=2)
            if tags.ok:
                data = tags.json()
                models = [m.get("name") for m in data.get("models", [])]
                model_present = model in models if model else None
        except Exception:
            model_present = None

    return {
        "ok": True,
        "ollama": {"reachable": reachable, "model": model, "model_present": model_present},
    }


# --- Startup: optional Ollama warm-up ---
def warm_ollama_model():

    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.3:latest")

    # Quick reachability probe (non-fatal)
    try:
        requests.get(base_url, timeout=1.5)
    except Exception:
        # Ollama isn't reachable; don't block app startup
        return

    # Best-effort warmup without blocking startup too long
    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": "Ready?", "stream": False, "keep_alive": "30m"},
            timeout=15,
        )
        # Ignore status errors; this is a warmup hint
        _ = resp.status_code
    except Exception:
        pass


# (startup handled via lifespan)

# --- 5. Server Runner ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
