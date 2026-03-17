import csv
import os
import re
import sys
import datetime
import glob
from difflib import SequenceMatcher

# 增加日志记录功能
def write_log(content):
    log_path = os.path.join(os.path.dirname(__file__), "process_log.txt")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {content}\n")

def parse_txt_line(line):
    """
    解析TXT行，返回 (原始行, 纯问题文本)
    例如: "1. 展示湖泊（...）" -> ("1. 展示湖泊（...）", "展示湖泊")
    """
    line = line.strip()
    # 1. 去除开头的序号 "1. "
    text_no_num = re.sub(r'^\d+\.\s*', '', line)
    
    # 2. 尝试去除末尾的括号后缀
    # 策略：找到第一个全角左括号 '（'，如果它后面跟着的是类似 SQL 或代码的内容，则截断
    # 但有些问题本身可能包含括号。
    # 观察数据，后缀通常是连续的括号组，位于末尾。
    # 简单策略：以第一个 '（' 分割，取第一部分。但要注意不要误伤问题里的括号。
    # 让我们先试着用正则匹配末尾的括号组
    
    # 假设后缀总是以 （ 开头，且通常包含英文字符
    # 我们可以尝试分割
    parts = text_no_num.split('（')
    if len(parts) > 1:
        # 只要第一部分，通常是中文问题
        question_body = parts[0].strip()
    else:
        question_body = text_no_num.strip()
        
    return line, question_body

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def detect_encoding(file_path):
    """简单的编码检测"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1000)
        return 'utf-8'
    except UnicodeDecodeError:
        return 'gbk'

def select_file_from_dir(directory, patterns, description):
    """从指定目录选择文件"""
    if not os.path.exists(directory):
        print(f"错误: 目录不存在: {directory}")
        return None

    files = []
    if isinstance(patterns, str):
        patterns = [patterns]
    
    for pat in patterns:
        files.extend(glob.glob(os.path.join(directory, pat)))
    
    # 简单的去重排序
    files = sorted(list(set(files)))

    if not files:
        print(f"在 {directory} 未找到符合条件的文件")
        return None

    print(f"\n--- 请选择 {description} ---")
    print(f"目录: {directory}")
    for i, f in enumerate(files):
        print(f"{i + 1}. {os.path.basename(f)}")
    
    while True:
        choice = input(f"请输入序号 (1-{len(files)}): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                selected_file = files[idx]
                print(f"已选择: {os.path.basename(selected_file)}")
                return selected_file
        print("输入无效，请重新输入")

def main():
    print("=== CSV排序工具 (按问题集顺序) ===")
    
    # 预定义目录
    csv_dir = r"f:\geroserverFabu\csv"
    txt_dir = r"f:\geroserverFabu\txtquery"

    # 1. 选择 CSV
    csv_path = select_file_from_dir(csv_dir, "*.csv", "CSV文件")
    if not csv_path:
        return

    # 2. 选择 TXT
    txt_path = select_file_from_dir(txt_dir, "*.txt", "问题集TXT文件")
    if not txt_path:
        return

    # 3. 读取 TXT
    txt_encoding = detect_encoding(txt_path)
    txt_items = [] # List of (original_line, question_body)
    try:
        with open(txt_path, 'r', encoding=txt_encoding) as f:
            for line in f:
                if line.strip():
                    txt_items.append(parse_txt_line(line))
    except Exception as e:
        print(f"读取TXT文件失败: {e}")
        return
        
    print(f"\n读取到 {len(txt_items)} 个问题 (参考顺序)")

    # 4. 读取 CSV
    csv_encoding = detect_encoding(csv_path)
    print(f"检测到CSV编码为: {csv_encoding}")
    
    rows = []
    headers = []
    
    try:
        with open(csv_path, 'r', encoding=csv_encoding, newline='') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                print("CSV文件为空")
                return
            
            print("\nCSV列名:")
            for i, h in enumerate(headers):
                print(f"{i}: {h}")
                
            col_input = input("\n请输入用于匹配的列名 (或序号): ").strip()
            
            target_col_idx = -1
            if col_input.isdigit():
                idx = int(col_input)
                if 0 <= idx < len(headers):
                    target_col_idx = idx
            else:
                if col_input in headers:
                    target_col_idx = headers.index(col_input)
            
            if target_col_idx == -1:
                print("无效的列名或序号")
                return
                
            print(f"使用列 '{headers[target_col_idx]}' 进行匹配")
            
            for row in reader:
                rows.append(row)
                
    except Exception as e:
        print(f"读取CSV文件失败: {e}")
        return

    # 5. 匹配逻辑 (模糊匹配 + 排序)
    print("\n正在进行智能匹配排序...")
    
    # 建立 CSV 数据的索引池： {row_index: (row_data, match_value)}
    csv_pool = {}
    for i, row in enumerate(rows):
        if len(row) > target_col_idx:
            val = row[target_col_idx].strip()
            # 简单的清洗，去掉可能的括号后缀（如果有的话，保持一致性）
            _, val_body = parse_txt_line(val)
            csv_pool[i] = {'row': row, 'val': val, 'val_body': val_body}
            
    sorted_rows = []
    matched_csv_indices = set()
    
    # 遍历 TXT 问题集
    for txt_orig, txt_body in txt_items:
        best_match_idx = -1
        best_match_score = 0
        match_type = "None"
        
        # 在剩余的 CSV 行中寻找最佳匹配
        for idx, item in csv_pool.items():
            if idx in matched_csv_indices:
                continue
                
            csv_val = item['val']
            csv_body = item['val_body']
            
            score = 0
            # 1. 精确匹配 Body
            if csv_body == txt_body:
                score = 1.0
                match_type = "Exact"
            # 2. 包含匹配 (CSV 是 TXT 的一部分，或者反之)
            elif csv_body in txt_body or txt_body in csv_body:
                # 长度差异不能太大，防止误判
                len_ratio = min(len(csv_body), len(txt_body)) / max(len(csv_body), len(txt_body))
                if len_ratio > 0.5:
                    score = 0.95
                    match_type = "Contain"
            # 3. 模糊匹配
            else:
                sim = similarity(csv_body, txt_body)
                if sim > 0.8: # 阈值可调
                    score = sim
                    match_type = "Fuzzy"
            
            # 更新最佳匹配
            if score > best_match_score:
                best_match_score = score
                best_match_idx = idx
                # 如果是精确匹配，直接跳出循环
                if score == 1.0:
                    break
        
        # 如果找到了足够好的匹配
        if best_match_idx != -1 and best_match_score > 0.8:
            sorted_rows.append(csv_pool[best_match_idx]['row'])
            matched_csv_indices.add(best_match_idx)
            # print(f"Match: TXT='{txt_body}' <-> CSV='{csv_pool[best_match_idx]['val_body']}' ({match_type}, {best_match_score:.2f})")
    
    # 识别删除的内容
    deleted_rows = []
    deleted_contents = []
    for idx, item in csv_pool.items():
        if idx not in matched_csv_indices:
            deleted_rows.append(item['row'])
            deleted_contents.append(item['val'])
            
    # 输出结果
    print(f"\n处理结果:")
    print(f"原始CSV行数: {len(rows)}")
    print(f"排序后CSV行数: {len(sorted_rows)}")
    print(f"删除行数: {len(deleted_rows)}")
    
    if deleted_rows:
        print("\n删除的内容 (前10条):")
        for content in deleted_contents[:10]:
            print(f"- {content}")
        if len(deleted_contents) > 10:
            print(f"... 以及其他 {len(deleted_contents)-10} 条")

    # 保存
    base, ext = os.path.splitext(csv_path)
    out_path = f"{base}_sorted{ext}"
    
    try:
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(sorted_rows)
        print(f"\n文件已保存: {out_path}")
        
        # 记录日志
        log_content = f"CSV排序完成。源文件: {csv_path}, 参考TXT: {txt_path}, 原行数: {len(rows)}, 结果行数: {len(sorted_rows)}, 删除行数: {len(deleted_rows)}"
        write_log(log_content)
        
    except Exception as e:
        print(f"保存文件失败: {e}")

if __name__ == "__main__":
    main()
