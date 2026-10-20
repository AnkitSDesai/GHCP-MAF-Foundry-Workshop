"""Lab 2 ★Stretch 完成版: 構造化出力でレポート化 (Pydantic + JSON 保存)

`data/report_<YYYYMMDD-HHMMSS>.json` に構造化結果を書き出す。
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

load_dotenv()

INSTRUCTIONS = """あなたは Microsoft 365 と Azure のリリース情報を Pydantic で構造化して返すアシスタントです。
必ず MRC MCP (https://www.microsoft.com/releasecommunications/mcp) を使って一次情報を取得し、
要求されたスキーマで出力してください。"""

MRC_URL = "https://www.microsoft.com/releasecommunications/mcp"


class ReleaseItem(BaseModel):
    product: str = Field(description="製品/サービス名 (例: Azure Functions, Microsoft Teams)")
    title: str = Field(description="更新のタイトル")
    status: str = Field(description="ステータス (GA / Public Preview / Retiring など)")
    released_at: str = Field(description="GA/プレビュー化された日付 (YYYY-MM-DD 推奨)")
    url: str = Field(description="出典 URL")
    summary: str = Field(description="50 文字程度の日本語サマリ")


class ReleaseReport(BaseModel):
    period: str = Field(description="レポート対象期間 (例: 2026年5月)")
    summary: str = Field(description="3〜5 行の総括")
    items: list[ReleaseItem] = Field(description="主要な更新項目")


async def main() -> None:
    mrc_mcp = MCPStreamableHTTPTool(name="MRC", url=MRC_URL)

    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        )
        async with client.as_agent(
            name="MSUpdatesReporter",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        ) as agent:
            response = await agent.run(
                "直近 GA になった主要な Microsoft 365 / Azure 更新を 5 件、構造化して返してください。",
                options={"response_format": ReleaseReport},
            )

            try:
                report = response.value
            except ValidationError as err:
                print("構造化応答の parse に失敗しました:", err, file=sys.stderr)
                print("--- 生レスポンス ---", file=sys.stderr)
                print(response.text, file=sys.stderr)
                sys.exit(1)

            out_dir = Path("data")
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_path = out_dir / f"report_{stamp}.json"
            out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            print(f"Saved: {out_path}")
            print(f"  period={report.period}  items={len(report.items)}")


if __name__ == "__main__":
    asyncio.run(main())
