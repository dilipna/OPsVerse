from opsverse_evals.structured_eval import aggregate, extract_json, score_case


def test_extract_json_from_fence_and_bare():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"a": 1}') == {"a": 1}
    # prose around a JSON object still yields the object
    assert extract_json('Sure! Here it is: {"kind": "Deployment"} hope that helps') == {
        "kind": "Deployment"
    }
    assert extract_json("no json here at all") is None
    # a JSON array (not an object) is not a valid structured answer here
    assert extract_json("[1, 2, 3]") is None


def test_score_case_perfect_and_partial():
    perfect = score_case(
        {"cpu": "500m", "memory": "256Mi"}, ["cpu", "memory"], {"cpu": "500m", "memory": "256Mi"}
    )
    assert perfect == {"parseable": 1.0, "schema_valid": 1.0, "field_hits": 2, "field_total": 2}

    # case-insensitive + int/float leniency
    lenient = score_case({"level": "ERROR", "n": 3.0}, ["level"], {"level": "error", "n": 3})
    assert lenient["field_hits"] == 2

    # right schema, wrong value
    wrong = score_case({"kind": "Service"}, ["kind"], {"kind": "Deployment"})
    assert wrong == {"parseable": 1.0, "schema_valid": 1.0, "field_hits": 0, "field_total": 1}


def test_score_case_unparseable_and_missing_key():
    assert score_case(None, ["a"], {"a": 1}) == {
        "parseable": 0.0,
        "schema_valid": 0.0,
        "field_hits": 0,
        "field_total": 1,
    }
    missing = score_case({"other": 1}, ["a"], {"a": 1})
    assert missing["schema_valid"] == 0.0
    assert missing["field_hits"] == 0


def test_score_case_list_fields():
    hit = score_case({"ports": [8000, 9090]}, ["ports"], {"ports": [8000, 9090]})
    assert hit["field_hits"] == 1
    # float-typed list members normalize to ints
    coerced = score_case({"ports": [8000.0, 9090.0]}, ["ports"], {"ports": [8000, 9090]})
    assert coerced["field_hits"] == 1


def test_aggregate():
    scores = [
        {"parseable": 1.0, "schema_valid": 1.0, "field_hits": 2, "field_total": 2},
        {"parseable": 1.0, "schema_valid": 0.0, "field_hits": 0, "field_total": 1},
        {"parseable": 0.0, "schema_valid": 0.0, "field_hits": 0, "field_total": 1},
    ]
    agg = aggregate(scores)
    assert agg["json_parse_rate"] == round(2 / 3, 4)
    assert agg["schema_valid_rate"] == round(1 / 3, 4)
    assert agg["field_accuracy"] == round(2 / 4, 4)
    assert aggregate([])["json_parse_rate"] == 0.0
