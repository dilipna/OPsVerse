"""Build the optional LLM injection layer for ingestion from settings.

Lives in the API package (not rype_ingestion) because it does network I/O; the
ingestion library only receives a callable. See rype_security.llm_classifier and
docs/reports/security-classifier-v1.md for what the layer measured.
"""

from __future__ import annotations

from functools import lru_cache

from rype_core.settings import Settings, get_settings
from rype_ingestion.pipeline import InjectionClassifier
from rype_security.llm_classifier import LLMInjectionClassifier


def build_injection_classifier(settings: Settings) -> InjectionClassifier | None:
    if not settings.injection_llm_model:
        return None
    if not settings.openrouter_api_key:
        raise ValueError(
            "RYPE_INJECTION_LLM_MODEL is set but OPENROUTER_API_KEY is not; "
            "refusing to start ingestion with a second layer that cannot run"
        )
    classifier = LLMInjectionClassifier(
        settings.injection_llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.injection_llm_base_url,
    )

    def classify(text: str) -> bool | None:
        verdict = classifier.classify(text)
        return None if verdict.label == "error" else verdict.is_injection

    return classify


@lru_cache
def get_injection_classifier() -> InjectionClassifier | None:
    """One instance per process, shared by the worker and the stream consumer."""
    return build_injection_classifier(get_settings())


def pipeline_options() -> dict[str, object]:
    """Keyword arguments for ingest_bytes, so every ingest path applies the layer."""
    return {
        "llm_classifier": get_injection_classifier(),
        "llm_fail_closed": get_settings().injection_llm_fail_closed,
    }
