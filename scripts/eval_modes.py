"""Compare the three QA modes (rag / full / agent) on the evaluation scenarios with the real LLM.

For every scenario question and mode it records:
- key-point coverage: share of answer-key points the answer states (judged by the LLM against the key)
- source recall: share of the scenario's answer sources (Discord thread, PR, Notion page) the answer cites
- unsupported sections, invented citations, latency, number of LLM calls, prompt size
Results go to data/eval_modes/<timestamp>.json and a summary to docs/EVAL_MODES.md.

Usage:  python scripts/eval_modes.py [--modes rag full agent] [--repeat 1]
Each run calls Claude (subscription quota): roughly questions x modes answers plus as many judge calls.
"""

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import REPO_ROOT, Settings, get_settings  # noqa: E402
from app.connectors.scenario import ScenarioConnector  # noqa: E402
from app.db.session import create_session_factory, init_db  # noqa: E402
from app.embeddings.factory import get_embedder  # noqa: E402
from app.ingest.pipeline import ingest_documents  # noqa: E402
from app.llm.factory import get_provider  # noqa: E402
from app.llm.json_utils import extract_json_object  # noqa: E402
from app.qa.service import MODES, QAService  # noqa: E402
from app.qa.workspace import WorkspaceExport  # noqa: E402
from app.retrieval.hybrid import ChunkIndex  # noqa: E402

JUDGE_SYSTEM = """你是嚴格的評分員。比對「回答」是否包含「答案要點」中的每一點。
意思相同即可，不要求字面一致；回答裡沒有明確寫出的要點算沒有涵蓋。也檢查回答是否有與要點矛盾或捏造的內容。
只輸出 JSON：{"covered": [true 或 false, ...（順序與要點相同）], "contradiction": true 或 false, "note": "一句說明"}"""


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"covered": {"type": "array", "items": {"type": "boolean"}},
                   "contradiction": {"type": "boolean"}, "note": {"type": "string"}},
    "required": ["covered", "contradiction", "note"],
}


def judge_prompt(question: str, points: list[str], answer_text: str) -> str:
    listed = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    return f"問題：{question}\n\n答案要點：\n{listed}\n\n回答：\n{answer_text or '（沒有回答）'}"


async def run(modes: list[str], repeat: int) -> dict:
    base = get_settings()
    tmp = Path(tempfile.mkdtemp(prefix="g16-eval-"))
    settings = Settings(_env_file=None, database_path=tmp / "eval.db", workspace_dir=tmp / "workspace",
                        llm_provider=base.llm_provider, llm_model=base.llm_model, llm_timeout_s=300,
                        embedding_provider=base.embedding_provider, embedding_model=base.embedding_model)
    paths = sorted((REPO_ROOT / "scripts" / "seed_workspace").glob("scenario_*.yaml"))
    connector = ScenarioConnector(paths)
    factory = create_session_factory(settings.db_file)
    init_db(factory.kw["bind"])
    embedder = get_embedder()
    provider = get_provider(settings)
    index, workspace = ChunkIndex(), WorkspaceExport(settings.workspace_dir)
    rows = []
    with factory() as session:
        ingest_documents(session, connector.fetch(), embedder)
        service = QAService(session, embedder, index, provider, settings, workspace)
        for scenario in connector.scenarios:
            expected = {connector.urls[k] for k in scenario["answer_key"]["sources"]}
            for item in scenario["eval_questions"]:
                points = [p for part in item["parts"] for p in scenario["answer_key"][part]]
                for mode in modes:
                    for attempt in range(repeat):
                        print(f"[{scenario['id']}] {mode} #{attempt + 1}: {item['question'][:40]}", flush=True)
                        started = time.perf_counter()
                        try:
                            result = await service.answer(item["question"], mode)
                            error = None
                        except Exception as exc:  # record failures instead of aborting the whole run
                            result, error = None, f"{type(exc).__name__}: {exc}"
                        wall = time.perf_counter() - started
                        row = {"scenario": scenario["id"], "question": item["question"], "parts": item["parts"],
                               "mode": mode, "attempt": attempt + 1, "wall_s": round(wall, 1), "error": error}
                        if result:
                            text = "\n".join(s["text"] for s in result.sections)
                            verdict = await judge(provider, item["question"], points, text)
                            cited = {s["url"] for s in result.sources}
                            row.update({
                                "answer": text, "cited_urls": sorted(cited), "mode_used": result.mode,
                                "coverage": sum(verdict["covered"]) / len(points),
                                "covered": verdict["covered"], "contradiction": verdict["contradiction"],
                                "judge_note": verdict["note"],
                                "source_recall": len(expected & cited) / len(expected),
                                "unsupported_sections": sum(1 for s in result.sections if not s["supported"]),
                                "invented_citations": len(result.dropped_citations),
                                "llm_calls": result.llm_calls, "latency_s": round(result.latency_ms / 1000, 1),
                                "sources_given": result.sources_given, "unanswerable": result.unanswerable,
                            })
                        rows.append(row)
    return {"started": datetime.now().isoformat(timespec="seconds"), "llm": provider.name,
            "model": settings.llm_model or "CLI default", "embedding": embedder.model_id, "rows": rows}


async def judge(provider, question: str, points: list[str], answer_text: str) -> dict:
    for _ in range(2):
        result = await provider.generate(JUDGE_SYSTEM, judge_prompt(question, points, answer_text),
                                         json_schema=JUDGE_SCHEMA)
        try:
            data = extract_json_object(result.text)
            covered = [bool(x) for x in data.get("covered", [])][: len(points)]
            covered += [False] * (len(points) - len(covered))
            return {"covered": covered, "contradiction": bool(data.get("contradiction")),
                    "note": str(data.get("note", ""))}
        except ValueError:
            continue
    return {"covered": [False] * len(points), "contradiction": False, "note": "judge failed"}


def summarise(report: dict) -> list[dict]:
    out = []
    for mode in MODES:
        rows = [r for r in report["rows"] if r["mode"] == mode]
        ok = [r for r in rows if not r["error"]]
        if not rows:
            continue

        def mean(key, ok=ok):
            return round(statistics.mean(r[key] for r in ok), 3) if ok else None

        out.append({
            "mode": mode, "runs": len(rows), "errors": len(rows) - len(ok),
            "coverage": mean("coverage"), "source_recall": mean("source_recall"),
            "contradictions": sum(r["contradiction"] for r in ok),
            "unsupported_sections": sum(r["unsupported_sections"] for r in ok),
            "invented_citations": sum(r["invented_citations"] for r in ok),
            "latency_s": mean("latency_s"), "latency_max_s": max((r["latency_s"] for r in ok), default=None),
            "llm_calls": mean("llm_calls"), "sources_given": mean("sources_given"),
        })
    return out


def write_markdown(report: dict, summary: list[dict], path: Path) -> None:
    pct = lambda v: "—" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    lines = [
        "# 問答模式比較：rag / full / agent",
        "",
        f"- 執行時間：{report['started']}",
        f"- LLM：{report['llm']}（{report['model']}）；embedding：{report['embedding']}",
        f"- 題目：兩個評估情境各 3 題（完整任務題、只問原因、只問理由），每題每種模式各跑 {report['repeat']} 次",
        "- 要點涵蓋率：回答寫出了答案 key 中多少要點（由 Claude 依答案 key 評分）",
        "- 來源命中率：情境的三個答案來源（Discord 討論串、GitHub PR、Notion 規格）有幾個被引用",
        "",
        "| 模式 | 要點涵蓋率 | 來源命中率 | 矛盾 / 捏造 | 無來源段落 | 不存在的引用 "
        "| 平均回應時間 | 最慢 | LLM 呼叫數 | 給模型的來源數 | 失敗 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['mode']} | {pct(s['coverage'])} | {pct(s['source_recall'])} | {s['contradictions']} | "
            f"{s['unsupported_sections']} | {s['invented_citations']} | {s['latency_s']} 秒 | "
            f"{s['latency_max_s']} 秒 | "
            f"{s['llm_calls']} | {s['sources_given']} | {s['errors']} |")
    lines += ["", "## 每題結果", "", "| 情境 | 題目 | 模式 | 涵蓋 | 來源 | 秒 | 評分說明 |",
              "|---|---|---|---|---|---|---|"]
    for r in report["rows"]:
        if r["error"]:
            lines.append(f"| {r['scenario']} | {r['question'][:24]} | {r['mode']} | 失敗 | | {r['wall_s']} | "
                         f"{r['error'][:60]} |")
        else:
            lines.append(f"| {r['scenario']} | {r['question'][:24]} | {r['mode']} | {pct(r['coverage'])} | "
                         f"{pct(r['source_recall'])} | {r['latency_s']} | {r['judge_note'][:60]} |")
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modes", nargs="+", default=list(MODES), choices=MODES)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--markdown", default=str(REPO_ROOT / "docs" / "EVAL_MODES.md"))
    args = parser.parse_args()

    report = asyncio.run(run(args.modes, args.repeat))
    report["repeat"] = args.repeat
    summary = summarise(report)
    report["summary"] = summary
    out_dir = REPO_ROOT / "data" / "eval_modes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    write_markdown(report, summary, Path(args.markdown))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nSaved {out} and {args.markdown}")


if __name__ == "__main__":
    main()
