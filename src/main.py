import uuid
import time
import json
import base64
import aiohttp
import aiofiles
import os
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse

from .config import API_KEY, PROXY_URL, SYSTEM_PROMPT_TAG_START, SYSTEM_PROMPT_TAG_END
from .gemini_client import gemini_manager
from .conversation import Conversation
from .models import (
    ChatCompletionRequest, ChatCompletionResponse, ChatCompletionMessage,
    ChatCompletionChoice, ModelList, ModelCard, TextContentBlock,
    ImageContentBlock, Content, ImageUrl
)


# (修改) 移除所有会话缓存逻辑
# ACTIVE_SESSIONS: TTLCache[str, Conversation] = TTLCache(maxsize=1024, ttl=3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("temp_uploads", exist_ok=True)
    await gemini_manager.initialize()
    yield
    await gemini_manager.close()


app = FastAPI(lifespan=lifespan, title="Catfish API", version="1.2.2 Final")
auth_scheme = HTTPBearer()


# ... (verify_key, fake_stream_response_generator 保持不变) ...
async def verify_key(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    if not API_KEY: return
    if credentials.scheme != "Bearer" or credentials.credentials != API_KEY: raise HTTPException(status_code=401,
                                                                                                 detail="Incorrect bearer token",
                                                                                                 headers={
                                                                                                     "WWW-Authenticate": "Bearer"})


async def fake_stream_response_generator(response_content: str, model: str, session_id: str):
    response_id = f"chatcmpl-{uuid.uuid4()}"
    created_timestamp = int(time.time())
    choice_data_role = {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
    chunk_role = {"id": response_id, "object": "chat.completion.chunk", "created": created_timestamp, "model": model,
                  "choices": [choice_data_role]}
    yield f"data: {json.dumps(chunk_role)}\n\n"
    choice_data_content = {"index": 0, "delta": {"content": response_content}, "finish_reason": "stop"}
    chunk_content = {"id": response_id, "object": "chat.completion.chunk", "created": created_timestamp, "model": model,
                     "choices": [choice_data_content]}
    yield f"data: {json.dumps(chunk_content)}\n\n"
    yield "data: [DONE]\n\n"


async def process_multimodal_content(messages: list) -> tuple[str, list[str]]:
    # 此函数现在只用于提取图片，文本部分由新的 flatten 函数处理
    user_prompt_parts = []
    temp_file_paths = []
    last_user_message = next((msg for msg in reversed(messages) if msg.role == 'user'), None)
    if not last_user_message or isinstance(last_user_message.content, str):
        return "", []

    async with aiohttp.ClientSession() as session:
        for content_block in last_user_message.content:
            if isinstance(content_block, TextContentBlock):
                user_prompt_parts.append(content_block.text)  # 仍然提取文本以备用
            elif isinstance(content_block, ImageContentBlock):
                image_url = content_block.image_url.url
                file_path = os.path.join("temp_uploads", f"{uuid.uuid4()}")
                try:
                    if image_url.startswith("data:image"):
                        header, encoded = image_url.split(",", 1)
                        file_extension = header.split("/")[1].split(";")[0]
                        file_path_with_ext = f"{file_path}.{file_extension}"
                        async with aiofiles.open(file_path_with_ext, "wb") as f:
                            await f.write(base64.b64decode(encoded))
                        temp_file_paths.append(file_path_with_ext)
                    else:
                        async with session.get(image_url) as resp:
                            resp.raise_for_status()
                            content_type = resp.headers.get('Content-Type', '')
                            file_extension = f".{content_type.split('/')[-1]}" if '/' in content_type else ".jpg"
                            file_path_with_ext = f"{file_path}{file_extension}"
                            async with aiofiles.open(file_path_with_ext, "wb") as f: await f.write(await resp.read())
                            temp_file_paths.append(file_path_with_ext)
                except Exception as e:
                    print(f"Error processing image: {e}")
    return " ".join(user_prompt_parts), temp_file_paths


# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
#               核心新增：对话历史“压平”函数
# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
def flatten_messages_to_prompt(messages: list) -> str:
    """将OpenAI格式的messages列表转换为一个单一的、巨大的字符串prompt。"""
    system_prompt = ""
    history_parts = []

    # 1. 提取系统提示
    system_message = next((msg.content for msg in messages if msg.role == 'system' and isinstance(msg.content, str)),
                          None)
    if system_message:
        system_prompt = (
            f"{SYSTEM_PROMPT_TAG_START}\n"
            f"{system_message}\n"
            f"{SYSTEM_PROMPT_TAG_END}\n\n"
        )

    # 2. 遍历并格式化历史记录
    for msg in messages:
        if msg.role == 'system':
            continue  # 已经处理过了

        role_prefix = "User" if msg.role == 'user' else "Assistant"

        # 处理不同格式的 content
        if isinstance(msg.content, str):
            history_parts.append(f"{role_prefix}: {msg.content}")
        elif isinstance(msg.content, list):
            text_content_parts = [block.text for block in msg.content if isinstance(block, TextContentBlock)]
            full_text = " ".join(text_content_parts)
            history_parts.append(f"{role_prefix}: {full_text}")

    # 3. 组合最终的 prompt
    full_history = "\n\n".join(history_parts)
    return f"{system_prompt}{full_history}"


# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Welcome to CatfishAPI!"}


@app.get("/v1/models", response_model=ModelList, dependencies=[Depends(verify_key)])
async def list_models():
    # ... (保持不变) ...
    try:
        model_ids = await gemini_manager.client.get_models()
        if model_ids: return ModelList(data=[ModelCard(id=model_id) for model_id in model_ids])
    except Exception as e:
        print(f"Error dynamically fetching models: {e}")
    fallback_models = ["gemini-1.5-pro", "gemini-1.5-flash"]
    return ModelList(data=[ModelCard(id=model_id) for model_id in fallback_models])


@app.post("/v1/chat/completions", dependencies=[Depends(verify_key)])
async def chat_completions(request: ChatCompletionRequest):
    # (核心修改) 调用新函数将整个历史记录压平成一个 prompt
    final_prompt_text = flatten_messages_to_prompt(request.messages)

    # 仍然需要调用旧函数，但只为了提取图片文件
    _, temp_files = await process_multimodal_content(request.messages)

    if not final_prompt_text and not temp_files:
        raise HTTPException(status_code=400, detail="No user text or valid image content.")

    # (修改) 每次都创建一个新的、无状态的 Conversation 实例
    convo = Conversation(gemini_manager)
    # session_id 仅用于响应，不再用于状态管理
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # (修改) 调用一个更简单的 send_message
        response_object = await convo.send_message(
            user_input=final_prompt_text,
            model=request.model,
            files=temp_files
        )

        # ... (后续的图文代理和响应构建逻辑完全保持不变) ...
        response_content_parts: list = []
        if response_object.text:
            response_content_parts.append(TextContentBlock(type="text", text=response_object.text))
        if hasattr(response_object, 'images') and response_object.images:
            async with httpx.AsyncClient(proxy=PROXY_URL, cookies=gemini_manager.client.cookies, timeout=30.0,
                                         follow_redirects=True) as client:
                for img in response_object.images:
                    if hasattr(img, 'url') and img.url:
                        try:
                            image_response = await client.get(img.url)
                            image_response.raise_for_status()
                            image_data = image_response.content
                            content_type = image_response.headers.get("content-type", "image/png")
                            base64_encoded_image = base64.b64encode(image_data).decode("utf-8")
                            data_uri = f"data:{content_type};base64,{base64_encoded_image}"
                            image_block = ImageContentBlock(type="image_url", image_url=ImageUrl(url=data_uri))
                            response_content_parts.append(image_block)
                        except Exception as e:
                            print(f"Failed to download or encode image via proxy: {e}")
                            error_text = f"\n[Error: Backend failed to proxy image from {img.url}]"
                            response_content_parts.append(TextContentBlock(type="text", text=error_text))
        final_content: Content
        if len(response_content_parts) == 1 and response_content_parts[0].type == "text":
            final_content = response_content_parts[0].text
        elif not response_content_parts:
            final_content = ""
        else:
            final_content = response_content_parts

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for f in temp_files:
            try:
                os.remove(f)
            except OSError as e:
                print(f"Error cleaning up temp file {f}: {e}")

    if request.stream:
        stream_content: str
        if isinstance(final_content, list):
            texts = [part.text for part in final_content if hasattr(part, 'text')]
            images = [f"![Generated Image]({part.image_url.url})" for part in final_content if
                      hasattr(part, 'image_url')]
            stream_content = "\n".join(texts + images)
        else:
            stream_content = final_content or ""
        return StreamingResponse(fake_stream_response_generator(stream_content, request.model, session_id),
                                 media_type="text/event-stream")
    else:
        response_id = f"chatcmpl-{uuid.uuid4()}"
        created_timestamp = int(time.time())
        response_message = ChatCompletionMessage(role="assistant", content=final_content)
        choice = ChatCompletionChoice(message=response_message)
        return ChatCompletionResponse(id=response_id, created=created_timestamp, model=request.model, choices=[choice],
                                      session_id=session_id)