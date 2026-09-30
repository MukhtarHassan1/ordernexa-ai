"""Check that configured text/vision models exist on the active Ollama server.

Run inside the API container: python -m app.services.ollama_preflight --mode text
This checks model presence only: it does NOT prove generation or extraction quality.
"""
import argparse
import asyncio

from app.services.ai_gateway import OllamaProvider


async def run(mode: str) -> int:
    provider = OllamaProvider()
    installed = await provider._available_models()
    print(f"Configured Ollama endpoint: {provider.base_url}")
    if installed is None:
        print("FAILED: Could not read this server's /api/tags registry.")
        return 2
    print("Installed on THIS server:", ", ".join(installed) or "(none)")
    missing = False
    for kind in (("text", "vision") if mode == "both" else (mode,)):
        model = provider.selected_model(has_images=kind == "vision")
        ok = model in installed
        print(f"{kind.upper()} model: {model or '(unset)'} -> {'INSTALLED' if ok else 'MISSING'}")
        missing |= not ok
    if missing:
        print("Action: pull the missing model on the configured Ollama host, "
              "or change OLLAMA_TEXT_MODEL / OLLAMA_VISION_MODEL in .env "
              "and recreate API. Docker and Windows Ollama do not share models.")
        return 1
    print("Registry check passed. Perform separate generation/schema tests before uploads.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("text", "vision", "both"), default="both")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.mode)))
