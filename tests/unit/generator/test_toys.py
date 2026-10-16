import json
from collections import Counter
from pathlib import Path

from data.generator import answer, classify, extract

from evalgate.contracts import Case

ROOT = Path(__file__).resolve().parents[3]
TOYS = ROOT / "evals/datasets/toys"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (TOYS / name).read_text().splitlines()]


def test_150_rows_90_dev_60_test() -> None:
    for name in ["classify.v1.jsonl", "extract.v1.jsonl", "answer.v1.jsonl"]:
        rows = load(name)
        assert len(rows) == 150, name
        assert Counter(r["split"] for r in rows) == {"dev": 90, "test": 60}, name
        assert len({r["id"] for r in rows}) == 150
        for r in rows:
            Case.model_validate(r)
    corpus = load("faq_corpus.v1.jsonl")
    assert len(corpus) == 40
    assert len({d["id"] for d in corpus}) == 40


def test_generation_is_deterministic() -> None:
    assert classify.generate() == classify.generate()
    assert extract.generate() == extract.generate()
    assert answer.generate() == answer.generate()


def test_classify_labels_balanced() -> None:
    labels = Counter(r["expected"]["label"] for r in load("classify.v1.jsonl"))
    assert set(labels) == set(classify.LABELS)
    assert max(labels.values()) - min(labels.values()) <= 1


def test_answer_questions_unique_and_reference_in_corpus() -> None:
    rows = load("answer.v1.jsonl")
    assert len({r["input"]["question"] for r in rows}) == 150
    corpus = {d["id"]: d["input"]["text"] for d in load("faq_corpus.v1.jsonl")}
    for r in rows:
        exp = r["expected"]
        assert exp["answer"] in corpus[exp["doc_id"]]
        for fact in exp["key_facts"]:
            assert fact in exp["answer"]


def test_extract_expected_fields_present_in_document() -> None:
    for r in load("extract.v1.jsonl"):
        doc, exp = r["input"]["document"], r["expected"]
        assert exp["invoice_number"] in doc
        assert exp["vendor"] == doc.splitlines()[0]
        assert f"{exp['total']:,.2f}" in doc
