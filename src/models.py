from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional, Union
import time
import base64


# --- 多模态内容模型 (参考 GPT-4 Vision) ---

class ImageUrl(BaseModel):
    url: str
    detail: Optional[Literal["low", "high", "auto"]] = "auto"


class TextContentBlock(BaseModel):
    type: Literal["text"]
    text: str


class ImageContentBlock(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrl


# content 字段现在可以是字符串，也可以是图文混合的列表
Content = Union[str, List[Union[TextContentBlock, ImageContentBlock]]]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: Content


# --- 请求与响应模型 ---

class ChatCompletionRequest(BaseModel):
    model: str = "gemini-1.5-pro"
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None

    class Config:
        extra = "ignore"


# --- 图片生成模型 (参考 DALL-E 3) ---

class GeneratedImage(BaseModel):
    # DALL-E 3 API 使用 b64_json，但我们直接返回URL更方便
    url: str
    revised_prompt: Optional[str] = None


class ChatCompletionMessage(BaseModel):
    role: Literal["assistant"]
    # (修改) 将 content 的类型从 Optional[str] 改为 Content
    # 这样它就可以同时支持纯文本和图文混合列表
    content: Optional[Content] = None
    # (新增) Tool Calls 占位，虽然我们不支持，但为了格式兼容
    tool_calls: Optional[List] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage
    # (新增) 用于存放DALL-E风格的图片生成结果
    # 注意：我们将图片生成的结果放在 choice.message.content 里，
    # 或者如果需要更明确的区分，可以像下面这样单独放。
    # 为了简化，我们这里只修改 message.content 的格式。
    finish_reason: Literal["stop"] = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Usage = Field(default_factory=Usage)
    session_id: str


# --- Model List Models (保持不变) ---
class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "Google"


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelCard]