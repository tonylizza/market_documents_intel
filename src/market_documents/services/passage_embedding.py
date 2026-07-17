"""Passage embedding: local model wrapper, batching, and run orchestration.

Mirrors `services/extraction.py`/`services/passage_segmentation.py`: this
module owns the configuration fingerprint that drives idempotent skipping,
and the query-time rule for selecting a segmentation run's current
successful embedding. The actual model call is behind the `EmbeddingModel`
protocol so orchestration and batching are unit-testable without downloading
or running the real Hugging Face model.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.config import get_settings
from market_documents.models.embedding import EmbeddingRun, PassageEmbedding
from market_documents.models.enums import EmbeddingRunStatus, PassageSegmentationRunStatus
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.services.embedding_config import (
    EMBEDDING_CONFIG,
    EMBEDDING_DIMENSION,
    MAXIMUM_MODEL_TOKENS,
    MODEL_NAME,
    MODEL_REVISION,
    NORMALIZATION_METHOD,
    POOLING_STRATEGY,
    TOKENIZER_NAME,
    TOKENIZER_REVISION,
    compute_configuration_hash,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Model abstraction (real implementation lazily wraps sentence-transformers;
# tests inject a fake satisfying the same protocol)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EncodedPassage:
    vector: list[float]
    input_token_count: int
    truncated: bool


class EmbeddingModel(Protocol):
    def count_tokens(self, text: str) -> int: ...

    def encode_batch(self, texts: list[str]) -> list[EncodedPassage]: ...


class SentenceTransformerEmbeddingModel:
    """Wraps a pinned sentence-transformers model.

    Loaded once per process via `get_embedding_model` (module-level LRU
    cache) -- `embed-all` over many segmentation runs must not reload the
    model per run.
    """

    def __init__(self, cache_dir: Path) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, cache_folder=str(cache_dir))

    def count_tokens(self, text: str) -> int:
        return len(self._model.tokenizer.encode(text, add_special_tokens=True))

    def encode_batch(self, texts: list[str]) -> list[EncodedPassage]:
        vectors = self._model.encode(
            texts, batch_size=len(texts), normalize_embeddings=True, convert_to_numpy=True
        )
        return [
            EncodedPassage(vector=vec.tolist(), input_token_count=self.count_tokens(text), truncated=False)
            for text, vec in zip(texts, vectors)
        ]


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformerEmbeddingModel:
    """The process-wide singleton real embedding model, loaded from the
    persistent Hugging Face cache (downloading on first use if needed)."""
    settings = get_settings()
    return SentenceTransformerEmbeddingModel(settings.hf_cache_dir)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_embedding_run(session: Session, segmentation_run_id: uuid.UUID) -> EmbeddingRun | None:
    """The current successful embedding run for a segmentation run.

    Defined as the most recently completed run with status COMPLETED or
    COMPLETED_WITH_WARNINGS, exactly like `get_current_extraction_run`.
    """
    return session.scalars(
        select(EmbeddingRun)
        .where(
            EmbeddingRun.segmentation_run_id == segmentation_run_id,
            EmbeddingRun.status.in_((EmbeddingRunStatus.COMPLETED, EmbeddingRunStatus.COMPLETED_WITH_WARNINGS)),
        )
        .order_by(EmbeddingRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_embedding_runs_by_segmentation_run(
    session: Session, segmentation_run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, EmbeddingRun]:
    if not segmentation_run_ids:
        return {}
    candidate_runs = session.scalars(
        select(EmbeddingRun)
        .where(
            EmbeddingRun.segmentation_run_id.in_(segmentation_run_ids),
            EmbeddingRun.status.in_((EmbeddingRunStatus.COMPLETED, EmbeddingRunStatus.COMPLETED_WITH_WARNINGS)),
        )
        .order_by(EmbeddingRun.segmentation_run_id, EmbeddingRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, EmbeddingRun] = {}
    for run in candidate_runs:
        current.setdefault(run.segmentation_run_id, run)
    return current


@dataclass
class EmbeddingOutcome:
    segmentation_run_id: uuid.UUID
    run: EmbeddingRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def embed_segmentation_run(
    session: Session,
    segmentation_run: PassageSegmentationRun,
    *,
    model: EmbeddingModel | None = None,
    force: bool = False,
    batch_size: int | None = None,
) -> EmbeddingOutcome:
    """Embed every eligible Passage of one completed segmentation run.

    Eligibility requires the segmentation run to be COMPLETED or
    COMPLETED_WITH_WARNINGS and to have at least one passage not excluded
    from alignment. Skips (returning the existing run) if the current
    successful embedding already used an identical configuration
    fingerprint, and `force` was not set.
    """
    if segmentation_run.status not in (
        PassageSegmentationRunStatus.COMPLETED,
        PassageSegmentationRunStatus.COMPLETED_WITH_WARNINGS,
    ):
        return EmbeddingOutcome(
            segmentation_run_id=segmentation_run.id, run=None, ineligible=True,
            ineligible_reason=f"segmentation run status is {segmentation_run.status.value}, not successful",
        )

    eligible_passages = session.scalars(
        select(Passage).where(
            Passage.segmentation_run_id == segmentation_run.id,
            Passage.excluded_from_alignment.is_(False),
        )
    ).all()
    if not eligible_passages:
        return EmbeddingOutcome(
            segmentation_run_id=segmentation_run.id, run=None, ineligible=True,
            ineligible_reason="no eligible (non-excluded) passages to embed",
        )

    configuration_hash = compute_configuration_hash()
    current_run = get_current_embedding_run(session, segmentation_run.id)
    if current_run is not None and not force and current_run.configuration_hash == configuration_hash:
        return EmbeddingOutcome(
            segmentation_run_id=segmentation_run.id, run=current_run, skipped=True,
            skip_reason="identical successful embedding run already exists",
        )

    run = EmbeddingRun(
        segmentation_run_id=segmentation_run.id,
        model_name=MODEL_NAME,
        model_revision=MODEL_REVISION,
        tokenizer_name=TOKENIZER_NAME,
        tokenizer_revision=TOKENIZER_REVISION,
        embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy=POOLING_STRATEGY,
        normalization_method=NORMALIZATION_METHOD,
        maximum_model_tokens=MAXIMUM_MODEL_TOKENS,
        configuration_hash=configuration_hash,
        status=EmbeddingRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    effective_model = model if model is not None else get_embedding_model()
    effective_batch_size = batch_size or EMBEDDING_CONFIG.batch_size

    try:
        with session.begin_nested():
            _run_embedding(session, run, eligible_passages, effective_model, effective_batch_size)
    except Exception as exc:  # never leave a run silently half-written
        run.status = EmbeddingRunStatus.FAILED
        run.error_message = f"embedding failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("passage embedding failed for segmentation run %s", segmentation_run.id)

    session.flush()
    return EmbeddingOutcome(segmentation_run_id=segmentation_run.id, run=run)


def _run_embedding(
    session: Session,
    run: EmbeddingRun,
    passages: list[Passage],
    model: EmbeddingModel,
    batch_size: int,
) -> None:
    embedded_count = 0
    skipped_count = 0
    warnings: list[str] = []

    embeddable: list[Passage] = []
    for passage in passages:
        token_count = model.count_tokens(passage.raw_text)
        if token_count > MAXIMUM_MODEL_TOKENS:
            skipped_count += 1
            warnings.append(
                f"passage {passage.id}: token count {token_count} exceeds model limit "
                f"({MAXIMUM_MODEL_TOKENS}), skipped rather than silently truncated"
            )
            continue
        embeddable.append(passage)

    for batch_start in range(0, len(embeddable), batch_size):
        batch = embeddable[batch_start : batch_start + batch_size]
        texts = [p.raw_text for p in batch]
        try:
            encoded = model.encode_batch(texts)
        except Exception as exc:
            # Isolate the failure to specific passages by falling back to
            # one-by-one encoding for this batch, rather than losing the
            # whole batch's results to one bad input.
            logger.warning("batch embedding failed (%s), retrying passages individually", exc)
            encoded = []
            for text in texts:
                try:
                    encoded.extend(model.encode_batch([text]))
                except Exception as inner_exc:
                    encoded.append(None)
                    warnings.append(f"embedding failed for a passage: {inner_exc}")

        for passage, result in zip(batch, encoded):
            if result is None:
                skipped_count += 1
                continue
            if len(result.vector) != EMBEDDING_DIMENSION:
                skipped_count += 1
                warnings.append(
                    f"passage {passage.id}: embedding dimension {len(result.vector)} "
                    f"!= expected {EMBEDDING_DIMENSION}, skipped"
                )
                continue
            session.add(
                PassageEmbedding(
                    embedding_run_id=run.id,
                    passage_id=passage.id,
                    embedding=result.vector,
                    input_token_count=result.input_token_count,
                    truncated=result.truncated,
                )
            )
            embedded_count += 1

    run.embedded_passage_count = embedded_count
    run.skipped_passage_count = skipped_count
    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(warnings) if warnings else None
    # A partial run (any skip/failure) is never fully successful.
    run.status = EmbeddingRunStatus.COMPLETED if skipped_count == 0 else EmbeddingRunStatus.COMPLETED_WITH_WARNINGS


@dataclass
class BatchEmbeddingOutcome:
    completed: list[uuid.UUID] = field(default_factory=list)
    completed_with_warnings: list[uuid.UUID] = field(default_factory=list)
    skipped: list[uuid.UUID] = field(default_factory=list)
    ineligible: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    failed: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def embed_eligible_segmentation_runs(
    session: Session,
    *,
    model: EmbeddingModel | None = None,
    limit: int | None = None,
    force: bool = False,
    batch_size: int | None = None,
) -> BatchEmbeddingOutcome:
    """Embed every current successful segmentation run, continuing past
    individual failures."""
    outcome = BatchEmbeddingOutcome()

    current_runs = session.scalars(
        select(PassageSegmentationRun)
        .where(
            PassageSegmentationRun.status.in_(
                (PassageSegmentationRunStatus.COMPLETED, PassageSegmentationRunStatus.COMPLETED_WITH_WARNINGS)
            )
        )
        .order_by(PassageSegmentationRun.created_at)
    ).all()
    # De-duplicate to the current successful run per narrative document.
    latest_by_narrative: dict[uuid.UUID, PassageSegmentationRun] = {}
    for run in current_runs:
        existing = latest_by_narrative.get(run.narrative_document_id)
        if existing is None or (run.completed_at and existing.completed_at and run.completed_at > existing.completed_at):
            latest_by_narrative[run.narrative_document_id] = run
    runs = list(latest_by_narrative.values())
    if limit is not None:
        runs = runs[:limit]

    for run in runs:
        try:
            result = embed_segmentation_run(session, run, model=model, force=force, batch_size=batch_size)
        except Exception:
            logger.exception("unexpected orchestration error embedding segmentation run %s", run.id)
            outcome.failed.append((run.id, "unexpected orchestration error"))
            continue

        if result.ineligible:
            outcome.ineligible.append((run.id, result.ineligible_reason or "ineligible"))
            continue
        if result.skipped:
            outcome.skipped.append(run.id)
            continue

        embedding_run = result.run
        if embedding_run is None:
            continue

        if embedding_run.status == EmbeddingRunStatus.FAILED:
            outcome.failed.append((run.id, embedding_run.error_message or "unknown error"))
        elif embedding_run.status == EmbeddingRunStatus.COMPLETED:
            outcome.completed.append(run.id)
        elif embedding_run.status == EmbeddingRunStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(run.id)

    return outcome
