# --- custom_parser.py (生图解析专家版) ---

import json
from gemini_webapi import GeneratedImage


def find_generated_images_from_raw_text(raw_text: str, cookies: dict, proxy: str | None) -> list[GeneratedImage]:
    """
    一个专门的解析器，只负责从原始响应文本中提取生成的图片。
    """
    generated_images = []
    try:
        keyword = ")]}'"
        start_index = raw_text.find(keyword)
        if start_index == -1: return []

        json_blob = raw_text[start_index:]
        clean_text = json_blob[4:].strip() if json_blob.startswith(keyword) else json_blob
        data = json.loads(clean_text)

        # 遍历所有数据块，寻找包含 "https://lh3.googleusercontent.com/gg/" 的部分
        # 这是 Google 生成图片的典型 URL 特征
        for item in data:
            if isinstance(item, list) and len(item) > 2 and isinstance(item[2], str):
                if "https://lh3.googleusercontent.com/gg/" in item[2]:
                    # 找到了一个可能包含图片数据块
                    inner_data_str = item[2]
                    inner_data = json.loads(inner_data_str)

                    # 在这个数据块内部递归查找图片URL
                    urls = _recursive_find_urls(inner_data)
                    for url in urls:
                        generated_images.append(
                            GeneratedImage(
                                url=url,
                                title="[Generated Image (Recovered)]",
                                alt="",
                                proxy=proxy,
                                cookies=cookies
                            )
                        )

        # 去重
        unique_images = []
        seen_urls = set()
        for img in generated_images:
            if img.url not in seen_urls:
                unique_images.append(img)
                seen_urls.add(img.url)

        if unique_images:
            print(f"[DEBUG] Custom parser successfully recovered {len(unique_images)} generated image(s).")
        return unique_images

    except (json.JSONDecodeError, IndexError, TypeError):
        return []


def _recursive_find_urls(data) -> list[str]:
    """递归辅助函数，用于在未知结构中查找所有图片URL"""
    urls = []
    if isinstance(data, dict):
        for key, value in data.items():
            urls.extend(_recursive_find_urls(value))
    elif isinstance(data, list):
        for item in data:
            urls.extend(_recursive_find_urls(item))
    elif isinstance(data, str) and data.startswith("https://lh3.googleusercontent.com/gg/"):
        urls.append(data)
    return urls