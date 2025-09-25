from __future__ import annotations

import startupper.startup_namer as sn


def test_default_agent_strips_list_markers_and_numbers(monkeypatch):
    # Simulate Ollama streaming output containing numbered/bulleted lines and a lone number
    numbered = (
        "1. Magnify\n"
        "2. MagniCity\n"
        "3. MagniWorld\n"
        "4) Magnifico\n"
        "- MagniNetworks\n"
        "6\n"
    )

    def fake_generate(url, model, prompt, **kwargs):  # signature match is loose for test
        return numbered

    monkeypatch.setattr(sn.wol, "generate", fake_generate)

    agent = sn.DefaultNameRiffAgent(model="dummy", url="http://dummy/api/generate")
    names = agent.riff("Magniv", 5)

    # Expect list markers removed and the numeric-only line dropped
    assert names == [
        "Magnify",
        "MagniCity",
        "MagniWorld",
        "Magnifico",
        "MagniNetworks",
    ]
