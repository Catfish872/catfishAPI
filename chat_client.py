import os
import requests
import json
from dotenv import load_dotenv

# --- 配置 ---
# 从 .env 文件加载环境变量，这样我们就不需要手动设置了
load_dotenv()

API_URL_BASE = "http://127.0.0.1:8000"
MODELS_ENDPOINT = f"{API_URL_BASE}/v1/models"
CHAT_ENDPOINT = f"{API_URL_BASE}/v1/chat/completions"

# 从环境变量中读取API Key
API_KEY = os.environ.get("API_KEY")
MODEL_TO_USE = "gemini-2.5-flash"


def fetch_and_list_models(headers: dict):
    """获取并打印可用的模型列表。"""
    print("--- 1. Fetching available models from the server ---")
    try:
        response = requests.get(MODELS_ENDPOINT, headers=headers)
        response.raise_for_status()  # 检查HTTP错误

        models_data = response.json()
        model_ids = [model['id'] for model in models_data.get('data', [])]

        if not model_ids:
            print("Could not find any available models.")
            return False

        print("✅ Models fetched successfully. Available models:")
        for model_id in model_ids:
            print(f"   - {model_id}")
        return True

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("❌ Authentication Error: The provided API_KEY is incorrect.")
            print("   Please check your .env file and ensure API_KEY is set correctly.")
        else:
            print(f"❌ HTTP Error fetching models: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection Error: Could not connect to the server at {API_URL_BASE}.")
        print(f"   Please ensure the server is running. Details: {e}")
        return False


def start_chat_loop(headers: dict):
    """启动交互式聊天循环。"""
    print(f"\n--- 2. Starting interactive chat using model: '{MODEL_TO_USE}' ---")
    print("Type 'exit' or 'quit' to end the conversation.")
    print("Type 'new' to start a new conversation.")

    print("\nEnter the System Prompt for this session (or press Enter for default):")
    system_prompt = input("> ")
    if not system_prompt:
        system_prompt = "You are a helpful AI assistant."
        print(f"Using default system prompt: '{system_prompt}'")

    session_id = None

    while True:
        print("-" * 50)
        user_message = input("You: ")

        if user_message.lower() in ["exit", "quit"]:
            print("\nGoodbye!")
            break

        if user_message.lower() == "new":
            session_id = None
            print("\n✨ Starting a new conversation.")
            print("Enter the System Prompt for this new conversation (or press Enter for default):")
            system_prompt = input("> ")
            if not system_prompt:
                system_prompt = "You are a helpful AI assistant."
                print(f"Using default system prompt: '{system_prompt}'")
            continue

        messages = []
        if session_id is None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": MODEL_TO_USE,
            "messages": messages,
            "session_id": session_id
        }

        try:
            response = requests.post(CHAT_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()
            ai_response = data['choices'][0]['message']['content']
            session_id = data['session_id']

            print(f"\nAI: {ai_response}")

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print("\n❌ Authentication Error: API Key is incorrect. Exiting.")
                break
            else:
                print(f"\n[Error]: HTTP Error: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            print(f"\n[Error]: Could not connect to the API server. Details: {e}")
        except (KeyError, IndexError, json.JSONDecodeError):
            print(f"\n[Error]: Failed to parse the server's response. Text: {response.text}")


def main():
    """主函数，检查配置并启动客户端。"""
    print("=============================================")
    print("    CatfishAPI Interactive Client v2.0     ")
    print("=============================================")

    if not API_KEY:
        print("❌ Error: API_KEY environment variable not found.")
        print("Please create a .env file in the root directory and add your API_KEY.")
        return

    # 准备所有请求都需要使用的认证头部
    auth_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    # 第一步：获取模型列表
    if fetch_and_list_models(auth_headers):
        # 如果成功，则进入聊天循环
        start_chat_loop(auth_headers)


if __name__ == "__main__":
    main()