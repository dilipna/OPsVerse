import json
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

REPORT = {"report": "retrieval-ablation-v1", "kind": "retrieval-ablation", "results": {}}


def wire_reports(env, tmp_path):
    (tmp_path / "retrieval-ablation-v1-summary.json").write_text(json.dumps(REPORT))
    (tmp_path / "not-a-summary.md").write_text("# nope")
    # lifespan doesn't run under ASGITransport; the router only reads reports_dir
    env.app.state.settings = SimpleNamespace(reports_dir=str(tmp_path))


async def test_list_and_get_reports(env, tmp_path):
    wire_reports(env, tmp_path)
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        listed = await client.get("/v1/evals/reports")
        assert listed.status_code == 200
        assert [r["report"] for r in listed.json()] == ["retrieval-ablation-v1"]

        one = await client.get("/v1/evals/reports/retrieval-ablation-v1")
        assert one.status_code == 200
        assert one.json()["kind"] == "retrieval-ablation"

        missing = await client.get("/v1/evals/reports/nope")
        assert missing.status_code == 404

        # path traversal is rejected, not resolved
        traversal = await client.get("/v1/evals/reports/..%2f..%2fsecrets")
        assert traversal.status_code == 404
