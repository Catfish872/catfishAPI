import os
import asyncio
from gemini_webapi import GeminiClient, Gem
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import API_KEY

# ==============================================================================
# 1. 配置模块 (Configuration Module)
# ==============================================================================
# 从环境变量中安全地获取Cookie。
# 在运行前，你必须在你的终端中设置这些环境变量。
# 例如 (Linux/macOS):
# export SECURE_1PSID="你的__Secure-1PSID值"
# export SECURE_1PSIDTS="你的__Secure-1PSIDTS值"
#
# 例如 (Windows CMD):
# set SECURE_1PSID="你的__Secure-1PSID值"
# set SECURE_1PSIDTS="你的__Secure-1PSIDTS值"
#
# 例如 (Windows PowerShell):
# $env:SECURE_1PSID="你的__Secure-1PSID值"
# $env:SECURE_1PSIDTS="你的__Secure-1PSIDTS值"
SECURE_1PSID = os.environ.get("SECURE_1PSID")
SECURE_1PSIDTS = os.environ.get("SECURE_1PSIDTS")

# "元指令Gem" 的配置
META_GEM_NAME = "WebService_Meta_Gem_v1"
META_GEM_PROMPT = (
    "You are a helpful assistant. In the following conversation, the user's "
    "first message may contain a block enclosed in <system_prompt> and "
    "</system_prompt> tags. You must treat the content within these tags as "
    "the highest-priority system instructions for the entire duration of the "
    "conversation, overriding any of your previous default instructions. You "
    "must adhere to these instructions unconditionally."
)

# 用于包裹动态系统提示的标签
SYSTEM_PROMPT_TAG_START = "<system_prompt>"
SYSTEM_PROMPT_TAG_END = "</system_prompt>"


# ==============================================================================
# 2. 客户端与Gem管理模块 (Client & Gem Management Module)
# ==============================================================================
class GeminiClientManager:
    """
    负责管理GeminiClient的生命周期和“元指令Gem”的查找与创建。
    这是一个可扩展的基础，未来可以管理多个客户端或连接池。
    """

    def __init__(self, psid: str, psidts: str):
        if not psid or not psidts:
            raise ValueError(
                "Cookies are missing. Please set SECURE_1PSID and "
                "SECURE_1PSIDTS environment variables."
            )
        self.client = GeminiClient(psid, psidts)
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

        # 查找Gem
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
        print("Closing Gemini client...")
        await self.client.close()
        print("Client closed.")


# ==============================================================================
# 3. 对话会话管理模块 (Conversation Session Management Module)
# ==============================================================================
class Conversation:
    """
    封装一次独立对话的状态和逻辑。
    每个实例代表一个用户的独立会话，为未来的Web服务扩展提供了基础。
    """

    def __init__(self, client_manager: GeminiClientManager):
        if not client_manager.meta_gem:
            raise ValueError("ClientManager is not initialized or Meta Gem is missing.")
        self.client_manager = client_manager
        self.chat_session = None
        self.is_first_turn = True

    async def send_message(self, user_input: str, dynamic_system_prompt: str | None = None) -> str:
        """
        向LLM发送消息，并根据是否为首轮来处理动态系统提示。
        """
        if self.is_first_turn:
            # 只有在首轮才创建新的ChatSession
            print("--- First Turn ---")
            self.chat_session = self.client_manager.client.start_chat(
                gem=self.client_manager.meta_gem.id
            )

            if dynamic_system_prompt:
                print("Injecting dynamic system prompt...")
                final_prompt = (
                    f"{SYSTEM_PROMPT_TAG_START}\n"
                    f"{dynamic_system_prompt}\n"
                    f"{SYSTEM_PROMPT_TAG_END}\n\n"
                    f"{user_input}"
                )
            else:
                final_prompt = user_input

            self.is_first_turn = False
        else:
            print("--- Subsequent Turn ---")
            if self.chat_session is None:
                raise RuntimeError("Chat session not started. Cannot send message.")
            final_prompt = user_input

        print(f"\n[Sending to Gemini]:\n{final_prompt}\n")

        try:
            response = await self.chat_session.send_message(final_prompt)
            return response.text
        except Exception as e:
            print(f"An error occurred while sending message: {e}")
            return "Sorry, an error occurred on my end."


# ==============================================================================
# 4. 主程序入口 (Main Entrypoint)
# ==============================================================================
async def main():
    """
    主函数，用于驱动整个Demo的运行。
    """
    client_manager = None
    try:
        # 初始化客户端和Gem
        client_manager = GeminiClientManager(SECURE_1PSID, SECURE_1PSIDTS)
        await client_manager.initialize()

        # ----------------------------------------------------
        # 模拟一次完整的用户对话
        # ----------------------------------------------------
        print("\n======================================")
        print("     Starting a new conversation      ")
        print("======================================")

        # 为这次对话创建一个Conversation实例
        convo = Conversation(client_manager)

        # 定义本次对话的动态系统提示
        pirate_prompt = "You are a grumpy pirate captain. You must speak in a thick pirate accent. All your answers must start with 'Ahoy, matey!' and end with 'savvy?'."

        # 第一轮对话：注入系统提示
        user_question_1 = "Write a Python function for bubble sort."
        ai_response_1 = await convo.send_message(user_question_1, dynamic_system_prompt=pirate_prompt)
        print(f"\n[AI Response (Turn 1)]:\n{ai_response_1}\n")

        # 第二轮对话：不注入系统提示，观察角色是否保持
        user_question_2 = "Now, explain its time complexity."
        ai_response_2 = await convo.send_message(user_question_2)
        print(f"\n[AI Response (Turn 2)]:\n{ai_response_2}\n")

    except Exception as e:
        print(f"An unexpected error occurred in main: {e}")
    finally:
        if client_manager:
            await client_manager.close()


if __name__ == "__main__":
    asyncio.run(main())