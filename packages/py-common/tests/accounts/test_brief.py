from dataclasses import replace

import pytest

from igs_common.accounts import generate_brief, inputs_hash
from igs_common.accounts.health import compute_health
from igs_common.db.enums import AccountHealth
from igs_common.llm import FakeLLM, LLMError, Role, Scripted

from .helpers import BALANCE_FACT, EMAIL, TODAY, snapshot


def _sentences(*items: tuple[str, list[int]]) -> Scripted:
    return Scripted(json={"sentences": [{"text": t, "sources": s} for t, s in items]})


async def test_brief_keeps_only_cited_sentences_and_renumbers() -> None:
    snap = snapshot(facts=(BALANCE_FACT,))
    # Sources: S0 system, S1 = EMAIL (fact source first), S2 = CALL.
    llm = FakeLLM(
        [
            _sentences(
                ("Lakeshore tiene la gira confirmada para marzo [S0].", [0]),
                ("AP libera el saldo en cinco días hábiles.", [1, 1]),
                ("Haines está muy enojado.", [99]),  # invalid source → dropped
                ("Sin fuentes.", []),  # uncited → dropped
                ("Dos jugadoras son celíacas.", [2]),
            )
        ]
    )
    brief = await generate_brief(llm, snap, today=TODAY, model="m")

    assert brief.text == (
        "Lakeshore tiene la gira confirmada para marzo. [1] "
        "AP libera el saldo en cinco días hábiles. [2] "
        "Dos jugadoras son celíacas. [3]"
    )
    assert [(c.n, c.interaction_id) for c in brief.citations] == [
        (1, None),
        (2, EMAIL.id),
        (3, snap.interactions[0].id),
    ]
    assert brief.dropped_sentences == 2
    assert brief.health is AccountHealth.GREEN
    (request,) = llm.requests
    assert request.role is Role.AGENT
    prompt = request.items[0].content  # type: ignore[union-attr]
    assert '<source id="S1" kind="interaction">' in prompt and "(fuente: S1)" in prompt


async def test_brief_without_any_supported_sentence_fails() -> None:
    llm = FakeLLM([_sentences(("Nada.", [42]))])
    with pytest.raises(LLMError):
        await generate_brief(llm, snapshot(), today=TODAY, model="m")


def test_inputs_hash_tracks_every_input() -> None:
    snap = snapshot()
    health = compute_health(snap, today=TODAY)
    base = inputs_hash(snap, health, today=TODAY, model="m")
    assert base == inputs_hash(snap, health, today=TODAY, model="m")
    with_fact = snapshot(facts=(BALANCE_FACT,))
    assert base != inputs_hash(with_fact, health, today=TODAY, model="m")
    assert base != inputs_hash(snap, health, today=TODAY.replace(day=23), model="m")
    assert base != inputs_hash(snap, health, today=TODAY, model="other")
    closed = snapshot(facts=(replace(BALANCE_FACT, status="done"),))
    assert inputs_hash(with_fact, health, today=TODAY, model="m") != inputs_hash(
        closed, health, today=TODAY, model="m"
    )
