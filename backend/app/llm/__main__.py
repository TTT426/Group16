"""Smoke-test a provider:  python -m app.llm "你好，請用一句話自我介紹" [--provider ollama --model qwen3:8b]"""

import argparse
import asyncio

from ..config import get_settings
from .factory import get_provider


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None, help="default: LLM_MODEL (or the provider's default)")
    parser.add_argument("--system", default="You are a concise assistant.")
    args = parser.parse_args()

    provider = get_provider(get_settings(), args.provider, args.model)
    result = await provider.generate(args.system, args.prompt)
    print(result.text)
    print(f"\n-- {result.provider} / {result.model} / {result.latency_ms} ms "
          f"/ in={result.input_tokens} out={result.output_tokens}")


if __name__ == "__main__":
    asyncio.run(_main())
