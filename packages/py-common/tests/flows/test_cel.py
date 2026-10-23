import pytest

from igs_common.flows import cel

CTX = {
    "trigger": {
        "trip": {"id": "t-2711", "startDate": "2027-03-07"},
        "item": {"title": "vs Belgrano"},
    },
    "vars": {"leadId": "l-501", "count": 3},
    "nodes": {
        "list_unconfirmed": {
            "output": {
                "items": [
                    {"id": "i1", "title": "Bus", "providerName": "Transportes RdlP"},
                    {"id": "i2", "title": "Referee", "providerName": "Árbitros AFA"},
                ]
            }
        }
    },
    "execution": {"id": "ex-1", "now": "2027-01-01T12:00:00+00:00"},
}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{{ trigger.trip.id }}", "t-2711"),
        ("{{ vars.count }}", 3),  # single placeholder keeps its type
        ("{{ size(nodes.list_unconfirmed.output.items) > 1 }}", True),
        ("Trip {{ trigger.trip.id }} has {{ vars.count }} items", "Trip t-2711 has 3 items"),
        ("{{ nodes.list_unconfirmed.output.items.map(i, i.id) }}", ["i1", "i2"]),
        (
            "{{ nodes.list_unconfirmed.output.items.map(i, i.title + ' (' + i.providerName + ')')"
            ".join(', ') }}",
            "Bus (Transportes RdlP), Referee (Árbitros AFA)",
        ),
        (
            "{{ timestamp(trigger.trip.startDate + 'T09:00:00-03:00') - duration('720h') }}",
            "2027-02-05T09:00:00-03:00",
        ),
        ("{{ timestamp(execution.now) + duration('48h') }}", "2027-01-03T12:00:00+00:00"),
        ("{{ duration('720h') }}", "P30D"),
        ("{{ has(trigger.item.notes) ? trigger.item.notes : 'none' }}", "none"),
        ("{{ default(trigger.item.notes, 'n/a') }}", "n/a"),
        ("{{ default(trigger.item.title, 'n/a') }}", "vs Belgrano"),
        ("{{ default(trigger.missing.deep.field, 0) }}", 0),
        ("{{ formatDate(timestamp('2027-03-07T09:00:00-03:00'), 'en-US') }}", "Mar 7, 2027"),
        ("{{ formatDate(timestamp('2027-03-07T09:00:00-03:00'), 'es-AR') }}", "7 mar 2027"),
        ("{{ date(timestamp('2027-03-07T09:00:00-03:00')) }}", "2027-03-07"),
        ("{{ '  Hola  '.trim().lowerAscii() }}", "hola"),
        ("{{ 'a,b'.split(',') }}", ["a", "b"]),
        ("plain text", "plain text"),
    ],
)
def test_render(template: str, expected: object) -> None:
    assert cel.render_template(template, CTX) == expected


def test_evaluate_bool_requires_bool() -> None:
    assert cel.evaluate_bool("vars.count == 3", CTX) is True
    with pytest.raises(cel.ExpressionError, match="expected bool"):
        cel.evaluate_bool("vars.count", CTX)


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("1 +", "syntax"),
        ("", "syntax"),
        ("secrets.openai", "unknown_scope"),
        ("now()", "unknown_function"),  # no wall-clock in expressions: determinism on replay
        ("vars.name.toUpper()", "unknown_function"),
        ("x" * (cel.MAX_EXPRESSION_LENGTH + 1), "too_long"),
        ("vars.a.map(x, x.map(y, y.map(z, z.map(w, w))))", "too_complex"),
        ("default(size(vars.a), 0)", "syntax"),
    ],
)
def test_compile_errors(source: str, kind: str) -> None:
    with pytest.raises(cel.ExpressionError) as exc:
        cel.compile_expression(source)
    assert exc.value.kind == kind


def test_now_is_rejected_with_a_clear_message() -> None:
    with pytest.raises(cel.ExpressionError, match="execution.now"):
        cel.compile_expression("now() > timestamp(execution.now)")


def test_macro_variables_and_strings_are_not_scopes() -> None:
    expr = cel.compile_expression("vars.items.exists(item, item.name == 'nodes.fake')")
    assert expr.scopes == frozenset({"vars"})
    assert expr.node_refs == frozenset()


def test_node_references_are_collected() -> None:
    expr = cel.compile_expression("nodes.a.output.x + nodes['b-c'].output.y")
    assert expr.node_refs == frozenset({"a", "b-c"})


def test_missing_field_is_an_expression_error() -> None:
    with pytest.raises(cel.ExpressionError) as exc:
        cel.render_template("{{ trigger.trip.nope }}", CTX)
    assert exc.value.kind == "evaluation"
    assert "nope" in exc.value.message


def test_unbalanced_template() -> None:
    with pytest.raises(cel.ExpressionError, match="unbalanced"):
        cel.compile_template("Hello {{ vars.count }} }}")


def test_rendered_text_is_capped() -> None:
    ctx = {**CTX, "vars": {"big": "x" * (cel.MAX_RENDERED_BYTES + 1)}}
    with pytest.raises(cel.ExpressionError) as exc:
        cel.render_template("Big: {{ vars.big }}", ctx)
    assert exc.value.kind == "output"


def test_render_value_walks_nested_config() -> None:
    config = {"inputs": {"tripId": "{{ trigger.trip.id }}", "ids": ["{{ vars.count }}", 1]}}
    assert cel.render_value(config, CTX) == {"inputs": {"tripId": "t-2711", "ids": [3, 1]}}
