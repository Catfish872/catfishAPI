import json


# ==============================================================================
# ======================== START: 替代类定义 =================================
# 我们自己定义这些类，以避免任何导入问题。
# 它们只需要结构和属性名与原始类相同即可。
# ==============================================================================

class _FallbackGeneratedImage:
    """一个替代 gemini_webapi.GeneratedImage 的类"""

    def __init__(self, url: str):
        self.url = url
        self.title = ""  # 保持属性完整
        self.alt = ""  # 保持属性完整


class _FallbackCandidate:
    """一个替代 gemini_webapi.GeminiCandidate 的类"""

    def __init__(self, text: str, image_urls: list[str]):
        self.text = text
        self.generated_images = [_FallbackGeneratedImage(url=u) for u in image_urls]

        # 保持其他属性的结构完整性
        self.web_images = []
        self.code = {}

    @property
    def images(self):
        """为了兼容 main.py 中对 .images 的调用"""
        return self.generated_images + self.web_images


# ==============================================================================
# ========================= END: 替代类定义 ==================================
# ==============================================================================


def parse_error_response_for_images(raw_text: str):
    """
    一个后备解析器，它不关心错误类型，只尝试从原始响应文本中
    强行解析出文本和图片，并返回我们自己定义的替代对象。
    """
    try:
        clean_text = raw_text
        if clean_text.startswith(")]}'"):
            clean_text = clean_text.split('\n', 1)[-1]

        data = json.loads(clean_text)

        inner_json_str = None
        for item in data:
            if isinstance(item, list) and len(item) > 2 and isinstance(item[2], str) and "rc_" in item[2]:
                inner_json_str = item[2]
                break

        if not inner_json_str:
            return None

        inner_data = json.loads(inner_json_str)

        final_text = ""
        image_urls = []

        if isinstance(inner_data, list) and len(inner_data) > 0 and \
                isinstance(inner_data[0], list) and len(inner_data[0]) > 1 and \
                isinstance(inner_data[0][1], list) and len(inner_data[0][1]) > 0:
            final_text = inner_data[0][1][0] or ""

        if isinstance(inner_data, list) and len(inner_data) > 0 and \
                isinstance(inner_data[0], list) and len(inner_data[0]) > 4 and \
                isinstance(inner_data[0][4], list) and len(inner_data[0][4]) > 0 and \
                isinstance(inner_data[0][4][0], list):
            images_block = inner_data[0][4][0]
            for img_data in images_block:
                if isinstance(img_data, list) and len(img_data) > 3 and \
                        isinstance(img_data[3], str) and img_data[3].startswith("https://"):
                    image_urls.append(img_data[3])

        if final_text or image_urls:
            # 返回我们自己定义的替代类的实例
            return _FallbackCandidate(text=final_text, image_urls=image_urls)

    except (json.JSONDecodeError, IndexError, TypeError, KeyError):
        return None

    return None