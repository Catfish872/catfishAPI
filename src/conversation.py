from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_result
from typing import List, Any
import traceback

from .custom_parser import parse_error_response_for_images

from .gemini_client import GeminiClientManager
from .config import SYSTEM_PROMPT_TAG_START, SYSTEM_PROMPT_TAG_END, RETRY_ATTEMPTS



def is_empty_result(value) -> bool:
    if not value: return True
    # 检查 .images 属性，这对于原始库对象和我们的后备对象都有效
    has_text = hasattr(value, 'text') and value.text
    has_images = hasattr(value, 'images') and value.images
    if has_text or has_images: return False
    return True



class Conversation:
    """
    封装一次独立对话的状态和逻辑。
    """

    def __init__(self, client_manager: GeminiClientManager):
        if not client_manager.meta_gem:
            raise ValueError("ClientManager is not initialized or Meta Gem is missing.")
        self.client_manager = client_manager
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
        is_first_turn = self.metadata is None
        chat_session = self.client_manager.client.start_chat(
            gem=self.client_manager.meta_gem.id,
            model=model,
            metadata=self.metadata
        )
        final_prompt = user_input
        if is_first_turn and dynamic_system_prompt:
            final_prompt = (
                f"{SYSTEM_PROMPT_TAG_START}\n"
                f"{dynamic_system_prompt}\n"
                f"{SYSTEM_PROMPT_TAG_END}\n\n"
                f"{user_input}"
            )
        print(f"\n[Sending to Gemini]: Prompt: '{final_prompt[:100]}...', Files: {files}\n")

        try:
            response = await chat_session.send_message(final_prompt, files=files)
        except Exception as e:
            print(f"[DEBUG] Gemini API call crashed. Attempting fallback parsing.")
            error_message = traceback.format_exc()
            response = parse_error_response_for_images(error_message)
            if response is None:
                print(f"[DEBUG] Fallback parsing FAILED after crash. Rethrowing.")
                raise e
            print(f"[DEBUG] Fallback parsing SUCCESSFUL after crash.")

        self.metadata = chat_session.metadata
        return response
