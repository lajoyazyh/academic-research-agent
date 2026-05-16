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
