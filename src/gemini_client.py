# --- gemini_client.py (已修复 NameError 的最终“融合”版) ---

import asyncio
import re
import orjson as json
from pathlib import Path
from typing import Optional

from gemini_webapi import GeminiClient, Gem, ModelOutput, Candidate, WebImage, GeneratedImage
from gemini_webapi.constants import Model, Endpoint
from gemini_webapi.utils import upload_file, parse_file_name, logger
from gemini_webapi.exceptions import APIError, GeminiError, ImageGenerationError

# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
#
#                   这里是唯一的、关键的修正
#
# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
from .config import SECURE_1PSID, SECURE_1PSIDTS, META_GEM_NAME, META_GEM_PROMPT, PROXY_URL
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                         修正结束
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

from .custom_parser import find_generated_images_from_raw_text

original_init = GeminiClient.__init__


async def patched_generate_content(
        self,
        prompt: str,
        files: list[str | Path] | None = None,
        model: Model | str = Model.UNSPECIFIED,
        gem: Gem | str | None = None,
        chat: Optional["ChatSession"] = None,
        **kwargs,
) -> ModelOutput:
    if not isinstance(model, Model): model = Model.from_name(model)
    gem_id = gem.id if isinstance(gem, Gem) else gem
    real_chat_session_instance = chat

    response = await self.client.post(
        Endpoint.GENERATE.value,
        headers=model.model_header,
        data={
            "at": self.access_token,
            "f.req": json.dumps(
                [
                    None,
                    json.dumps(
                        [
                            (
                                [
                                    prompt, 0, None,
                                    [[[await upload_file(file, self.proxy)], parse_file_name(file)] for file in files],
                                ]
                                if files else [prompt]
                            ),
                            None,
                            real_chat_session_instance.metadata if real_chat_session_instance else None,
                        ]
                        + ([None] * 16 + [gem_id] if gem_id else [])
                    ).decode(),
                ]
            ).decode(),
        },
        **kwargs,
    )

    if response.status_code != 200:
        await self.close()
        raise APIError(f"Request failed with status code {response.status_code}")

    try:
        response_json = json.loads(response.text.split("\n")[2])
        body = None
        body_index = 0
        for i, part in enumerate(response_json):
            try:
                main_part = json.loads(part[2])
                if main_part and len(main_part) > 4 and main_part[4]:
                    body = main_part
                    body_index = i
                    break
            except (IndexError, TypeError, ValueError):
                continue

        if not body:
            raise GeminiError("Failed to find response body.")

        candidates = []
        for candidate_index, candidate_data in enumerate(body[4]):
            rcid = candidate_data[0]
            text = candidate_data[1][0]

            thoughts = None
            try:
                thoughts = candidate_data[37][0][0]
            except (TypeError, IndexError):
                pass

            web_images = []
            try:
                if candidate_data[12] and candidate_data[12][1]:
                    web_images = [WebImage(url=img[0][0][0], title=img[7][0], alt=img[0][4], proxy=self.proxy) for img
                                  in candidate_data[12][1]]
            except (TypeError, IndexError):
                pass

            generated_images = []
            image_parsing_failed = False
            try:
                if candidate_data[12] and candidate_data[12][7] and candidate_data[12][7][0]:
                    img_body = None
                    for i in range(body_index, len(response_json)):
                        try:
                            img_part = json.loads(response_json[i][2])
                            if img_part[4][candidate_index][12][7][0]:
                                img_body = img_part
                                break
                        except (IndexError, TypeError, ValueError):
                            continue
                    if not img_body: raise ImageGenerationError("Could not find image data block.")
                    img_candidate = img_body[4][candidate_index]
                    text = re.sub(r"http://googleusercontent\.com/image_generation_content/\d+", "",
                                  img_candidate[1][0]).rstrip()
                    generated_images = [GeneratedImage(url=gen_img[0][3][3],
                                                       title=f"[Generated Image {gen_img[3][6]}]" if gen_img[3][
                                                           6] else "[Generated Image]", alt=(
                            gen_img[3][5][i] if gen_img[3][5] and len(gen_img[3][5]) > i else (
                                gen_img[3][5][0] if gen_img[3][5] else "")), proxy=self.proxy, cookies=self.cookies) for
                                        i, gen_img in enumerate(img_candidate[12][7][0])]
            except (TypeError, IndexError):
                image_parsing_failed = True
                logger.warning("Official parser failed on generated images. Engaging custom parser as fallback.")

            if image_parsing_failed:
                recovered_images = find_generated_images_from_raw_text(response.text, self.cookies, self.proxy)
                if recovered_images:
                    generated_images = recovered_images
                    text = re.sub(r"http://googleusercontent\.com/image_generation_content/\d+", "", text).rstrip()

            candidate = Candidate(rcid=rcid, text=text, thoughts=thoughts, web_images=web_images,
                                  generated_images=generated_images)
            candidates.append(candidate)

        if not candidates:
            raise GeminiError("No valid candidates found.")

        output = ModelOutput(metadata=body[1], candidates=candidates)
        if real_chat_session_instance:
            real_chat_session_instance.last_output = output
        return output

    except Exception as e:
        raise APIError(f"FATAL: The final fusion parser also failed. Error: {e}. Raw Response: {response.text}")


def patched_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)


GeminiClient.__init__ = patched_init
GeminiClient.generate_content = patched_generate_content

print("[INFO] ULTIMATE FUSION MONKEY PATCH APPLIED. Image history and image generation are now robustly supported.")


class GeminiClientManager:
    """这个类保持不变。"""

    def __init__(self, psid: str, psidts: str):
        if not psid or not psidts:
            raise ValueError("Cookies missing.")
        self.client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts, proxy=PROXY_URL)
        self.meta_gem: Gem | None = None

    async def initialize(self):
        print("Initializing Gemini client...")
        await self.client.init()
        print("Client initialized successfully.")
        print(f"Checking for Meta Gem: '{META_GEM_NAME}'...")
        await self.client.fetch_gems()
        existing_gem = self.client.gems.get(name=META_GEM_NAME)
        if existing_gem:
            self.meta_gem = existing_gem
        else:
            print("Meta Gem not found. Creating a new one...")
            self.meta_gem = await self.client.create_gem(name=META_GEM_NAME, prompt=META_GEM_PROMPT)

    async def close(self):
        if self.client: await self.client.close()


gemini_manager = GeminiClientManager(SECURE_1PSID, SECURE_1PSIDTS)