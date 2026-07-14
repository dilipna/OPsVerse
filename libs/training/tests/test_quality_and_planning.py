from opsverse_training.generate_instructions import plan_tasks
from opsverse_training.quality import Deduper, quality_drop_reason
from opsverse_training.schemas import DatasetManifest, InstructionPair, Message

GOOD_USER = "How do I configure liveness probes for a Deployment in Kubernetes?"
GOOD_ASSISTANT = (
    "Add a livenessProbe to the container spec. For an HTTP check, set "
    "httpGet.path and port, then tune initialDelaySeconds and periodSeconds "
    "so the kubelet only restarts genuinely wedged containers."
)


def test_quality_accepts_good_pair():
    assert quality_drop_reason(GOOD_USER, GOOD_ASSISTANT) is None


def test_quality_drop_reasons():
    assert quality_drop_reason("hi", GOOD_ASSISTANT) == "user_too_short"
    assert quality_drop_reason(GOOD_USER, "short") == "assistant_too_short"
    assert quality_drop_reason(GOOD_USER, "x" * 9000) == "assistant_too_long"
    # scaffold leaks teach the model to cite context it won't have
    leaked = GOOD_ASSISTANT + " This is described in the provided excerpt."
    assert quality_drop_reason(GOOD_USER, leaked) == "scaffold_leak"
    assert quality_drop_reason(GOOD_USER * 3, GOOD_USER * 3) == "user_equals_assistant"


def test_deduper_exact_and_near():
    deduper = Deduper()
    assert not deduper.is_duplicate(GOOD_USER)
    deduper.add(GOOD_USER)
    # exact modulo normalization
    assert deduper.is_duplicate(GOOD_USER.upper())
    # near-duplicate: same question with filler words keeps shingle overlap high
    assert deduper.is_duplicate(
        "Hey, how do I configure liveness probes for a Deployment in Kubernetes?"
    )
    # one load-bearing word changed = a different question, NOT a duplicate
    assert not deduper.is_duplicate(
        "How do I configure liveness probes for a StatefulSet in Kubernetes?"
    )
    assert not deduper.is_duplicate("What is a Terraform state file?")


def test_plan_tasks_round_robins_formats():
    rows = [{"chunk_id": f"c{i}"} for i in range(7)]
    tasks = plan_tasks(rows, 6)
    assert [fmt for _, fmt in tasks] == ["qa", "explain", "diagnosis", "qa", "explain", "diagnosis"]
    # one task per document, capped at n
    assert [row["chunk_id"] for row, _ in tasks] == [f"c{i}" for i in range(6)]


def test_instruction_pair_roundtrip_and_manifest():
    pair = InstructionPair(
        id="c1:qa",
        format="qa",
        messages=[
            Message(role="user", content=GOOD_USER),
            Message(role="assistant", content=GOOD_ASSISTANT),
        ],
        source_chunk_ids=["c1"],
        tool="kubernetes",
        generator_model="gemini/test",
    )
    loaded = InstructionPair.model_validate_json(pair.model_dump_json())
    assert loaded.user_text == GOOD_USER
    assert loaded.assistant_text == GOOD_ASSISTANT

    manifest = DatasetManifest(
        name="instructions",
        version="1",
        generator_model="gemini/test",
        examples=1,
        decontamination={"dropped": 0},
    )
    assert "decontamination" in manifest.model_dump()
