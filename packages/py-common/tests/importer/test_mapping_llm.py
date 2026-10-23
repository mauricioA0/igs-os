"""The AI column mapper only proposes known fields, above a confidence bar, from value shapes."""

from igs_common.importer.mapping import match_headers, suggest_with_llm
from igs_common.importer.parse import read_file
from igs_common.importer.schema import SPECS, Entity
from igs_common.llm import FakeLLM, Message, Scripted

CSV = (
    b"Programa,Kickoff,Back home,Where,Nation,Precio x pax,Head,Org\n"
    b"IGS-5,2027-03-12,2027-03-20,Rosario,Argentina,2890,Women's tour,Lakeshore University\n"
)


async def test_llm_maps_unknown_headers_and_bad_suggestions_are_dropped() -> None:
    [sheet] = read_file(CSV, "trips.csv")
    spec = SPECS[Entity.TRIPS]
    base = match_headers(spec, sheet.headers)
    assert base.index_of() == {}
    llm = FakeLLM(
        [
            Scripted(
                json={
                    "columns": [
                        {"header": "Programa", "field": "code", "confidence": 0.9, "reason": "id"},
                        {
                            "header": "Kickoff",
                            "field": "start_date",
                            "confidence": 0.8,
                            "reason": "d",
                        },
                        {
                            "header": "Back home",
                            "field": "end_date",
                            "confidence": 0.8,
                            "reason": "d",
                        },
                        {"header": "Where", "field": "city", "confidence": 0.7, "reason": "place"},
                        {"header": "Nation", "field": "country", "confidence": 0.95, "reason": "c"},
                        {
                            "header": "Precio x pax",
                            "field": "price_per_person_usd",
                            "confidence": 0.9,
                            "reason": "$",
                        },
                        {"header": "Head", "field": "title", "confidence": 0.4, "reason": "unsure"},
                        {
                            "header": "Org",
                            "field": "made_up_field",
                            "confidence": 0.99,
                            "reason": "x",
                        },
                        {"header": "Nation", "field": "city", "confidence": 0.65, "reason": "dup"},
                        {
                            "header": "Not a header",
                            "field": "title",
                            "confidence": 0.99,
                            "reason": "x",
                        },
                    ]
                }
            )
        ]
    )
    mapped = await suggest_with_llm(llm, spec, sheet, base)
    assert mapped.index_of() == {
        "code": 0,
        "start_date": 1,
        "end_date": 2,
        "city": 3,
        "country": 4,
        "price_per_person_usd": 5,
    }
    assert all(c.source == "llm" for c in mapped.columns if c.field)
    # Low confidence, invented fields and unknown headers are discarded.
    assert mapped.columns[6].field is None and mapped.columns[7].field is None
    [request] = llm.requests
    prompt = "\n".join(i.content for i in request.items if isinstance(i, Message))
    for value in ("Rosario", "Lakeshore", "2890", "IGS-5"):
        assert value not in prompt  # headers and shapes only, never cell values


async def test_nothing_to_map_means_no_model_call() -> None:
    [sheet] = read_file(b"code,title\nX,Y\n", "trips.csv")
    spec = SPECS[Entity.TRIPS]
    llm = FakeLLM([])
    mapping = match_headers(spec, sheet.headers)
    assert await suggest_with_llm(llm, spec, sheet, mapping) is mapping
    assert llm.requests == []
