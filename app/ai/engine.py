"""Unified LangChain / multi-provider AI Engine for TalentHunt OS."""

import logging
from typing import Any, Generator
from pydantic import BaseModel

from app.config.settings import settings

logger = logging.getLogger("talenthunt.ai.engine")


PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-1.5-flash",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20240620",
    "local": "local-model",
    "lmstudio": "local-model",
    "ollama": "llama3",
    "llama_cpp": "local-model",
}

class AIEngine:
    """Unified interface for managing multi-provider LLM completions & streamings."""

    def __init__(self) -> None:
        if settings.gemini_api_key:
            self.default_provider = "gemini"
            self.default_model = PROVIDER_DEFAULT_MODELS["gemini"]
        elif settings.openai_api_key:
            self.default_provider = "openai"
            self.default_model = PROVIDER_DEFAULT_MODELS["openai"]
        elif settings.anthropic_api_key:
            self.default_provider = "anthropic"
            self.default_model = PROVIDER_DEFAULT_MODELS["anthropic"]
        else:
            self.default_provider = "local"
            self.default_model = "local-model"

    def get_llm(
        self,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Any:
        """Instantiate and return a LangChain chat model based on provider, with automatic local model fallback."""
        requested_provider = (provider or self.default_provider).lower()
        model_name = model or PROVIDER_DEFAULT_MODELS.get(requested_provider, self.default_model)

        if requested_provider == "gemini" and settings.gemini_api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=settings.gemini_api_key,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
            except Exception as exc:
                logger.warning("Gemini provider unavailable (%s). Falling back to local LM Studio model.", exc)

        elif requested_provider == "openai" and settings.openai_api_key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=model_name,
                    api_key=settings.openai_api_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                logger.warning("OpenAI provider unavailable (%s). Falling back to local LM Studio model.", exc)

        elif requested_provider == "anthropic" and settings.anthropic_api_key:
            try:
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(
                    model=model_name,
                    api_key=settings.anthropic_api_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                logger.warning("Anthropic provider unavailable (%s). Falling back to local LM Studio model.", exc)

        elif requested_provider == "ollama":
            base_url = "http://127.0.0.1:11434/v1"
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    base_url=base_url,
                    api_key=settings.openai_api_key or "ollama",
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                logger.warning("Ollama provider failed (%s). Falling back to local LM Studio.", exc)

        elif requested_provider == "llama_cpp":
            base_url = f"http://{settings.llama_server_host}:{settings.llama_server_port}/v1"
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    base_url=base_url,
                    api_key=settings.openai_api_key or "llama-cpp",
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                logger.warning("llama_cpp provider failed (%s). Falling back to local LM Studio.", exc)

        # Primary Local LM Studio Handler & Fallback
        base_url = f"http://{settings.llama_server_host}:{settings.llama_server_port}/v1"
        local_key = settings.openai_api_key or "lmstudio"
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                base_url=base_url,
                api_key=local_key,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except ImportError:
            raise RuntimeError("langchain-openai package is required for local model compatibility. Run: pip install langchain-openai")

    def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate a complete text response for a given prompt."""
        llm = self.get_llm(provider=provider, model=model, temperature=temperature)
        messages = []
        if system_prompt:
            from langchain_core.messages import SystemMessage
            messages.append(SystemMessage(content=system_prompt))
        from langchain_core.messages import HumanMessage
        messages.append(HumanMessage(content=prompt))

        import time
        start_time = time.time()
        
        try:
            response = llm.invoke(messages)
            latency = (time.time() - start_time) * 1000
            
            # Observability telemetry
            import logging
            t_logger = logging.getLogger("talenthunt.ai.telemetry")
            t_logger.setLevel(logging.INFO)
            t_logger.info(f"LLM Invoke | Model: {llm.model_name if hasattr(llm, 'model_name') else model} | Latency: {latency:.2f}ms")
            
            return str(response.content)
        except Exception as e:
            logger.error(f"LLM Invoke failed: {e}")
            raise

    def stream_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Stream chunks of response for real-time UI/voice integration."""
        llm = self.get_llm(provider=provider, model=model, temperature=temperature)
        messages = []
        if system_prompt:
            from langchain_core.messages import SystemMessage
            messages.append(SystemMessage(content=system_prompt))
        from langchain_core.messages import HumanMessage
        messages.append(HumanMessage(content=prompt))

        import time
        start_time = time.time()
        first_token = True
        
        try:
            for chunk in llm.stream(messages):
                if first_token:
                    latency = (time.time() - start_time) * 1000
                    import logging
                    t_logger = logging.getLogger("talenthunt.ai.telemetry")
                    t_logger.setLevel(logging.INFO)
                    t_logger.info(f"LLM Stream Start | Model: {llm.model_name if hasattr(llm, 'model_name') else model} | Time to First Token: {latency:.2f}ms")
                    first_token = False
                    
                if hasattr(chunk, "content") and chunk.content:
                    yield str(chunk.content)
        except Exception as e:
            logger.error(f"LLM Stream failed: {e}")
            raise

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        system_prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> BaseModel | None:
        """Generate a structured response adhering to a Pydantic schema."""
        llm = self.get_llm(provider=provider, model=model)
        messages = []
        if system_prompt:
            from langchain_core.messages import SystemMessage
            messages.append(SystemMessage(content=system_prompt))
        from langchain_core.messages import HumanMessage
        messages.append(HumanMessage(content=prompt))

        try:
            structured_llm = llm.with_structured_output(schema)
            return structured_llm.invoke(messages)
        except Exception as exc:
            import json
            logger.warning(
                "Structured output not supported natively by provider/model (%s): %s. Falling back to JSON parsing.",
                provider,
                exc,
            )
            json_schema_str = json.dumps(schema.model_json_schema(), indent=2)
            sys_instruct = (
                f"You MUST return a valid JSON object matching the schema below. "
                f"Do NOT include markdown formatting or backticks.\n\n"
                f"Schema:\n{json_schema_str}"
            )
            if system_prompt:
                sys_instruct = f"{system_prompt}\n\n{sys_instruct}"

            from langchain_core.messages import SystemMessage
            fallback_messages = [
                SystemMessage(content=sys_instruct),
                HumanMessage(content=prompt),
            ]
            response = llm.invoke(fallback_messages)
            raw_text = str(response.content).strip()
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()
            try:
                return schema.model_validate_json(raw_text)
            except Exception as e:
                logger.error("Failed to parse structured output: %s", e)
                return None


# Global AI Engine Instance
ai_engine = AIEngine()
