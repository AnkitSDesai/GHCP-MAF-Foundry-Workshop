"""Agent Framework の evaluate_agent で Local チェックと Foundry 評価を組み合わせて実行する。

実行: python src/evaluate_agent.py
結果: 標準出力に要約 + results/eval-<timestamp>.json に保存 (共有用)
"""

import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from agent_framework import LocalEvaluator, MCPStreamableHTTPTool, evaluate_agent, evaluator
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import INSTRUCTIONS, MRC_URL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@evaluator
def has_source_url(response: str) -> bool:
    """回答に出典 URL が含まれるか (指示「出典 URL を添える」の遵守確認)。"""
    return re.search(r"https?://", response) is not None


@evaluator
def is_concise(response: str) -> bool:
    """回答が長すぎないか (文字数ベース。日本語は空白区切りが使えないため)。"""
    return len(response) < 1500


def summarize(results) -> dict:
    """EvalResults のリストを共有しやすい dict に変換する。"""
    summary = []
    for r in results:
        summary.append(
            {
                "provider": r.provider,
                "status": r.status,
                "passed": r.passed,
                "failed": r.failed,
                "total": r.total,
                "per_evaluator": r.per_evaluator,
                "report_url": r.report_url,
                "error": r.error,
                "items": [
                    {
                        "item_id": i.item_id,
                        "status": i.status,
                        "scores": [
                            {"name": s.name, "score": s.score, "passed": s.passed} for s in i.scores
                        ],
                    }
                    for i in r.items
                ],
            }
        )
    return {"generated_at": datetime.now(UTC).isoformat(), "results": summary}


async def main() -> None:
    load_dotenv(ROOT / ".env")
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]

    data = json.loads((ROOT / "data" / "eval_inputs.json").read_text(encoding="utf-8"))
    queries = [item["query"] for item in data]

    local = LocalEvaluator(has_source_url, is_concise)
    mrc_mcp = MCPStreamableHTTPTool(name="MRC", url=MRC_URL)

    async with AzureCliCredential() as credential, AIProjectClient(endpoint=endpoint, credential=credential) as project_client:
        foundry = FoundryEvals(
            project_client=project_client,
            model=model,
            evaluators=[
                FoundryEvals.INTENT_RESOLUTION,
                FoundryEvals.TASK_ADHERENCE,
                FoundryEvals.RELEVANCE,
                FoundryEvals.COHERENCE,
            ],
        )
        client = FoundryChatClient(project_endpoint=endpoint, model=model, credential=credential)
        async with client.as_agent(
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        ) as agent:
            results = await evaluate_agent(
                agent=agent,
                queries=queries,
                evaluators=[local, foundry],
                eval_name="ms-updates-agent-eval",
            )

    for r in results:
        print(f"\n[{r.provider}] status={r.status} passed={r.passed}/{r.total}")
        for name, counts in r.per_evaluator.items():
            print(f"  {name}: {counts}")
        if r.report_url:
            print(f"  Report: {r.report_url}")
        if r.error:
            print(f"  Error: {r.error}")

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"eval-{timestamp}.json"
    out_path.write_text(json.dumps(summarize(results), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
