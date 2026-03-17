import csv
import os
import re
import glob
import statistics
from difflib import SequenceMatcher

# 映射字典：全称工具名 -> 黄金链代号
TOOL_MAP = {
    'get_cached_visualization_url': 'c',
    'get_layers_for_ai_selection': 'g',
    'filter_features_to_temp_layer': 'f',
    'get_layer_schema': 'k',
    'get_field_values': 'v',
    'overlay_analysis': 'o',
    'calculate_layer_metrics': 'a',
    'calculate_layer_distance': 'd',
    'buffer_analysis': 'b',
    'show_layer_on_map': 'SH'
}

def parse_txt_line(line):
    """从 TXT 行中提取：1. 问题文本 (去掉序号) 2. 黄金工具链字符串"""
    line = line.strip()
    if not line: return None, None
    gold_chain_match = re.search(r'[（\(]([a-zA-Z]+)[）\)]$', line)
    gold_chain = ""
    question_body = line
    if gold_chain_match:
        gold_chain = gold_chain_match.group(1)
        question_body = line[:gold_chain_match.start()].strip()
    question_body = re.sub(r'^\d+[→\.]\s*', '', question_body).strip()
    return question_body, gold_chain

def tokenize_chain(chain_str):
    """将代号链解析为 token 列表"""
    tokens = []
    i = 0
    while i < len(chain_str):
        if chain_str[i:i+2] == 'SH':
            tokens.append('SH')
            i += 2
        else:
            tokens.append(chain_str[i])
            i += 1
    return tokens

def convert_csv_tool_chain(tool_str):
    """将 CSV 工具链转换为 tokens"""
    if not tool_str: return []
    
    # 兼容多种分隔符: '->' 或 ','
    if '->' in tool_str:
        parts = tool_str.split('->')
    else:
        parts = tool_str.split(',')
        
    tokens = []
    for p in parts:
        p = p.strip()
        # 去除可能残留的引号
        p = p.strip('"').strip("'")
        
        if not p: continue
        
        matched_code = None
        for name, code in TOOL_MAP.items():
            # 1. 精确匹配 name
            # 2. 匹配 name + "_tool" (例如 CSV 是 get_xxx, Map 是 get_xxx_tool - 不太可能，Map key 是无 tool 的)
            # 3. 匹配 p 是 name + "_tool" (例如 CSV 是 get_xxx_tool, Map 是 get_xxx)
            if p == name or p == name + "_tool":
                matched_code = code
                break
            # 反向匹配: 如果 p 有 _tool 后缀，尝试去掉后匹配 Map key
            if p.endswith('_tool') and p[:-5] == name:
                matched_code = code
                break
                
        if matched_code: tokens.append(matched_code)
        else: tokens.append('UNK')
    return tokens

def calculate_lcs_len(gold_tokens, actual_tokens):
    """计算 LCS 长度"""
    m, n = len(gold_tokens), len(actual_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if gold_tokens[i-1] == actual_tokens[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]

def select_file_from_dir(directory, patterns, description):
    """从目录选择文件"""
    if not os.path.exists(directory):
        print(f"错误: 目录不存在: {directory}")
        return None
    files = []
    if isinstance(patterns, str): patterns = [patterns]
    for pat in patterns: files.extend(glob.glob(os.path.join(directory, pat)))
    files = sorted(list(set(files)))
    if not files:
        print(f"在 {directory} 未找到符合条件的文件")
        return None
    print(f"\n--- 请选择 {description} ---")
    for i, f in enumerate(files):
        print(f"{i + 1}. {os.path.basename(f)}")
    while True:
        choice = input(f"请输入序号 (1-{len(files)}): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(files): return files[idx]
        print("输入无效")

def get_headers(csv_path):
    """读取 CSV 头部"""
    enc = 'utf-8'
    try:
        with open(csv_path, 'r', encoding='utf-8') as f: f.read(1000)
    except: enc = 'gbk'
    
    with open(csv_path, 'r', encoding=enc, newline='') as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
            return headers, enc
        except StopIteration:
            return [], enc

def manual_select_column(headers, prompt, allow_empty=False):
    """手动选择列"""
    print(f"\n{prompt}")
    for i, h in enumerate(headers):
        print(f"{i}. {h}")
    if allow_empty:
        print("N. 不选择 (跳过)")
        
    while True:
        choice = input("请输入列序号: ").strip()
        if allow_empty and choice.upper() == 'N':
            return -1
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(headers):
                return idx
        print("输入无效")

def main():
    print("=== 综合指标计算脚本 (SR, TIA, ART) ===")
    
    csv_dir = r"f:\geroserverFabu\csv\merged_results"
    txt_dir = r"f:\geroserverFabu\txtquery"
    
    # 1. 选择 CSV
    csv_path = select_file_from_dir(csv_dir, "*.csv", "CSV结果文件")
    if not csv_path: return
    headers, encoding = get_headers(csv_path)
    if not headers:
        print("CSV 文件为空")
        return

    # 2. 选择指标
    print("\n--- 请选择要计算的指标 (多选，用逗号分隔) ---")
    print("1. SR  (成功率)")
    print("2. TIA (工具调用准确率)")
    print("3. ART (平均响应时间)")
    print("4. Token (平均Token消耗)")
    print("5. 全部计算")
    
    metric_choice = input("请输入选项 (例如 1,3): ").strip()
    selected_metrics = set()
    if '5' in metric_choice or not metric_choice:
        selected_metrics = {'SR', 'TIA', 'ART', 'Token'}
    else:
        # 支持逗号、空格分隔
        clean_input = metric_choice.replace('，', ',').replace(' ', ',')
        parts = [p.strip() for p in clean_input.split(',') if p.strip()]
        
        if '1' in parts: selected_metrics.add('SR')
        if '2' in parts: selected_metrics.add('TIA')
        if '3' in parts: selected_metrics.add('ART')
        if '4' in parts: selected_metrics.add('Token')
    
    print(f"已选择指标: {', '.join(selected_metrics)}")
    
    # 3. 如果选择了 TIA，需要加载 TXT
    gold_map = {}
    if 'TIA' in selected_metrics:
        txt_path = select_file_from_dir(txt_dir, "*.txt", "问题集TXT文件")
        if not txt_path: return
        print(f"\n正在读取问题集: {os.path.basename(txt_path)}...")
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    q, chain = parse_txt_line(line)
                    if q and chain: gold_map[q] = chain
        except Exception as e:
            print(f"读取TXT失败: {e}")
            return
    
    # 4. 选择尺度
    print("\n--- 请选择等级尺度 ---")
    print("1. 尺度 20 (L1:1-20, L2:21-40...)")
    print("2. 尺度 60 (L1:1-60, L2:61-120...)")
    scale_choice = input("请输入选项 (1 或 2): ").strip()
    scale_size = 60 if scale_choice == '2' else 20

    # 5. 列映射 (自动检测 + 手动确认)
    print("\n--- 字段映射配置 ---")
    
    # 自动尝试识别 Query
    query_idx = -1
    for i, h in enumerate(headers):
        if 'query' in h.lower() or '问题' in h.lower() or 'question' in h.lower():
            query_idx = i
            break
            
    # 自动尝试识别 Groups
    auto_groups = []
    # 假设最多检测 5 组
    for suffix_idx in range(1, 6):
        suffix = f"_{suffix_idx}"
        g = {'tool': -1, 'dur': -1, 'succ': -1, 'token': -1}
        found_any = False
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if h_lower.endswith(suffix):
                if 'tool' in h_lower or '工具' in h_lower: g['tool'] = i; found_any = True
                elif 'duration' in h_lower or '耗时' in h_lower: g['dur'] = i; found_any = True
                elif '是否成功' in h_lower or 'success' in h_lower: g['succ'] = i; found_any = True
                elif 'token' in h_lower: g['token'] = i; found_any = True
        if found_any:
            auto_groups.append(g)
    
    print(f"自动检测到 Query 列索引: {query_idx} ({headers[query_idx] if query_idx>=0 else '未找到'})")
    print(f"自动检测到 {len(auto_groups)} 组运行数据。")
    
    use_auto = input("是否使用自动检测的列映射? (y/n, 默认y): ").strip().lower()
    if use_auto == 'n':
        # 手动映射
        query_idx = manual_select_column(headers, "请选择【问题/Query】列:")
        
        while True:
            try:
                run_count = int(input("请输入每个问题的运行次数 (例如 3): ").strip())
                if run_count > 0: break
            except: pass
            
        group_indices = []
        for r in range(run_count):
            print(f"\n--- 配置第 {r+1} 次运行的列 ---")
            g = {'tool': -1, 'dur': -1, 'succ': -1, 'token': -1}
            
            if 'TIA' in selected_metrics:
                g['tool'] = manual_select_column(headers, f"请选择 Run {r+1} 的【工具/Tool】列:")
            
            if 'ART' in selected_metrics:
                g['dur'] = manual_select_column(headers, f"请选择 Run {r+1} 的【耗时/Duration】列:")
            
            if 'Token' in selected_metrics:
                g['token'] = manual_select_column(headers, f"请选择 Run {r+1} 的【Token】列:")
            
            # SR 需要 Success，TIA 也依赖 Success 来判定归零
            if 'SR' in selected_metrics or 'TIA' in selected_metrics:
                g['succ'] = manual_select_column(headers, f"请选择 Run {r+1} 的【是否成功/Success】列:")
                
            group_indices.append(g)
    else:
        group_indices = auto_groups
        if query_idx == -1:
             query_idx = manual_select_column(headers, "自动检测失败，请手动选择【问题/Query】列:")

    # 6. 处理数据
    print(f"\n正在分析 CSV...")
    results = []
    
    with open(csv_path, 'r', encoding=encoding, newline='') as f:
        reader = csv.reader(f)
        next(reader) # Skip headers
        
        for row in reader:
            if not row: continue
            if query_idx >= len(row): continue
            
            # Query
            q_raw = row[query_idx]
            q_clean = re.sub(r'^\d+[→\.]\s*', '', q_raw).strip()
            
            # Gold Chain
            gold_chain_str = None
            if 'TIA' in selected_metrics:
                gold_chain_str = gold_map.get(q_clean)
                if not gold_chain_str:
                    for k, v in gold_map.items():
                        if q_clean in k or k in q_clean:
                            gold_chain_str = v
                            break
            
            # Metrics for this row
            row_success_count = 0
            row_durations = []
            row_tokens = []
            row_tias = []
            valid_runs = 0
            
            for g in group_indices:
                # Success
                is_success = False
                if g['succ'] != -1 and g['succ'] < len(row):
                    val = row[g['succ']].strip()
                    if val == '是' or val.lower() == 'true':
                        is_success = True
                        row_success_count += 1
                
                # Duration
                if g['dur'] != -1 and g['dur'] < len(row):
                    try:
                        row_durations.append(float(row[g['dur']]))
                    except:
                        row_durations.append(0.0)
                
                # Token
                if g['token'] != -1 and g['token'] < len(row):
                    try:
                        row_tokens.append(float(row[g['token']]))
                    except:
                        row_tokens.append(0.0)

                # TIA
                if 'TIA' in selected_metrics and g['tool'] != -1 and g['tool'] < len(row):
                    acc = 0.0
                    if gold_chain_str:
                        tool_str = row[g['tool']]
                        actual_tokens = convert_csv_tool_chain(tool_str)
                        gold_tokens = tokenize_chain(gold_chain_str)
                        lcs = calculate_lcs_len(gold_tokens, actual_tokens)
                        gold_len = len(gold_tokens)
                        acc = lcs / gold_len if gold_len > 0 else 0
                    
                    # 仅将成功的运行计入 TIA (修改为: 失败算0, 分母为总运行次数)
                    if is_success:
                        row_tias.append(acc)
                    else:
                        row_tias.append(0.0)
                        
            # Aggregate Row Data
            row_data = {'success_count': row_success_count}
            
            # TIA Logic
            if 'TIA' in selected_metrics:
                if row_tias:
                    row_data['avg_tia'] = statistics.mean(row_tias)
                else:
                    row_data['avg_tia'] = 0.0
            
            # ART Logic
            if 'ART' in selected_metrics:
                row_data['avg_duration'] = statistics.mean(row_durations) if row_durations else 0.0
            
            # Token Logic
            if 'Token' in selected_metrics:
                row_data['avg_token'] = statistics.mean(row_tokens) if row_tokens else 0.0
                
            results.append(row_data)

    # 7. 分级汇总
    # 动态生成等级 L1, L2, ...
    max_items = len(results)
    num_levels = (max_items + scale_size - 1) // scale_size
    
    summary = []
    
    for i in range(num_levels):
        start_idx = i * scale_size
        end_idx = min((i + 1) * scale_size, max_items)
        items = results[start_idx:end_idx]
        if not items: continue
        
        level_name = f"L{i+1}"
        count = len(items)
        runs_per_item = len(group_indices)
        
        stat = {'Level': level_name, 'Count': count}
        
        if 'SR' in selected_metrics:
            total_succ = sum(x['success_count'] for x in items)
            # 注意：分母是 (题目数 * 运行次数)
            stat['SR'] = total_succ / (count * runs_per_item) if count > 0 else 0
            
        if 'TIA' in selected_metrics:
            stat['TIA'] = statistics.mean(x['avg_tia'] for x in items) if count > 0 else 0
            
        if 'ART' in selected_metrics:
            stat['ART'] = statistics.mean(x['avg_duration'] for x in items) if count > 0 else 0
            
        if 'Token' in selected_metrics:
            stat['Token'] = statistics.mean(x['avg_token'] for x in items) if count > 0 else 0
            
        summary.append(stat)
        
    # 添加 Total 行
    if results:
        total_count = len(results)
        runs_per_item = len(group_indices)
        total_stat = {'Level': 'Total', 'Count': total_count}
        
        if 'SR' in selected_metrics:
            total_succ = sum(x['success_count'] for x in results)
            total_stat['SR'] = total_succ / (total_count * runs_per_item)
            
        if 'TIA' in selected_metrics:
            total_stat['TIA'] = statistics.mean(x['avg_tia'] for x in results)
            
        if 'ART' in selected_metrics:
            total_stat['ART'] = statistics.mean(x['avg_duration'] for x in results)
            
        if 'Token' in selected_metrics:
            total_stat['Token'] = statistics.mean(x['avg_token'] for x in results)
            
        summary.append(total_stat)

    # 8. 输出
    print("\n=== 计算结果 ===")
    headers = ['Level']
    if 'SR' in selected_metrics: headers.append('SR')
    if 'TIA' in selected_metrics: headers.append('TIA')
    if 'ART' in selected_metrics: headers.append('ART (s)')
    if 'Token' in selected_metrics: headers.append('Token')
    headers.append('Count')
    
    # 打印表头
    header_str = " | ".join([f"{h:<10}" for h in headers])
    print(header_str)
    print("-" * len(header_str))
    
    for s in summary:
        row_str = f"{s['Level']:<10}"
        if 'SR' in selected_metrics: row_str += f" | {s['SR']:<9.2%}"
        if 'TIA' in selected_metrics: row_str += f" | {s['TIA']:<9.2%}"
        if 'ART' in selected_metrics: row_str += f" | {s['ART']:<9.2f}"
        if 'Token' in selected_metrics: row_str += f" | {s.get('Token', 0):<9.2f}"
        row_str += f" | {s['Count']}"
        print(row_str)

    # 保存
    base_name = os.path.splitext(os.path.basename(csv_path))[0]
    output_path = os.path.join(csv_dir, f"{base_name}_M.csv")
    try:
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            # 需要把 key 对应回去 (SR -> SR, ART (s) -> ART)
            # DictWriter 需要准确的 keys
            clean_summary = []
            for s in summary:
                new_s = {'Level': s['Level'], 'Count': s['Count']}
                if 'SR' in selected_metrics: new_s['SR'] = s['SR']
                if 'TIA' in selected_metrics: new_s['TIA'] = s['TIA']
                if 'ART' in selected_metrics: new_s['ART (s)'] = s['ART']
                if 'Token' in selected_metrics: new_s['Token'] = s.get('Token', 0)
                clean_summary.append(new_s)
            
            writer.writerows(clean_summary)
        print(f"\n结果已保存至: {output_path}")
    except Exception as e:
        print(f"保存结果失败: {e}")

if __name__ == "__main__":
    main()
