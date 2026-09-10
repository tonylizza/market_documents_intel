from market_documents.services.retrieval_chunk_config import RetrievalChunkConfig
from market_documents.services.retrieval_chunking import split_into_retrieval_chunks


def _words(n: int, filler: str = "word") -> str:
    return " ".join(f"{filler}{i}" for i in range(n))


def _word_count_tokenizer(ratio: float = 1.0):
    """A fake tokenizer whose token count is `ratio` times the word count,
    rounded up -- lets tests exercise the token/word calibration gap
    directly without downloading the real BGE tokenizer."""

    def count_tokens(text: str) -> int:
        words = len(text.split())
        return int(-(-words * ratio // 1))  # ceil

    return count_tokens


def test_short_text_is_a_single_chunk():
    text = _words(10)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer())
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_oversized_text_is_split_into_multiple_chunks_under_the_ceiling():
    sentence = _words(50) + "."
    text = " ".join([sentence] * 4)  # ~200 words, well over a small ceiling
    config = RetrievalChunkConfig(max_tokens=100)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(), config=config)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= config.max_tokens


def test_no_chunk_exceeds_the_ceiling_even_with_a_dense_token_ratio():
    # Simulates the real corpus's dense financial-text calibration gap:
    # tokens well in excess of word count (docs/embedding-eligibility-token-
    # limit-diagnostic.md Section 5).
    sentence = _words(30) + "."
    text = " ".join([sentence] * 10)
    config = RetrievalChunkConfig(max_tokens=200)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(ratio=1.7), config=config)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= config.max_tokens


def test_chunking_prefers_sentence_boundaries():
    sentence = _words(20) + "."
    text = " ".join([sentence] * 6)
    config = RetrievalChunkConfig(max_tokens=45)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(), config=config)
    for chunk in chunks:
        assert chunk.text.endswith(".")


def test_single_oversized_sentence_falls_back_to_word_boundary_split():
    # One sentence (no punctuation) far larger than the ceiling: sentence-
    # level packing alone cannot subdivide it, so the word-boundary fallback
    # must engage.
    text = _words(90)
    config = RetrievalChunkConfig(max_tokens=20)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(), config=config)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= config.max_tokens
    # No content loss or duplication: every word appears exactly once, in order.
    reconstructed = " ".join(c.text for c in chunks).split()
    assert reconstructed == text.split()


def test_chunking_is_deterministic():
    sentence = _words(25) + "."
    text = " ".join([sentence] * 5)
    config = RetrievalChunkConfig(max_tokens=60)
    first = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(), config=config)
    second = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(), config=config)
    assert [c.text for c in first] == [c.text for c in second]
    assert [c.char_start for c in first] == [c.char_start for c in second]


def test_chunk_indices_are_sequential_and_char_spans_tile_the_source_exactly():
    sentence = _words(25) + "."
    text = " ".join([sentence] * 5)
    config = RetrievalChunkConfig(max_tokens=60)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(), config=config)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    covered = 0
    for chunk in chunks:
        assert chunk.char_start == covered
        covered = chunk.char_end
    assert covered == len(text)


def test_content_hash_reflects_chunk_text():
    import hashlib

    text = _words(10)
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer())
    assert chunks[0].content_hash == hashlib.sha256(chunks[0].text.encode("utf-8")).hexdigest()


def test_realistic_712_word_multi_sentence_passage_matches_milestone5_scale():
    # Mirrors the scale of the real corpus's largest observed oversized
    # passages (up to ~723 words, docs/embedding-eligibility-token-limit-
    # diagnostic.md Section 4.1), at the production 480-token ceiling and a
    # realistic dense token/word ratio (~1.3, Section 5's median-to-p90 band).
    sentence = _words(35) + "."
    text = " ".join([sentence] * 20)  # 720 words
    chunks = split_into_retrieval_chunks(text, count_tokens=_word_count_tokenizer(ratio=1.3))
    assert len(chunks) <= 4  # milestone 5's simulation observed a max of 4
    for chunk in chunks:
        assert chunk.token_count <= RetrievalChunkConfig().max_tokens
