# --- conversation.py (已移除重试的最终版) ---

from typing import List, Any

from .gemini_client import GeminiClientManager
from .config import SYSTEM_PROMPT_TAG_START, SYSTEM_PROMPT_TAG_END

def is_empty_result(value) -> bool:
    """辅助函数，检查返回结果是否真的有内容。"""
    if not value: return True
    has_text = hasattr(value, 'text') and value.text
    has_images = hasattr(value, 'images') and value.images
    if has_text or has_images: return False
    return True


class Conversation:
    """
    管理一个对话会话。它完全相信底层的 client 能成功返回结果。
    """
    def __init__(self, client_manager: GeminiClientManager):
        if not client_manager.meta_gem:
            raise ValueError("ClientManager is not initialized or Meta Gem is missing.")
        self.client_manager = client_manager
        # 注意：因为你的 main.py 每次都创建新的 Conversation，
        # 所以这个 self.metadata 在你的无状态架构下实际上不会被复用。
        self.metadata: dict[str, Any] | None = None

    async def send_message(
            self,
            user_input: str,
            # 移除了 dynamic_system_prompt，因为你的 flatten 函数已经处理了
            model: str | None = "gemini-1.5-pro",
            files: List[str] | None = None
    ):
        """
        发送消息。没有重试，没有复杂的错误处理，就是一次直接的调用。
        """
        # 注意：你的 flatten 函数已经包含了 system_prompt，所以这里不再需要
        final_prompt = user_input

        print(f"\nSending to Gemini (Single Attempt): Prompt: '{final_prompt[:100]}...', Files: {files}\n")

        # 由于你的架构是无状态的，我们每次都用空的 metadata 开始一个新的 chat_session
        chat_session = self.client_manager.client.start_chat(
            gem=self.client_manager.meta_gem.id,
            model=model,
            metadata=None # 每次都是新会话
        )

        # 直接调用 send_message，并相信它会成功（因为补丁会处理失败）
        response = await chat_session.send_message(final_prompt, files=files)

        # 检查以防万一
        if is_empty_result(response):
            raise Exception("Gemini returned an empty result. The monkey patch recovery might have failed.")

        return response