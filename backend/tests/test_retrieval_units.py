"""Pure-Python pieces of retrieval / ingest (no database)."""

import math

from app.connectors.base import NormalizedDocument
from app.embeddings.hashing import HashingEmbedder
from app.ingest.chunker import chunk_document, split_text
from app.retrieval.bm25 import BM25
from app.retrieval.linker import find_references, github_repo_of
from app.retrieval.tokenize import tokenize


def test_tokenize_mixed_chinese_english():
    tokens = tokenize("PAYMENT_DUPLICATE 付款失敗")
    assert {"payment_duplicate", "payment", "duplicate"} <= set(tokens)
    assert {"付", "款", "失", "敗", "付款", "款失", "失敗"} <= set(tokens)


def test_bm25_ranks_relevant_document_first():
    corpus = ["部署流程 staging", "付款失敗 PAYMENT_DUPLICATE 原因是重試", "新人 onboarding 清單"]
    bm25 = BM25([tokenize(t) for t in corpus])
    scores = bm25.scores(tokenize("付款為什麼失敗"))
    assert scores.index(max(scores)) == 1
    assert scores[0] == 0 and scores[2] == 0


def test_bm25_empty_corpus():
    assert BM25([]).scores(["x"]) == []


def test_split_text_respects_max_and_keeps_content():
    text = "\n\n".join(f"第{i}段。" + "內容" * 100 for i in range(5))
    pieces = split_text(text, 300)
    assert all(len(p) <= 300 for p in pieces)
    assert "".join(pieces).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(" ", "")


def test_chunk_document_adds_header_and_drops_repeated_title():
    doc = NormalizedDocument(source="notion", external_id="p", url="u", title="金流規格", text="金流規格\n\n內容")
    assert chunk_document(doc) == ["[Notion] 金流規格\n內容"]


def test_chunk_document_long_text_splits():
    doc = NormalizedDocument(source="discord", external_id="t", url="u", title="t",
                             text="\n".join(f"user{i}: message {i} " + "x" * 80 for i in range(50)))
    chunks = chunk_document(doc, max_chars=500)
    assert len(chunks) > 1
    assert all(c.startswith("[Discord] t\n") for c in chunks)
    assert all(len(c) <= 500 + len("[Discord] t\n") for c in chunks)


def test_hashing_embedder_normalised_and_lexically_similar():
    emb = HashingEmbedder(256)
    a, b, c = emb.embed(["付款失敗 重試", "付款 失敗 的原因 重試", "部署 staging 流程"])
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    dot = lambda u, v: sum(x * y for x, y in zip(u, v, strict=True))  # noqa: E731
    assert dot(a, b) > dot(a, c)
    assert emb.embed_query("付款失敗 重試") == a
    assert emb.embed([""])[0][0] == 1.0  # never a zero vector


def test_find_references_across_tools():
    text = (
        "PR https://github.com/Acme/Shop/pull/12 和規格 "
        "https://www.notion.so/acme/Spec-0123456789abcdef0123456789abcdef 以及 "
        "https://discord.com/channels/1/222/333 還有 #7"
    )
    refs = find_references(text, source="discord")
    assert refs[0].source == "github" and refs[0].external_ids == ("issue:12", "pr:12") and refs[0].repo == "acme/shop"
    assert refs[1].external_ids == ("01234567-89ab-cdef-0123-456789abcdef",)
    assert refs[2].external_ids == ("thread:222", "channel:222:333")
    assert len(refs) == 3  # "#7" is ignored outside GitHub

    github_refs = find_references("Fixes #7, see https://github.com/acme/shop/issues/3#issuecomment-1", source="github")
    ids = [r.external_ids for r in github_refs]
    assert ("issue:3", "pr:3") in ids and ("issue:7", "pr:7") in ids and len(ids) == 2


def test_github_repo_of():
    assert github_repo_of("https://github.com/Acme/Shop/issues/1") == "acme/shop"
    assert github_repo_of("https://discord.com/x") is None
