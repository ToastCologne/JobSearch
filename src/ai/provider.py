"""AI provider abstraction — supports Gemini (free), Anthropic, and Ollama."""
import json

from src.config import get_ai_config


async def generate(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
) -> str:
    """Generate text using the configured AI provider. Returns the full response string."""
    ai = get_ai_config()
    provider = ai["provider"]

    if provider == "gemini":
        return await _generate_gemini(prompt, system, max_tokens, ai)
    elif provider == "anthropic":
        return await _generate_anthropic(prompt, system, max_tokens)
    elif provider == "ollama":
        return await _generate_ollama(prompt, system, max_tokens, ai)
    else:
        raise ValueError(
            f"Unknown ai.provider '{provider}' in config.yaml. "
            "Choose: gemini, anthropic, or ollama."
        )


async def _generate_gemini(prompt: str, system: str, max_tokens: int, ai: dict) -> str:
    import google.generativeai as genai  # type: ignore
    from src.config import get_gemini_key

    genai.configure(api_key=get_gemini_key())

    generation_config = genai.types.GenerationConfig(max_output_tokens=max_tokens)
    model = genai.GenerativeModel(
        model_name=ai["gemini_model"],
        system_instruction=system if system else None,
        generation_config=generation_config,
    )

    response = await model.generate_content_async(prompt)
    return response.text


async def _generate_anthropic(prompt: str, system: str, max_tokens: int) -> str:
    import anthropic
    from src.config import get_anthropic_key

    client = anthropic.AsyncAnthropic(api_key=get_anthropic_key())

    kwargs: dict = dict(
        model="claude-opus-4-6",
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system

    text_chunks: list[str] = []
    async with client.messages.stream(**kwargs) as stream:
        async for chunk in stream.text_stream:
            text_chunks.append(chunk)

    return "".join(text_chunks)


async def _generate_ollama(prompt: str, system: str, max_tokens: int, ai: dict) -> str:
    import httpx

    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{ai['ollama_host']}/api/generate",
            json={
                "model": ai["ollama_model"],
                "prompt": full_prompt,
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
        )
        response.raise_for_status()
        return response.json()["response"]
