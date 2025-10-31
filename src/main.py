import uuid
import time
import json
import re
import ast
import base64
import aiohttp
import aiofiles
import os
from contextlib import asynccontextmanager
import httpx  # <--- 新增: 用于带认证下载图片

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from cachetools import TTLCache

from .config import API_KEY, PROXY_URL  # <--- 导入 PROXY_URL
from .gemini_client import gemini_manager
from .conversation import Conversation
from .models import (
    ChatCompletionRequest, ChatCompletionResponse, ChatCompletionMessage,
    ChatCompletionChoice, ModelList, ModelCard, TextContentBlock,
    ImageContentBlock, GeneratedImage
)
from gemini_webapi import GeneratedImage as GeminiGeneratedImage

# ... (ACTIVE_SESSIONS, lifespan, app, auth_scheme, verify_key, fake_stream_response_generator, process_multimodal_content 保持不变)
ACTIVE_SESSIONS: TTLCache[str, Conversation] = TTLCache(maxsize=1024, ttl=3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("temp_uploads", exist_ok=True)
    await gemini_manager.initialize()
    yield
    await gemini_manager.close()


app = FastAPI(lifespan=lifespan, title="Catfish API", version="1.2.2 Final")  # Final Version Bump!
auth_scheme = HTTPBearer()


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
    # ... (此函数保持不变)
    user_prompt_parts = []
    temp_file_paths = []
    last_user_message = next((msg for msg in reversed(messages) if msg.role == 'user'), None)
    if not last_user_message: return "", []
    if isinstance(last_user_message.content, str): return last_user_message.content, []
    async with aiohttp.ClientSession() as session:
        for content_block in last_user_message.content:
            if isinstance(content_block, TextContentBlock):
                user_prompt_parts.append(content_block.text)
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


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Welcome to CatfishAPI!"}


@app.get("/v1/models", response_model=ModelList, dependencies=[Depends(verify_key)])
async def list_models():
    # ... (此函数保持不变)
    try:
        model_ids = await gemini_manager.client.get_models()
        if model_ids: return ModelList(data=[ModelCard(id=model_id) for model_id in model_ids])
    except Exception as e:
        print(f"Error dynamically fetching models: {e}")
    fallback_models = ["gemini-1.5-pro", "gemini-1.5-flash"]
    return ModelList(data=[ModelCard(id=model_id) for model_id in fallback_models])


@app.post("/v1/chat/completions", dependencies=[Depends(verify_key)])
async def chat_completions(request: ChatCompletionRequest):
    system_prompt = next(
        (msg.content for msg in request.messages if isinstance(msg.content, str) and msg.role == 'system'), None)
    user_input_text, temp_files = await process_multimodal_content(request.messages)
    if not user_input_text and not temp_files: raise HTTPException(status_code=400,
                                                                   detail="No user text or valid image content.")

    session_id = request.session_id
    if session_id and session_id in ACTIVE_SESSIONS:
        convo = ACTIVE_SESSIONS[session_id]
    else:
        convo = Conversation(gemini_manager)
        session_id = str(uuid.uuid4())
        ACTIVE_SESSIONS[session_id] = convo

    try:
        response_object = await convo.send_message(
            user_input=user_input_text,
            dynamic_system_prompt=system_prompt,
            model=request.model,
            files=temp_files
        )
        ai_response_content = response_object.text or ""

        # vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
        #               核心修改：图片代理逻辑
        # vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
        if response_object.images:
            image_md_parts = ["\n\n**Generated Images:**"]
            # 创建一个带认证和代理的异步HTTP客户端来下载图片
            async with httpx.AsyncClient(
                    proxy=PROXY_URL,
                    cookies=gemini_manager.client.cookies,
                    timeout=30.0,
                    follow_redirects=True
            ) as client:
                for img in response_object.images:
                    if isinstance(img, GeminiGeneratedImage):
                        try:
                            print(f"Downloading generated image from: {img.url}")
                            # 使用后端客户端下载图片数据
                            image_response = await client.get(img.url)
                            image_response.raise_for_status()
                            image_data = image_response.content

                            # 将图片数据编码为 Base64
                            content_type = image_response.headers.get("content-type", "image/png")
                            base64_encoded_image = base64.b64encode(image_data).decode("utf-8")

                            # 创建一个可以直接在<img>标签中使用的 Data URI
                            data_uri = f"data:{content_type};base64,{base64_encoded_image}"

                            # 将 Data URI 放入 Markdown
                            image_md_parts.append(f"![Generated Image]({data_uri})")

                        except Exception as e:
                            print(f"Failed to download or encode image: {e}")
                            # 如果下载失败，返回原始URL作为备用
                            image_md_parts.append(f"![Failed to load image]({img.url})")

            ai_response_content += "\n".join(image_md_parts)
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for f in temp_files:
            try:
                os.remove(f)
            except OSError as e:
                print(f"Error cleaning up temp file {f}: {e}")

    if request.stream:
        return StreamingResponse(fake_stream_response_generator(ai_response_content, request.model, session_id),
                                 media_type="text/event-stream")
    else:
        response_id = f"chatcmpl-{uuid.uuid4()}"
        created_timestamp = int(time.time())
        response_message = ChatCompletionMessage(role="assistant", content=ai_response_content)
        choice = ChatCompletionChoice(message=response_message)
        return ChatCompletionResponse(id=response_id, created=created_timestamp, model=request.model, choices=[choice],
                                      session_id=session_id)