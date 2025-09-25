from __future__ import annotations

from typing import Callable, Iterable, List, Optional

import startupper.startup_namer as sn


class FakeAgent(sn.NameRiffAgent):
    """Deterministic riff agent for tests.

    - By default returns ["Alpha", "Beta", "Gamma", ...] up to the requested count.
    - You can force a custom list via names=... (it will be truncated to count).
    """

    def __init__(self, names: Optional[Iterable[str]] = None) -> None:
        self._names = list(names) if names is not None else None

    def riff(self, base: str, count: int, model: str | None = None) -> List[str]:
        if self._names is not None:
            return list(self._names)[:count]
        seed = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"]
        out: List[str] = []
        while len(out) < count:
            out.extend(seed)
        return out[:count]


class FakeDomainChecker(sn.DomainChecker):
    """Deterministic domain checker.

    - By default alternates availability and increments price.
    - You can pass a factory to control how DomainResult objects are created.
    """

    def __init__(self, factory: Optional[Callable[[int, str], sn.DomainResult]] = None) -> None:
        self._factory = factory

    def check(self, domains: List[str]) -> List[sn.DomainResult]:
        out: List[sn.DomainResult] = []
        for i, d in enumerate(domains):
            if self._factory is not None:
                out.append(self._factory(i, d))
            else:
                out.append(
                    sn.DomainResult(
                        domain=d,
                        available=bool(i % 2),
                        price=10.0 + i,
                        currency="USD",
                    )
                )
        return out

