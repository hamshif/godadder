import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List

# --- FastAPI Application Setup ---
app = FastAPI(
    title="Name Riffer",
    description="Riff startup domain names via PydanticAI + Ollama.",
    version="1.0.0",
)


# --- 4b. Riff Startup Names Endpoint ---
class RiffRequest(BaseModel):
    base: str
    count: int = Field(ge=1, le=50)


class NamesResponse(BaseModel):
    names: List[str]


# --- 4c. Name Riffing Agent (DI) ---
class NameRiffAgent:
    def riff(self, base: str, count: int) -> List[str]:
        raise NotImplementedError


class DefaultNameRiffAgent(NameRiffAgent):
    def __init__(self, model: str = "llama3.3:latest", url: str = "http://127.0.0.1:11434/api/generate"):
        self.model = model
        self.url = url

    def riff(self, base: str, count: int) -> List[str]:
        # Lazy imports to avoid brittle module-level import failures
        import requests
        from pydantic_ai import Agent as _Agent
        from pydantic_ai.models.function import FunctionModel as _FunctionModel
        from pydantic_ai.messages import ModelResponse as _ModelResponse, TextPart as _TextPart

        def _fn_model(messages, agent_info) -> _ModelResponse:
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

            body = {"model": self.model, "prompt": prompt_text, "stream": False, "keep_alive": "30m"}
            try:
                resp = requests.post(self.url, json=body, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                output = data.get("response", "")
            except Exception as e:
                output = f"Error calling Ollama: {e}"
            return _ModelResponse(parts=[_TextPart(content=output)])

        agent = _Agent(
            model=_FunctionModel(function=_fn_model, model_name=f"ollama:{self.model}"),
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


_default_riff_agent: NameRiffAgent = DefaultNameRiffAgent()


def get_riff_agent() -> NameRiffAgent:
    return _default_riff_agent


@app.post("/riff-names", response_model=NamesResponse)
def riff_names(request: RiffRequest, agent: NameRiffAgent = Depends(get_riff_agent)):
    try:
        names = agent.riff(request.base, request.count)
        return NamesResponse(names=names)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Riff error: {e}")

# --- 5. Server Runner ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
