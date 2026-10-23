import pytest

from igs_common.rag import filters
from igs_common.rag.filters import FilterError
from igs_common.rag.fusion import rrf


def test_with_tenant_always_wraps_and_stays_two_levels() -> None:
    assert filters.with_tenant("t", None) == {"$and": [{"tenant_id": {"$eq": "t"}}]}
    assert filters.with_tenant("t", {"source": "policy", "valid_until": {"$gte": 20000}}) == {
        "$and": [
            {"tenant_id": {"$eq": "t"}},
            {"source": {"$eq": "policy"}},
            {"valid_until": {"$gte": 20000}},
        ]
    }
    ors = filters.with_tenant("t", {"$or": [{"country": "AR"}, {"country": "BR"}]})
    assert ors == {
        "$and": [
            {"tenant_id": {"$eq": "t"}},
            {"$or": [{"country": {"$eq": "AR"}}, {"country": {"$eq": "BR"}}]},
        ]
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"tenant_id": "other"},  # tenant comes from the server
        {"$and": [{"$or": [{"country": "AR"}]}]},  # three levels
        {"$or": [{"country": "AR", "city": "BA"}]},  # multi-field item
        {"nope": "x"},  # unknown field
        {"country": {"$regex": "A.*"}},  # unknown operator
        {"country": {"$gt": "A"}},  # range on a string
        {"valid_from": {"$in": ["1"]}},  # $in on a number
        {"valid_from": "soon"},  # number field with a string
        {"$or": []},
        {"$or": [{"country": "AR"}], "city": "BA"},
    ],
)
def test_invalid_filters_are_rejected(bad: dict) -> None:
    with pytest.raises(FilterError):
        filters.normalize(bad)


def test_matches_semantics() -> None:
    p = {"source": "policy", "country": "AR", "valid_until": 21000}
    assert filters.matches(p, {"source": "policy", "valid_until": {"$gte": 20000}})
    assert not filters.matches(p, {"source": {"$in": ["guide", "email"]}})
    assert filters.matches(p, {"$or": [{"country": "BR"}, {"source": "policy"}]})
    assert filters.matches(p, {"city": {"$ne": "BA"}})  # missing field matches $ne
    assert filters.matches(p, {"city": {"$nin": ["BA"]}})
    assert not filters.matches(p, {"city": "BA"})


def test_to_sql_parameterizes_every_value() -> None:
    where, params = filters.to_sql(
        {"$or": [{"account_id": "a"}, {"source": {"$in": ["email", "call"]}}]}
    )
    assert (
        where
        == "(account_id = CAST(:f0 AS uuid) OR (payload->>'source') = ANY(CAST(:f1 AS text[])))"
    )
    assert params == {"f0": "a", "f1": ["email", "call"]}
    assert filters.to_sql({}) == ("TRUE", {})


def test_rrf_matches_reference_formula() -> None:
    fused = dict(rrf([["a", "b", "c"], ["b", "a"]]))
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 63)
    # ties keep first appearance
    assert [k for k, _ in rrf([["a", "b", "c"], ["b", "a"]])] == ["a", "b", "c"]
    assert rrf([["x"], ["y"]], weights=[2.0, 1.0])[0][0] == "x"
