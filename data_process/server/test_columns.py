
import pandas as pd
import os

csv_path = r"f:\geroserverFabu\csv\dify_deepseek_问题集V2_run1.csv"

try:
    df = pd.read_csv(csv_path, encoding='utf-8')
    print("Encoding: utf-8")
except UnicodeDecodeError:
    df = pd.read_csv(csv_path, encoding='gbk')
    print("Encoding: gbk")

print("Columns:", df.columns.tolist())
for col in df.columns:
    print(f"Column: '{col}' (len={len(col)})")
