from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class RetrievalCase(BaseModel):
    """One labeled retrieval query.

    The gold label is the chunk the question was generated from. Because the
    corpus contains near-duplicate content across documents, harnesses report
    both chunk-level and document-level credit (see run_ablation.py).
    """

    id: str  # stable: the gold chunk id
    question: str
    relevant_chunk_ids: list[str] = Field(min_length=1)
    relevant_document_ids: list[str] = Field(min_length=1)
    source: str
    tool: str | None = None
    doc_type: str | None = None
    section: str | None = None


class RetrievalDataset(BaseModel):
    name: str
    version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generator_model: str
    corpus_stats: dict[str, int] = {}
    cases: list[RetrievalCase] = []

    def save_jsonl(self, path: Path) -> None:
        """Header line with metadata, then one case per line (diff-friendly)."""
        lines = [self.model_dump_json(exclude={"cases"})]
        lines += [case.model_dump_json() for case in self.cases]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load_jsonl(cls, path: Path) -> "RetrievalDataset":
        header, *rest = path.read_text(encoding="utf-8").splitlines()
        dataset = cls.model_validate_json(header)
        dataset.cases = [RetrievalCase.model_validate_json(line) for line in rest if line]
        return dataset


class GradedRetrievalCase(BaseModel):
    """One query with *graded, multi-label* relevance over a judged pool.

    Contrast with `RetrievalCase`, whose single gold label is inherited from the
    chunk the question was generated from. That construction makes `recall@k`
    identical to `hit@k` (ADR-0018). Here relevance is judged over a **pool**
    contributed by every retrieval mode, so a query can have many relevant
    chunks at different grades and the rank-aware metrics carry information.

    Grades follow the TREC convention:
        3 = fully answers the question
        2 = substantially relevant / partial answer
        1 = on-topic but does not answer
        0 = not relevant
    """

    id: str  # the originating chunk id, kept so cases join back to RetrievalCase
    question: str
    grades: dict[str, int] = Field(default_factory=dict)  # chunk_id -> 0..3
    pool_size: int = 0
    pool_contributors: list[str] = Field(default_factory=list)  # modes that fed the pool
    seed_chunk_id: str | None = None  # the v2 single gold label, for comparison
    seed_grade: int | None = None  # grade the judge gave that seed chunk

    def relevant_ids(self, threshold: int = 2) -> set[str]:
        """Chunk ids counted as relevant at or above `threshold`."""
        return {cid for cid, g in self.grades.items() if g >= threshold}


class GradedRetrievalDataset(BaseModel):
    name: str
    version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    judge_model: str
    relevance_threshold: int = 2
    notes: str = ""
    cases: list[GradedRetrievalCase] = []

    def save_jsonl(self, path: Path) -> None:
        lines = [self.model_dump_json(exclude={"cases"})]
        lines += [case.model_dump_json() for case in self.cases]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load_jsonl(cls, path: Path) -> "GradedRetrievalDataset":
        header, *rest = path.read_text(encoding="utf-8").splitlines()
        dataset = cls.model_validate_json(header)
        dataset.cases = [GradedRetrievalCase.model_validate_json(line) for line in rest if line]
        return dataset


class GoldenAnswer(BaseModel):
    """A reference answer for one golden query, plus its atomic claims.

    Written *from the judged-relevant chunks* (grade >= 2), not from any
    system's retrieved output -- so it is independent of what any retrieval
    mode happened to return, and can be used to score all of them fairly.

    `claims` is the answer decomposed into atomic, independently-checkable
    factual statements. Contextual recall is the share of these claims that a
    given retrieval mode's context actually supports: it measures whether
    retrieval brought back *enough to answer*, which neither faithfulness
    (reference-free) nor hit@k (did we find the seed chunk) can express.
    """

    id: str
    question: str
    reference_answer: str
    claims: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)


class GoldenAnswerSet(BaseModel):
    name: str
    version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generator_model: str
    notes: str = ""
    answers: list[GoldenAnswer] = []

    def save_jsonl(self, path: Path) -> None:
        lines = [self.model_dump_json(exclude={"answers"})]
        lines += [a.model_dump_json() for a in self.answers]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load_jsonl(cls, path: Path) -> "GoldenAnswerSet":
        header, *rest = path.read_text(encoding="utf-8").splitlines()
        ds = cls.model_validate_json(header)
        ds.answers = [GoldenAnswer.model_validate_json(line) for line in rest if line]
        return ds


class JudgeValidationTask(BaseModel):
    """One blinded (question, candidate chunk) pair shown to a human annotator.

    Deliberately carries *no* identifiers that could be joined back to the
    golden set: no `case_id`, no `chunk_id`, no judge grade. An annotator who can
    look up what the judge said is not an independent second rater, and the
    agreement statistic would be measuring compliance instead. The join key
    lives only in the companion `JudgeValidationKey` file.
    """

    task_id: str
    question: str
    chunk_text: str


class JudgeValidationKey(BaseModel):
    """The judge's grade for one task, plus the sampling design it came from.

    `weight` is the inverse sampling probability for the item's stratum
    (stratum population / stratum sample size). Sampling is stratified on the
    *judge's* binary call because relevant items are only 15.8% of the pool, so
    an unstratified sample would estimate TPR from a handful of positives; the
    weights are what convert the balanced sample back to population rates.
    """

    task_id: str
    case_id: str
    chunk_id: str
    judge_grade: int
    stratum: str  # judge_relevant | judge_not_relevant
    weight: float
    split: str  # dev | test
    retrieved_by: list[str] = Field(default_factory=list)  # modes that surfaced this chunk
    is_seed_chunk: bool = False  # the chunk the question was generated from


class HumanLabel(BaseModel):
    """One human grade, produced by the offline labeling page."""

    task_id: str
    human_grade: int


class MultiTurnCase(BaseModel):
    """A 2-turn conversation testing whether retrieval survives a follow-up.

    `stream_chat` in `libs/rag/chat.py` sends only the CURRENT turn's raw text
    to the retriever (`retrieval_query = query`) -- history reaches the
    generator via the prompt but never reaches retrieval. `turn2_question` is
    written to be under-specified without `turn1_question` (a pronoun or
    ellipsis standing in for the entity turn 1 established), so it exercises
    exactly that gap.
    """

    id: str  # the chunk turn2 is grounded in
    turn1_question: str
    turn2_question: str  # coreferential/elliptical w.r.t. turn1
    relevant_chunk_ids: list[str] = Field(min_length=1)
    relevant_document_ids: list[str] = Field(min_length=1)
    source: str
    tool: str | None = None


class MultiTurnDataset(BaseModel):
    name: str
    version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generator_model: str
    cases: list[MultiTurnCase] = []

    def save_jsonl(self, path: Path) -> None:
        lines = [self.model_dump_json(exclude={"cases"})]
        lines += [case.model_dump_json() for case in self.cases]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load_jsonl(cls, path: Path) -> "MultiTurnDataset":
        header, *rest = path.read_text(encoding="utf-8").splitlines()
        dataset = cls.model_validate_json(header)
        dataset.cases = [MultiTurnCase.model_validate_json(line) for line in rest if line]
        return dataset
