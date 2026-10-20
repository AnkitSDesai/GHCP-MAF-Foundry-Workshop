"""Lab 2 完成版: Microsoft 最新情報エージェント (MRC MCP + AgentSession + ストリーミング対話モード)

実行モード:
- CLI 引数があれば 1 ターンだけ実行: `python src/agent.py "..."`
- 引数なしで起動すると対話モードに入る (quit / exit / 終了 で終了)
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

load_dotenv()

INSTRUCTIONS = """あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。
必ず MRC MCP のツール (https://www.microsoft.com/releasecommunications/mcp) を使って一次情報を取得し、
回答に出典 URL を添えてください。"""

MRC_URL = "https://www.microsoft.com/releasecommunications/mcp"


async def run_once(agent: Agent, query: str) -> None:
    """CLI 引数モード: 1 ターンだけ実行して標準出力に返す。"""
    response = await agent.run(query)
    print(response.text)


async def run_interactive(agent: Agent) -> None:
    """対話モード: AgentSession で文脈を保持しつつストリーミング応答する。"""
    session = agent.create_session()
    print("MS Updates Agent。質問を入力してください (quit / exit / 終了 で終わり)")

    while True:
        try:
            user_input = input("\nあなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower() in {"quit", "exit", "終了"}:
            break
        if not user_input:
            continue

        print(f"\n[conv:{getattr(session, 'conversation_id', 'pending')}]")
        print("エージェント: ", end="", flush=True)
        stream = agent.run(user_input, stream=True, session=session)
        async for chunk in stream:
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print()


async def main() -> None:
    mrc_mcp = MCPStreamableHTTPTool(name="MRC", url=MRC_URL)

    # canonical pattern: credential は async with、client は代入、agent は async with で閉じる
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        )
        async with client.as_agent(
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        ) as agent:
            if len(sys.argv) > 1:
                await run_once(agent, sys.argv[1])
            else:
                await run_interactive(agent)


if __name__ == "__main__":
    asyncio.run(main())
