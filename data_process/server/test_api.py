
import requests
import urllib.parse

# Assuming server is running at localhost:8005 (default in main.py)
url = "http://127.0.0.1:8005/api/file_content"
path = r"f:\geroserverFabu\csv\dify_deepseek_问题集V2_run1.csv"
params = {"path": path}

try:
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        print("Columns:", data.get("columns"))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"Request failed: {e}")
