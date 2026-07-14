import os

import httpx
from dotenv import find_dotenv, load_dotenv
from openai import OpenAI


class LLMClient:
    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
    DEFAULT_MODEL = "glm-4-flash"
    DEFAULT_EMBEDDING_MODEL = "embedding-2"

    def __init__(self, provider_config: dict | None = None):
        # 使用 find_dotenv 递归往上层查找 .env 文件
        load_dotenv(find_dotenv(usecwd=True))

        provider_config = provider_config or {}
        request_key = str(provider_config.get("api_key") or "").strip()
        request_base_url = str(provider_config.get("base_url") or "").strip()
        request_model = str(provider_config.get("chat_model") or provider_config.get("model") or "").strip()
        request_embedding_model = str(provider_config.get("embedding_model") or "").strip()
        self.provider_id = str(provider_config.get("provider_id") or "zhipu").strip()

        # BYOK: request-scoped keys are used only inside this client instance.
        self.api_key = request_key or os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY") or "your-api-key-here"
        self.base_url = request_base_url or os.getenv("ZHIPU_BASE_URL", self.DEFAULT_BASE_URL)
        self.model = request_model or os.getenv("ZHIPU_MODEL", self.DEFAULT_MODEL)
        self.embedding_model = request_embedding_model or os.getenv("EMBEDDING_MODEL", "") or ("" if self.provider_id == "custom" else self.DEFAULT_EMBEDDING_MODEL)
        self._using_request_key = bool(request_key)
        self._missing_api_key = not self.api_key or self.api_key == "your-api-key-here"

        # 为兼容底层库的环境变量校验，只同步服务器 fallback key，不同步用户请求 key。
        if not self._using_request_key and not self._missing_api_key and not os.getenv("OPENAI_API_KEY") and self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key
        if not os.getenv("OPENAI_BASE_URL"):
            os.environ["OPENAI_BASE_URL"] = self.base_url
        if not os.getenv("OPENAI_API_BASE"):
            os.environ["OPENAI_API_BASE"] = self.base_url

        http_client = httpx.Client(proxy=None)
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, http_client=http_client)

    def _ensure_configured(self):
        is_real_openai_client = self.client.__class__.__module__.startswith("openai")
        if self._missing_api_key and is_real_openai_client:
            raise RuntimeError(
                "需要配置 API Key。请在页面右上角打开 API 配置并填写自己的 API Key，"
                "或由服务端管理员配置 ZHIPU_API_KEY / OPENAI_API_KEY。"
            )

    def chat(self, system_prompt: str, user_query: str, history: list) -> str:
        self._ensure_configured()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if user_query:
            messages.append({"role": "user", "content": user_query})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )
        return response.choices[0].message.content

    def chat_stream(self, system_prompt: str, user_query: str, history: list):
        """流式对话，逐 token yield 返回内容。"""
        self._ensure_configured()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if user_query:
            messages.append({"role": "user", "content": user_query})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def embed(self, texts: list[str]) -> list[list[float]]:
        """调用智谱 text-embedding API，将文本列表转为向量列表。
        使用智谱 embedding-2 模型（1536 维）。
        自动分批（每批最多 64 条），API 不可用时降级为零向量。
        """
        if not texts:
            return []
        self._ensure_configured()
        if not self.embedding_model:
            raise RuntimeError("尚未配置向量模型，请在个人中心补充配置后重试。")

        batch_size = 64
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                resp = self.client.embeddings.create(
                    model=self.embedding_model,
                    input=batch,
                )
                all_embeddings.extend([d.embedding for d in resp.data])
            except Exception as exc:
                raise RuntimeError("向量模型调用失败，请在个人中心检查向量模型配置。") from exc

        return all_embeddings
