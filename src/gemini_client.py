from gemini_webapi import GeminiClient, Gem
from .config import SECURE_1PSID, SECURE_1PSIDTS, META_GEM_NAME, META_GEM_PROMPT, PROXY_URL


class GeminiClientManager:
    """
    负责管理GeminiClient的生命周期和“元指令Gem”的查找与创建。
    """

    def __init__(self, psid: str, psidts: str):
        if not psid or not psidts:
            raise ValueError(
                "Cookies are missing. Please set SECURE_1PSID and "
                "SECURE_1PSIDTS environment variables."
            )
        self.client = GeminiClient(psid, psidts, proxy=PROXY_URL)
        self.meta_gem: Gem | None = None

    async def initialize(self):
        """
        初始化客户端并确保“元指令Gem”存在。
        """
        print("Initializing Gemini client...")
        await self.client.init()
        print("Client initialized successfully.")

        print(f"Checking for Meta Gem: '{META_GEM_NAME}'...")
        await self.client.fetch_gems()

        existing_gem = self.client.gems.get(name=META_GEM_NAME)

        if existing_gem:
            print("Meta Gem found.")
            self.meta_gem = existing_gem
        else:
            print("Meta Gem not found. Creating a new one...")
            try:
                self.meta_gem = await self.client.create_gem(
                    name=META_GEM_NAME,
                    prompt=META_GEM_PROMPT,
                    description="Meta-instruction gem for web service proxy."
                )
                print("Meta Gem created successfully.")
            except Exception as e:
                print(f"Error creating Meta Gem: {e}")
                raise

    async def close(self):
        """关闭客户端连接。"""
        if self.client:
            print("Closing Gemini client...")
            await self.client.close()
            print("Client closed.")


# 创建一个全局实例，将在FastAPI的生命周期事件中被初始化
gemini_manager = GeminiClientManager(SECURE_1PSID, SECURE_1PSIDTS)