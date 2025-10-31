import browser_cookie3

# 只使用edge的cookies
cj = browser_cookie3.edge()

# 提取Gemini的cookies
gemini_cookies = {c.name: c.value for c in cj if ".google.com" in c.domain and c.name in ["__Secure-1PSID", "__Secure-1PSIDTS"]}

if "__Secure-1PSID" in gemini_cookies and "__Secure-1PSIDTS" in gemini_cookies:
    print("✅ Cookies found successfully!")
    print("-" * 40)
    print(f"SECURE_1PSID=\"{gemini_cookies['__Secure-1PSID']}\"")
    print(f"SECURE_1PSIDTS=\"{gemini_cookies['__Secure-1PSIDTS']}\"")
    print("-" * 40)
    print("Copy these values and set them as your environment variables.")
else:
    print("❌ Could not find Gemini cookies. Please make sure you are logged in to gemini.google.com in your browser (e.g., Chrome, Firefox).")