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
from .util import get_app_config
from .domain_helper import check_godaddy_domains, get_domain_store
from .persistence import DomainStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    reachable = wol.is_reachable(base_url, timeout=1.5)
    model_present = wol.model_present(base_url, model, timeout=2.0) if reachable else None
    return {"ok": True, "ollama": {"reachable": reachable, "model": model, "model_present": model_present}}


class DomainResult(BaseModel):
    domain: str
    available: Optional[bool] = None
    definitive: Optional[bool] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    price_error: Optional[str] = None
    error: Optional[str] = None


class DomainChecker:
    def check(self, domains: List[str]) -> List[DomainResult]:
        raise NotImplementedError


class GoDaddyDomainChecker(DomainChecker):
    def __init__(self, conf):
        self.conf = conf

    def check(self, domains: List[str]) -> List[DomainResult]:
        results_map = check_godaddy_domains(domains, self.conf)
        out: List[DomainResult] = []
        for d in domains:
            info = results_map.get(d, {}) or {}
            out.append(
                DomainResult(
                    domain=d,
                    available=info.get("available"),
                    definitive=info.get("definitive"),
                    price=info.get("price"),
                    currency=info.get("currency"),
                    price_error=info.get("price_error"),
                    error=info.get("error"),
                )
            )
        return out


_domain_checker: Optional[DomainChecker] = None


def get_domain_checker() -> DomainChecker:
    global _domain_checker
    if _domain_checker is None:
        try:
            conf = get_app_config()
        except Exception as e:
            raise RuntimeError(f"GoDaddy config load failed: {e}")
        _domain_checker = GoDaddyDomainChecker(conf)
    return _domain_checker


class CheckRequest(BaseModel):
    domains: List[str] = Field(min_length=1, max_length=100)
    persist: Optional[bool] = False


class CheckResponse(BaseModel):
    results: List[DomainResult]


@app.post("/check-domains", response_model=CheckResponse)
def check_domains(
    req: CheckRequest,
    checker: DomainChecker = Depends(get_domain_checker),
    store: DomainStore = Depends(get_domain_store),
):
    try:
        seen = set()
        ordered = []
        for d in req.domains:
            dd = d.strip().lower()
            if not dd or dd in seen:
                continue
            seen.add(dd)
            ordered.append(dd)
        results = checker.check(ordered)
        if req.persist:
            for r in results:
                try:
                    info = r.model_dump(exclude={"domain"})
                    store.upsert_domain(r.domain, info)
                except Exception:
                    logger.debug("persist upsert failed for %s", r.domain, exc_info=True)
        return CheckResponse(results=results)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Domain check error: {e}")


class RiffAndCheckRequest(BaseModel):
    base: str
    count: int = Field(ge=1, le=50)
    model: Optional[str] = None
    tlds: Optional[List[str]] = None
    persist: Optional[bool] = False


class RiffAndCheckItem(BaseModel):
    name: str
    domain: str
    available: Optional[bool] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    price_error: Optional[str] = None
    error: Optional[str] = None


class RiffAndCheckResponse(BaseModel):
    items: List[RiffAndCheckItem]
    names: List[str]


def _label_from_name(name: str) -> str:
    s = name.strip().lower()
    if "." in s:
        s = s.split(".", 1)[0]
    cleaned = "".join(ch for ch in s if ch.isalnum() or ch == "-")
    return cleaned


@app.post("/riff-and-check", response_model=RiffAndCheckResponse)
def riff_and_check(
    req: RiffAndCheckRequest,
    response: Response,
    agent: NameRiffAgent = Depends(get_riff_agent),
    checker: DomainChecker = Depends(get_domain_checker),
    store: DomainStore = Depends(get_domain_store),
):
    timing = os.getenv("RIFF_TIMING", "0") == "1"
    t0 = time.perf_counter() if timing else None
    try:
        names = agent.riff(req.base, req.count, model=req.model)
        if timing and t0 is not None:
            response.headers["X-Riff-Server-Ms"] = f"{(time.perf_counter() - t0) * 1000.0:.1f}"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Riff error: {e}")

    default_tlds = [".com", ".ai"]
    tlds = req.tlds or default_tlds
    tlds = [t if t.startswith(".") else f".{t}" for t in tlds]
    domains_to_check: List[str] = []
    domain_to_name: dict[str, str] = {}

    for nm in names:
        nm = nm.strip()
        label = _label_from_name(nm)
        if "." in nm:
            dd = nm.lower()
            domains_to_check.append(dd)
            domain_to_name[dd] = nm
        if label:
            for tld in tlds:
                dd = f"{label}{tld}"
                if dd not in domain_to_name:
                    domains_to_check.append(dd)
                    domain_to_name[dd] = nm

    seen = set()
    ordered: List[str] = []
    for d in domains_to_check:
        if d not in seen:
            seen.add(d)
            ordered.append(d)
    max_checks = int(os.getenv("CHECK_MAX", "100"))
    ordered = ordered[:max_checks]

    try:
        t1 = time.perf_counter() if timing else None
        results = checker.check(ordered)
        if timing and t1 is not None:
            response.headers["X-Check-Server-Ms"] = f"{(time.perf_counter() - t1) * 1000.0:.1f}"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Domain check error: {e}")

    items: List[RiffAndCheckItem] = []
    by_domain = {r.domain: r for r in results}
    for d in ordered:
        r = by_domain.get(d)
        if r is None:
            items.append(RiffAndCheckItem(name=domain_to_name.get(d, d), domain=d, error="no-result"))
        else:
            items.append(
                RiffAndCheckItem(
                    name=domain_to_name.get(d, d),
                    domain=r.domain,
                    available=r.available,
                    price=r.price,
                    currency=r.currency,
                    price_error=r.price_error,
                    error=r.error,
                )
            )

    if req.persist:
        for r in results:
            try:
                info = r.model_dump(exclude={"domain"})
                store.upsert_domain(r.domain, info)
            except Exception:
                logger.debug("persist upsert failed for %s", r.domain, exc_info=True)

    return RiffAndCheckResponse(items=items, names=names)


@app.get("/domains")
def list_domains(limit: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, store: DomainStore = Depends(get_domain_store)):
    """Return stored domain rows (simple JSON list)."""
    try:
        df = store.select_domains(columns=None, limit=limit, order_by=order_by, desc=desc)
        return [dict(row) for row in df.to_dict(orient="records")]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List domains error: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
