import os
import httpx
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

class LLMClient:
    def __init__(self):
        # 使用 find_dotenv 递归往上层查找 .env 文件
        load_dotenv(find_dotenv(usecwd=True))
        
        # 对外只依赖 ZHIPU_* 配置；为了兼容底层库的校验，在进程内同步 OPENAI_API_KEY
        self.api_key = os.getenv('ZHIPU_API_KEY') or os.getenv('OPENAI_API_KEY') or 'your-api-key-here'
        if not os.getenv('OPENAI_API_KEY') and self.api_key:
            os.environ['OPENAI_API_KEY'] = self.api_key
        self.base_url = os.getenv('ZHIPU_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/')
        if not os.getenv('OPENAI_BASE_URL'):
            os.environ['OPENAI_BASE_URL'] = self.base_url
        if not os.getenv('OPENAI_API_BASE'):
            os.environ['OPENAI_API_BASE'] = self.base_url
        http_client = httpx.Client(proxy=None)
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, http_client=http_client)
        self.model = os.getenv('ZHIPU_MODEL', 'glm-4-flash')

    def chat(self, system_prompt: str, user_query: str, history: list) -> str:
        messages = [{'role': 'system', 'content': system_prompt}]
        messages.extend(history)
        if user_query:
            messages.append({'role': 'user', 'content': user_query})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1
        )
        return response.choices[0].message.content

    def chat_stream(self, system_prompt: str, user_query: str, history: list):
        """流式对话，逐 token yield 返回内容。"""
        messages = [{'role': 'system', 'content': system_prompt}]
        messages.extend(history)
        if user_query:
            messages.append({'role': 'user', 'content': user_query})
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
        如果 API 不可用，返回零向量作为降级。
        """
        if not texts:
            return []
        try:
            resp = self.client.embeddings.create(
                model="embedding-2",
                input=texts,
            )
            return [d.embedding for d in resp.data]
        except Exception as e:
            print(f"[Embedding] API 调用失败，降级为零向量: {e}")
            return [[0.0] * 1536 for _ in texts]
