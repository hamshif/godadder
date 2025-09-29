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
import re
import asyncio
from collections import deque
import anyio
import httpx
from startupper.util import get_app_config
from startupper.domain_helper import check_godaddy_domains, BASE_URL, MAX_CALLS_PER_MINUTE
from startupper.persistence.domain_store import DomainStore
from startupper.persistence.sqlite_store import SQLiteDomainStore

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


tags_metadata = [
    {"name": "riff", "description": "Generate creative domain name ideas."},
    {"name": "domains", "description": "Domain availability and pricing checks."},
    {"name": "system", "description": "Service health and diagnostics."},
]

app = FastAPI(
    title="Name Riffer",
    description="Riff startup domain names via PydanticAI + Ollama.",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
)

# Default process-wide store; tests may override via DI provider
app.state.domain_store = SQLiteDomainStore()
app.state.domain_store.setup()


def provide_domain_store() -> DomainStore:
    return app.state.domain_store


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

    def estimate_token_budget(self, count: int) -> int:
        """Estimate token budget for generating `count` names (clamped).

        Policy: ~8 tokens per item, clamped to [64, 256].
        Subclasses may override to tune for different models.
        """
        return max(64, min(256, 8 * max(1, int(count))))


class DefaultNameRiffAgent(NameRiffAgent):
    def __init__(self, model: str = "qwen2.5:0.5b", url: str = "http://127.0.0.1:11434/api/generate", options: dict | None = None):
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
                token_budget = self.estimate_token_budget(count)
                # Downstream Ollama HTTP expects the option key 'num_predict'
                effective_options = {**self.options, "num_predict": token_budget}
                logger.debug(
                    "riff: preparing ollama.generate model=%s num_predict=%d options={temperature=%s, top_p=%s, top_k=%s, num_thread=%s}",
                    model_name,
                    token_budget,
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

        def _clean_name_line(line: str) -> str:
            s = line.strip()
            # Drop leading list markers like "1.", "1)", "-", "*", bullets
            s = re.sub(r"^\s*(?:\d+[\.)]\s*|[-•*]\s*)", "", s)
            # Trim stray punctuation
            s = s.strip(" -–—•*:\t")
            return s

        raw_lines = [ln for ln in text.splitlines()]
        cleaned = []
        for ln in raw_lines:
            s = _clean_name_line(ln)
            if not s or s.isdigit():
                continue
            cleaned.append(s)
        # Deduplicate while preserving order
        seen = set()
        names: List[str] = []
        for s in cleaned:
            if s not in seen:
                seen.add(s)
                names.append(s)

        # If model produced fewer names than requested, pad with base-derived fallbacks
        if len(names) < count:
            base_label = _label_from_name(base) or base.strip().lower()
            i = 1
            while len(names) < count and i <= 999:
                fallback = f"{base_label}-{i}"
                if fallback not in seen:
                    names.append(fallback)
                    seen.add(fallback)
                i += 1
        return names[:count]


_ollama_base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
default_riff_agent: NameRiffAgent = DefaultNameRiffAgent(model=_ollama_model, url=f"{_ollama_base}/api/generate", options=OLLAMA_OPTIONS)


def get_riff_agent() -> NameRiffAgent:
    return default_riff_agent


@app.post(
    "/riff-names",
    response_model=NamesResponse,
    tags=["riff"],
    summary="Riff domain names",
    description="Generate a list of brandable domain names based on a base term.",
)
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


@app.get(
    "/health",
    tags=["system"],
    summary="Service health",
    description="Lightweight health check including Ollama reachability and model presence.",
)
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
_async_checker: Optional["AsyncGoDaddyDomainChecker"] = None


def get_domain_checker() -> DomainChecker:
    global _domain_checker
    if _domain_checker is None:
        try:
            conf = get_app_config()
        except Exception as e:
            raise RuntimeError(f"GoDaddy config load failed: {e}")
        _domain_checker = GoDaddyDomainChecker(conf)
    return _domain_checker


class AsyncGoDaddyDomainChecker:
    """Async checker using httpx with bounded concurrency and a simple rate limiter."""

    def __init__(self, conf, *, max_concurrency: int = 8):
        self.conf = conf
        self.max_concurrency = max_concurrency
        self._sem = asyncio.Semaphore(max_concurrency)
        self._window: deque[float] = deque()  # request timestamps
        self._lock = asyncio.Lock()

    async def _rate_limit(self):
        # Enforce MAX_CALLS_PER_MINUTE across concurrent tasks
        while True:
            async with self._lock:
                now = asyncio.get_event_loop().time()
                # purge older than 60s
                while self._window and (now - self._window[0] >= 60.0):
                    self._window.popleft()
                if len(self._window) <  MAX_CALLS_PER_MINUTE:
                    self._window.append(now)
                    return
                # need to wait until earliest expires
                wait_for = 60.0 - (now - self._window[0]) + 0.01
            await asyncio.sleep(max(0.01, wait_for))

    async def _limited_get(self, client: httpx.AsyncClient, url: str, headers: dict, timeout: float = 10.0) -> httpx.Response:
        await self._rate_limit()
        async with self._sem:
            return await client.get(url, headers=headers, timeout=timeout)

    async def check(self, domains: List[str]) -> List[DomainResult]:
        headers = {
            "Authorization": f"sso-key {self.conf.GODADDY_API_KEY}:{self.conf.GODADDY_API_SECRET}",
            "Accept": "application/json",
        }
        out: list[DomainResult] = [None] * len(domains)  # type: ignore

        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            async def worker(idx: int, d: str):
                info: dict = {}
                try:
                    r = await self._limited_get(client, f"/domains/available?domain={d}&checkType=FAST", headers)
                    if r.status_code == 200:
                        data = r.json()
                        info["available"] = data.get("available", False)
                        info["definitive"] = data.get("definitive", False)
                    else:
                        info["error"] = f"Availability: {r.status_code} {r.text}"
                        out[idx] = DomainResult(domain=d, available=info.get("available"), definitive=info.get("definitive"), price_error=info.get("price_error"), price=info.get("price"), currency=info.get("currency"), error=info.get("error"))
                        return

                    if info.get("available"):
                        pr = await self._limited_get(client, f"/domains/price/{d}?action=register", headers)
                        if pr.status_code == 200:
                            pdata = pr.json()
                            info["price_micro"] = pdata.get("price", 0)
                            info["currency"] = pdata.get("currency", "USD")
                            info["price"] = pdata.get("price", 0) / 1_000_000
                        elif pr.status_code == 404:
                            info["price_error"] = "Pricing not available for this TLD in OTE"
                        else:
                            info["price_error"] = f"Price: {pr.status_code} {pr.text}"
                except Exception as e:
                    info["error"] = f"Exception: {e}"
                finally:
                    out[idx] = DomainResult(
                        domain=d,
                        available=info.get("available"),
                        definitive=info.get("definitive"),
                        price=info.get("price"),
                        currency=info.get("currency"),
                        price_error=info.get("price_error"),
                        error=info.get("error"),
                    )

            await asyncio.gather(*(worker(i, d) for i, d in enumerate(domains)))
        return out  # type: ignore


def get_async_domain_checker() -> "AsyncGoDaddyDomainChecker":
    global _async_checker
    if _async_checker is None:
        try:
            conf = get_app_config()
        except Exception as e:
            raise RuntimeError(f"GoDaddy config load failed: {e}")
        _async_checker = AsyncGoDaddyDomainChecker(conf)
    return _async_checker


class CheckRequest(BaseModel):
    domains: List[str] = Field(min_length=1, max_length=100)
    persist: Optional[bool] = False


class CheckResponse(BaseModel):
    results: List[DomainResult]


@app.post(
    "/check-domains",
    response_model=CheckResponse,
    tags=["domains"],
    summary="Check domain availability",
    description="Check availability and pricing for one or more domains. Optionally persist results.",
)
def check_domains(
    req: CheckRequest,
    checker: DomainChecker = Depends(get_domain_checker),
    store: DomainStore = Depends(provide_domain_store),
    async_checker: AsyncGoDaddyDomainChecker = Depends(get_async_domain_checker),
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
        threshold = int(os.getenv("CHECK_ASYNC_THRESHOLD", "4"))
        if len(ordered) >= threshold:
            results = anyio.from_thread.run(async_checker.check, ordered)
        else:
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
    persist: Optional[bool] = True


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


_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$",
    re.IGNORECASE,
)


def _looks_like_domain(text: str) -> bool:
    return bool(_DOMAIN_RE.match(text.strip().lower()))


def _label_from_name(name: str) -> str:
    # Normalize: drop list prefixes like "1.", then build a DNS-safe label
    s = re.sub(r"^\s*(?:\d+[\.)]\s*|[-•*]\s*)", "", name or "")
    s = s.strip().lower()
    cleaned = "".join(ch for ch in s if ch.isalnum() or ch == "-")
    return cleaned


@app.post(
    "/riff-and-check",
    response_model=RiffAndCheckResponse,
    tags=["domains", "riff"],
    summary="Riff names and check availability",
    description="Generate names, combine with TLDs, and check domain availability/pricing. Optionally persist results.",
)
def riff_and_check(
    req: RiffAndCheckRequest,
    response: Response,
    agent: NameRiffAgent = Depends(get_riff_agent),
    checker: DomainChecker = Depends(get_domain_checker),
    store: DomainStore = Depends(provide_domain_store),
    async_checker: AsyncGoDaddyDomainChecker = Depends(get_async_domain_checker),
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
        # Only treat as a direct domain if it actually looks like one
        if _looks_like_domain(nm):
            dd = nm.lower()
            domains_to_check.append(dd)
            domain_to_name[dd] = nm
        # Generate combinations with requested TLDs
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
        threshold = int(os.getenv("CHECK_ASYNC_THRESHOLD", "4"))
        if len(ordered) >= threshold:
            results = anyio.from_thread.run(async_checker.check, ordered)
        else:
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


@app.get(
    "/domains",
    tags=["domains"],
    summary="List persisted domains",
    description="List stored domain check results with optional sorting and limiting.",
)
def list_domains(limit: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, store: DomainStore = Depends(provide_domain_store)):
    """Return stored domain rows (simple JSON list)."""
    try:
        df = store.select_domains(columns=None, limit=limit, order_by=order_by, desc=desc)
        return [dict(row) for row in df.to_dict(orient="records")]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List domains error: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
