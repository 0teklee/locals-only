"""
CLI 진입점 — local-ai 명령어.

FastAPI 서버 없이 터미널에서 즉시 사용 가능 (CLI-First).

사용:
  local-ai chat "질문"
  local-ai code "코드 작성 요청" [--file src/foo.py]
  local-ai index /path/to/project
  local-ai models list
  local-ai models switch qwen2.5-coder:7b
  local-ai observe          # 이벤트 로그 tail
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="local-ai",
    help="White-Box Local AI Agent — Offline, CLI-First",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True, style="bold red")


# ------------------------------------------------------------------
# 공통 초기화
# ------------------------------------------------------------------

async def _build_runner(with_rag: bool = False, collection: str = "codebase") -> "AgentRunner":
    """AgentRunner 초기화 (비동기 — asyncio.run 내에서 await)."""
    from src.models.registry import ModelRegistry
    from src.models.pool import ModelPool
    from src.agent.dispatcher import TaskDispatcher
    from src.agent.runner import AgentRunner
    from src.context.builder import ContextBuilder
    from src.memory.manager import MemoryManager
    from src.rag.pipeline import RAGPipeline
    from src.tools.registry import ToolRegistry
    from src.tools import file_tools, shell_tools, git_tools, rag_tools
    from src.observe.bus import ObservabilityBus
    from src.config import settings

    obs = ObservabilityBus.get_default()
    registry = ModelRegistry()
    pool = ModelPool(registry, obs)
    await pool.initialize()

    memory = MemoryManager()
    memory.load_session()  # 이전 세션 복원

    rag = RAGPipeline(collection_name=collection) if with_rag else None
    ctx = ContextBuilder(memory=memory, rag=rag, system_prompt=settings.SYSTEM_PROMPT)

    tools = ToolRegistry(obs)
    file_tools.register(tools)
    shell_tools.register(tools)
    git_tools.register(tools)
    if rag is not None:
        rag_tools.register(tools, rag)

    dispatcher = TaskDispatcher(pool, obs)
    return AgentRunner(pool, dispatcher, tools, ctx, memory, obs)


# ------------------------------------------------------------------
# chat
# ------------------------------------------------------------------

@app.command()
def chat(
    message: str = typer.Argument(..., help="사용자 메시지"),
    no_stream: bool = typer.Option(False, "--no-stream", help="스트리밍 비활성화"),
    session: str = typer.Option("default", "--session", "-s", help="세션 ID"),
) -> None:
    """일반 대화 모드."""

    async def _run() -> None:
        runner = await _build_runner()
        if no_stream:
            result = await runner.run(message, session=session)
            console.print(result)
        else:
            console.print()  # 빈 줄
            await runner.run(
                message,
                on_token=lambda t: console.print(t, end="", highlight=False),
                session=session,
            )
            console.print()  # 완료 후 줄바꿈

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[dim]중단됨[/dim]")


# ------------------------------------------------------------------
# code
# ------------------------------------------------------------------

@app.command()
def code(
    request: str = typer.Argument(..., help="코드 생성/수정 요청"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="대상 파일 (컨텍스트로 포함)"),
    session: str = typer.Option("default", "--session", "-s"),
) -> None:
    """코드 에이전트 모드."""

    prompt = request
    if file is not None and file.exists():
        content = file.read_text(encoding="utf-8")
        prompt = f"File: {file}\n\n```\n{content}\n```\n\nRequest: {request}"
    elif file is not None:
        err_console.print(f"File not found: {file}")
        raise typer.Exit(1)

    async def _run() -> None:
        runner = await _build_runner(with_rag=False)
        console.print()
        await runner.run(
            prompt,
            on_token=lambda t: console.print(t, end="", highlight=False),
            session=session,
        )
        console.print()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[dim]중단됨[/dim]")


# ------------------------------------------------------------------
# index
# ------------------------------------------------------------------

@app.command()
def index(
    path: Path = typer.Argument(..., help="인덱싱할 디렉토리 경로"),
    collection: str = typer.Option("codebase", "--collection", "-c", help="ChromaDB 컬렉션명 (프로젝트별 격리)"),
) -> None:
    """코드베이스를 벡터 DB에 인덱싱."""
    if not path.exists():
        err_console.print(f"Path not found: {path}")
        raise typer.Exit(1)

    from src.rag.pipeline import RAGPipeline

    console.print(f"[bold]인덱싱 시작:[/bold] {path}  [dim](collection: {collection})[/dim]")
    with console.status("[green]인덱싱 중...[/green]"):
        rag = RAGPipeline(collection_name=collection)
        count = rag.index_codebase(str(path))
    console.print(f"[green]완료:[/green] {count}개 청크 인덱싱됨")


# ------------------------------------------------------------------
# models (서브 앱)
# ------------------------------------------------------------------

models_app = typer.Typer(help="모델 관리")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list() -> None:
    """설치된 Ollama 모델 목록 조회."""
    from src.models.ollama_adapter import OllamaAdapter

    async def _run() -> None:
        adapter = OllamaAdapter()
        try:
            models = await adapter.list_models()
        except Exception as e:
            err_console.print(f"Ollama 연결 실패: {e}")
            raise typer.Exit(1)

        if not models:
            console.print("[dim]설치된 모델 없음[/dim]")
            return
        console.print(f"\n{'모델명':<45} {'크기':>7}  {'컨텍스트':>10}  {'양자화'}")
        console.print("─" * 80)
        for m in models:
            ctx = f"{m.context_length:,}" if m.context_length else "?"
            console.print(
                f"{m.name:<45} {m.size_gb:>6.1f}G  {ctx:>10}  {m.quantization}"
            )

    asyncio.run(_run())


@models_app.command("switch")
def models_switch(
    name: str = typer.Argument(..., help="전환할 모델명 (ollama에 설치된 모델)"),
) -> None:
    """기본 모델 전환 (.env.local 업데이트)."""
    env_path = Path(".env.local")
    if env_path.exists():
        lines = [l for l in env_path.read_text().splitlines() if not l.startswith("DEFAULT_MODEL=")]
    else:
        lines = []
    lines.append(f"DEFAULT_MODEL={name}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]기본 모델 변경:[/green] {name}")
    console.print("[dim].env.local 업데이트됨 (다음 실행부터 적용)[/dim]")


# ------------------------------------------------------------------
# observe
# ------------------------------------------------------------------

@app.command()
def observe(
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f/-F", help="실시간 follow"),
    n: int = typer.Option(20, "--lines", "-n", help="마지막 N줄"),
) -> None:
    """이벤트 로그 조회 (data/logs/events.jsonl)."""
    import json
    import time

    log_path = Path("data/logs/events.jsonl")
    if not log_path.exists():
        console.print("[dim]이벤트 로그 없음 (아직 실행된 요청이 없습니다)[/dim]")
        return

    # 마지막 n줄 출력
    lines = log_path.read_text(encoding="utf-8").splitlines()[-n:]
    for line in lines:
        try:
            ev = json.loads(line)
            console.print(f"[dim]{ev['ts']:.3f}[/dim] [bold]{ev['type']:<25}[/bold] {ev['data']}")
        except Exception:
            console.print(line)

    if follow:
        console.print("\n[dim]실시간 모니터링 중... (Ctrl+C로 종료)[/dim]")
        try:
            with open(log_path, encoding="utf-8") as f:
                f.seek(0, 2)  # 파일 끝으로
                while True:
                    line = f.readline()
                    if line:
                        try:
                            ev = json.loads(line)
                            console.print(
                                f"[dim]{ev['ts']:.3f}[/dim] "
                                f"[bold]{ev['type']:<25}[/bold] {ev['data']}"
                            )
                        except Exception:
                            console.print(line.rstrip())
                    else:
                        time.sleep(0.2)
        except KeyboardInterrupt:
            pass


# ------------------------------------------------------------------
# 진입점
# ------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
