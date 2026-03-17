import csv
import re
import os
import difflib
import argparse

def list_and_select_file(directory, extension, description):
    """
    列出指定目录下特定扩展名的文件，并让用户选择。
    """
    print(f"\n正在查找 {description} 文件 (目录: {directory})...")
    if not os.path.exists(directory):
        print(f"目录不存在: {directory}")
        return None
        
    files = [f for f in os.listdir(directory) if f.endswith(extension)]
    
    if not files:
        print(f"在 {directory} 中未找到 {extension} 文件")
        return None
        
    print(f"请选择 {description} 文件:")
    for i, f in enumerate(files):
        print(f"{i + 1}. {f}")
        
    while True:
        try:
            choice = input(f"请输入序号 (1-{len(files)}): ")
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return os.path.join(directory, files[idx])
            else:
                print("无效的序号，请重试。")
        except ValueError:
            print("请输入有效的数字。")

def check_missing():
    """
    检查问题集.txt 中的问题是否都已在 mcp_flow_monitor.csv 中执行过。
    """
    parser = argparse.ArgumentParser(description="检查缺失问题")
    parser.add_argument("--txt", help="问题集文件路径")
    parser.add_argument("--csv", help="日志记录文件路径")
    args = parser.parse_args()

    # 交互式选择文件
    txt_dir = r'f:\geroserverFabu\txtquery'
    csv_dir = r'f:\geroserverFabu\csv'
    
    txt_path = args.txt
    if not txt_path:
        txt_path = list_and_select_file(txt_dir, '.txt', "问题集")
        
    if not txt_path:
        return

    csv_path = args.csv
    if not csv_path:
        csv_path = list_and_select_file(csv_dir, '.csv', "日志记录")
        
    if not csv_path:
        return

    print(f"\n正在比对:\n问题集: {txt_path}\n日志: {csv_path}\n")
    
    # 1. 读取 CSV 中的已执行问题 (QUERY 或 问题 列)
    executed_queries = set()
    possible_columns = ['问题', 'QUERY']
    
    if os.path.exists(csv_path):
        try:
            # 尝试 UTF-8-SIG 编码读取 (处理 BOM)
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                # 确定列名
                target_col = None
                if reader.fieldnames:
                    for col in possible_columns:
                        if col in reader.fieldnames:
                            target_col = col
                            break
                
                if target_col:
                    print(f"使用列名: {target_col}")
                    for row in reader:
                        if target_col in row and row[target_col]:
                            executed_queries.add(row[target_col].strip())
                else:
                    print(f"在 CSV (UTF-8) 中未找到支持的问题列 (寻找: {possible_columns})")

        except Exception as e:
            print(f"读取 CSV (UTF-8) 出错: {e}，尝试 GBK...")
            try:
                # 尝试 GBK 编码读取
                with open(csv_path, 'r', encoding='gbk') as f:
                    reader = csv.DictReader(f)
                    # 确定列名
                    target_col = None
                    if reader.fieldnames:
                        for col in possible_columns:
                            if col in reader.fieldnames:
                                target_col = col
                                break
                    
                    if target_col:
                        print(f"使用列名: {target_col}")
                        for row in reader:
                            if target_col in row and row[target_col]:
                                executed_queries.add(row[target_col].strip())
                    else:
                        print(f"在 CSV (GBK) 中未找到支持的问题列 (寻找: {possible_columns})")
                        
            except Exception as e2:
                print(f"读取 CSV (GBK) 也出错: {e2}")
                return

    print(f"CSV 中已记录的问题数量: {len(executed_queries)}")
    
    # 2. 读取 TXT 并提取问题进行比对
    missing_queries = []
    
    if os.path.exists(txt_path):
        try:
            # 尝试 UTF-8 读取
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # 尝试 GBK 读取
             with open(txt_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
                
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 过滤章节标题行，例如 "L101：" 或 "1→c：..."
            # 观察发现章节行通常以 L 开头，或者包含工具定义
            if line.startswith('L') and '：' in line:
                continue
            # 过滤工具定义行，如 "2→g：get_layers..."
            if re.search(r'^\d+→[a-z]+：', line):
                continue
            
            # 提取逻辑
            content = line
            
            # 1. 去掉箭头及之前的序号 (例如 "6→")
            if '→' in content:
                content = content.split('→', 1)[1]
            
            # 2. 去掉开头的 "1.", "2." 等序号
            content = re.sub(r'^\d+\.', '', content).strip()
            
            # 3. 去掉括号及之后的内容（通常是图层名或参数）
            # 示例: "展示全球湖泊（ne_10m_lakes）（cgSH）" -> "展示全球湖泊"
            # 使用正则分割，匹配第一个中文全角括号或英文半角括号
            parts = re.split(r'[（\(]', content, maxsplit=1)
            query_text = parts[0].strip()
            
            # 再次检查提取后的文本是否有效
            if not query_text:
                continue
            
            # 过滤掉一些非问题的描述行
            # 1. 长度过短（例如 "综合"）
            if len(query_text) <= 2: 
                continue
            # 2. 不包含中文字符（排除工具定义行，如 "c：get_cached_visualization_url_tool"）
            if not re.search(r'[\u4e00-\u9fa5]', query_text):
                continue
            # 3. 包含特定关键字
            if '_tool' in line:
                continue

            # 4. 核心比对：检查是否在 executed_queries 集合中
            if query_text not in executed_queries:
                missing_queries.append({
                    'original_line': line,
                    'extracted_query': query_text
                })
    else:
        print(f"未找到文件: {txt_path}")
        return
    
    # 3. 输出结果
    print(f"问题集总行数(估算): {len(lines)}")
    print(f"未在 CSV 中找到的问题数量: {len(missing_queries)}")

    # 自动生成缺失问题集文件
    if missing_queries:
        output_filename = f"{len(missing_queries)}问题集.txt"
        output_path = os.path.join(txt_dir, output_filename)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for item in missing_queries:
                    # 写入原始行内容
                    f.write(item['original_line'] + '\n')
            print(f"\n已自动生成缺失问题集文件: {output_path}")
        except Exception as e:
            print(f"\n生成文件失败: {e}")

    print("-" * 100)
    print(f"{'提取的问题内容':<40} | {'CSV 中最相似的问题 (相似度)'}")
    print("-" * 100)
    
    executed_list = list(executed_queries)
    
    for item in missing_queries:
        q = item['extracted_query']
        # 查找最相似的
        matches = difflib.get_close_matches(q, executed_list, n=1, cutoff=0.6)
        similar = ""
        if matches:
            ratio = difflib.SequenceMatcher(None, q, matches[0]).ratio()
            similar = f"{matches[0]} ({ratio:.2f})"
        else:
            similar = "无相似匹配"
            
        print(f"{q:<40} | {similar}")

if __name__ == "__main__":
    check_missing()
