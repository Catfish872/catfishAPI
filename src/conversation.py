from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_result
from typing import List, Any

from .gemini_client import GeminiClientManager
from .config import SYSTEM_PROMPT_TAG_START, SYSTEM_PROMPT_TAG_END, RETRY_ATTEMPTS


def is_empty_result(value) -> bool:
    if not value: return True
    has_text = hasattr(value, 'text') and value.text
    has_images = hasattr(value, 'images') and value.images
    if has_text or has_images: return False
    return True


class Conversation:
    """
    封装一次独立对话的状态和逻辑。
    这个版本是无状态的，每次请求都会根据metadata重新创建会话。
    """

    def __init__(self, client_manager: GeminiClientManager):
        if not client_manager.meta_gem:
            raise ValueError("ClientManager is not initialized or Meta Gem is missing.")
        self.client_manager = client_manager
        # (修改) 不再存储 chat_session 和 is_first_turn
        # 只存储对话的元数据
        self.metadata: dict[str, Any] | None = None

    @retry(
        wait=wait_random_exponential(min=1, max=10),
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        retry=retry_if_result(is_empty_result),
        reraise=True
    )
    async def send_message(
            self,
            user_input: str,
            dynamic_system_prompt: str | None = None,
            model: str | None = "gemini-1.5-pro",
            files: List[str] | None = None
    ):
        """
        向LLM发送消息。每次都会创建一个新的chat_session来保证稳定性。
        """
        is_first_turn = self.metadata is None

        # (修改) 每次都创建一个新的、干净的会话实例
        # 如果 self.metadata 存在，则用它来恢复对话历史
        chat_session = self.client_manager.client.start_chat(
            gem=self.client_manager.meta_gem.id,
            model=model,
            metadata=self.metadata
        )

        final_prompt = user_input
        # (修改) 只有在绝对的第一轮才注入系统提示
        if is_first_turn and dynamic_system_prompt:
            final_prompt = (
                f"{SYSTEM_PROMPT_TAG_START}\n"
                f"{dynamic_system_prompt}\n"
                f"{SYSTEM_PROMPT_TAG_END}\n\n"
                f"{user_input}"
            )

        print(f"\n[Sending to Gemini]: Prompt: '{final_prompt[:100]}...', Files: {files}\n")

        response = await chat_session.send_message(final_prompt, files=files)

        # (修改) 请求成功后，保存最新的元数据以供下一次使用
        self.metadata = chat_session.metadata

        return response