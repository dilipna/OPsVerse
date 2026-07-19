from opsverse_core.llm import LiteLLMClient


def make_client(**kw):
    return LiteLLMClient(["gemini/gemini-3.5-flash"], {"gemini": "k"}, **kw)


def test_call_kwargs_baseline():
    kwargs = make_client()._call_kwargs("gemini/gemini-3.5-flash", [])
    assert kwargs["model"] == "gemini/gemini-3.5-flash"
    assert kwargs["api_key"] == "k"
    # optional fields absent unless configured
    assert "api_base" not in kwargs
    assert "reasoning_effort" not in kwargs


def test_call_kwargs_includes_api_base_when_set():
    # the Phase-5 before/after eval path: point at a served OpsLM (vLLM/SGLang)
    client = make_client(api_base="http://localhost:8000/v1", reasoning_effort="minimal")
    kwargs = client._call_kwargs("openai/OpsLM-v1", [])
    assert kwargs["api_base"] == "http://localhost:8000/v1"
    assert kwargs["reasoning_effort"] == "minimal"


def test_api_key_resolved_by_provider_prefix():
    client = LiteLLMClient(["groq/llama"], {"gemini": "g", "groq": "q"})
    assert client._call_kwargs("groq/llama", [])["api_key"] == "q"
    # unknown provider -> no key (e.g. ollama/vllm need none)
    assert client._call_kwargs("ollama/opslm", [])["api_key"] is None
