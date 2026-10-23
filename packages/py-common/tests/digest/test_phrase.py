from igs_common.digest import build_digest, phrase_summary, template_summary
from igs_common.llm import FakeLLM, LLMError, Message, Scripted

from .helpers import NOW, inputs


class BrokenLLM(FakeLLM):
    async def generate(self, *args, **kwargs):  # type: ignore[no-untyped-def,override]
        raise LLMError("provider down")


async def test_model_summary_is_used_when_every_number_checks_out() -> None:
    facts = build_digest(inputs(), now=NOW)
    text = "Lakeshore está en rojo: los fees de 24 × US$95 siguen impagos. Decidí la aprobación."
    llm = FakeLLM([Scripted(json={"summary": text})])
    phrased = await phrase_summary(llm, facts)
    assert (phrased.source, phrased.summary, phrased.model) == ("llm", text, "fake-model")
    [request] = llm.requests
    assert request.output_model is not None
    first = request.items[0]
    assert isinstance(first, Message) and "Lakeshore University" in first.content  # facts as JSON


async def test_invented_number_gets_one_retry_with_the_offending_tokens() -> None:
    facts = build_digest(inputs(), now=NOW)
    good = "Lakeshore sigue en rojo con US$2,280 impagos."
    llm = FakeLLM(
        [Scripted(json={"summary": "Lakeshore debe US$3,000."}), Scripted(json={"summary": good})]
    )
    phrased = await phrase_summary(llm, facts)
    assert phrased.source == "llm" and phrased.summary == good
    retry = llm.requests[1].items[-1]
    assert isinstance(retry, Message) and "3,000" in retry.content


async def test_two_bad_attempts_fall_back_to_the_template() -> None:
    facts = build_digest(inputs(), now=NOW)
    bad = Scripted(json={"summary": "Hay 7 clientes en rojo."})
    phrased = await phrase_summary(FakeLLM([bad, bad]), facts)
    assert phrased.source == "template" and phrased.summary == template_summary(facts)
    assert phrased.rejected == ("7",)


async def test_provider_errors_and_no_model_use_the_template() -> None:
    facts = build_digest(inputs(), now=NOW)
    assert (await phrase_summary(BrokenLLM([]), facts)).source == "template"
    phrased = await phrase_summary(None, facts)
    assert phrased.summary.startswith("Lo primero: Lakeshore University — Decidir la aprobación")


async def test_empty_day_template() -> None:
    from igs_common.digest import DigestInputs

    facts = build_digest(DigestInputs(), now=NOW)
    assert template_summary(facts) == "Sin pendientes urgentes hoy."
