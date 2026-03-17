import csv
import os
import re
import sys
import glob

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
    """
    从 TXT 行中提取：
    1. 问题文本 (去掉序号)
    2. 黄金工具链字符串 (从末尾括号中提取)
    """
    line = line.strip()
    if not line:
        return None, None
        
    # 1. 提取黄金工具链：通常在末尾的圆括号中，例如 （cgSH）
    # 使用正则从末尾寻找 (chars)
    # 注意：全角括号 '（' 和半角 '(' 都可能出现
    
    # 策略：先找末尾的括号内容
    # 假设黄金链只包含字母
    gold_chain_match = re.search(r'[（\(]([a-zA-Z]+)[）\)]$', line)
    
    gold_chain = ""
    question_body = line
    
    if gold_chain_match:
        gold_chain = gold_chain_match.group(1)
        # 将问题文本截断到括号前
        question_body = line[:gold_chain_match.start()].strip()
    
    # 清理问题文本开头的序号
    question_body = re.sub(r'^\d+\.\s*', '', question_body).strip()
    
    # 有时候括号里可能是表名，黄金链在更后面的括号里？或者同一个括号里？
    # 观察样例：1.展示全球湖泊（ne_10m_lakes）（cgSH）
    # 这种情况下，上面的正则只会匹配最后一个括号 (cgSH)，是正确的。
    
    return question_body, gold_chain

def convert_csv_tool_chain(tool_str):
    """
    将 CSV 中的工具链字符串转换为代号链
    例如: "get_cached_visualization_url -> -> get_layers_for_ai_selection" -> "cg"
    """
    if not tool_str:
        return ""
        
    # 分割字符串，通常是用 " -> " 分割
    # 但有时会有 " ->  -> " 这种空隙，或者其他分隔符
    # 简单策略：提取所有单词，看是否在映射表中
    
    # 先尝试按 -> 分割
    parts = tool_str.split('->')
    
    chain = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 有些工具名可能带有 _tool 后缀，或者没有
        # 我们的映射表里的键没有 _tool 后缀，但 CSV 里可能有？
        # 观察 CSV：get_cached_visualization_url (没有 _tool)
        # 观察 TXT 头部定义：get_cached_visualization_url_tool (有 _tool)
        # 只要匹配前缀即可
        
        # 尝试匹配
        matched_code = None
        for name, code in TOOL_MAP.items():
            if p == name or p == name + "_tool":
                matched_code = code
                break
        
        if matched_code:
            chain.append(matched_code)
        # else:
            # print(f"Warning: Unknown tool in CSV: {p}")
            
    return "".join(chain)

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
                return files[idx]
        print("输入无效，请重新输入")

def main():
    print("=== 工具调用准确率计算器 ===")
    
    csv_dir = r"f:\geroserverFabu\csv"
    txt_dir = r"f:\geroserverFabu\txtquery"
    
    # 1. 选择文件
    csv_path = select_file_from_dir(csv_dir, "*.csv", "CSV文件")
    if not csv_path: return
    
    txt_path = select_file_from_dir(txt_dir, "*.txt", "问题集TXT文件")
    if not txt_path: return
    
    # 2. 读取并解析 TXT (建立 问题 -> 黄金链 的映射)
    print(f"\n正在读取问题集: {os.path.basename(txt_path)}...")
    gold_map = {} # {question_body: gold_chain}
    
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                q, chain = parse_txt_line(line)
                if q and chain:
                    gold_map[q] = chain
    except Exception as e:
        print(f"读取TXT失败: {e}")
        return
        
    print(f"提取到 {len(gold_map)} 条带有黄金链的问题")
    
    # 3. 读取 CSV 并计算
    print(f"\n正在分析CSV: {os.path.basename(csv_path)}...")
    
    total_gold_len = 0
    total_match_len = 0
    
    # 用于记录详细差异
    diff_records = []
    
    try:
        # 简单的编码检测
        enc = 'utf-8'
        try:
            with open(csv_path, 'r', encoding='utf-8') as f: f.read(1000)
        except:
            enc = 'gbk'
            
        with open(csv_path, 'r', encoding=enc, newline='') as f:
            reader = csv.reader(f)
            headers = next(reader)
            
            # 寻找列索引
            try:
                query_idx = -1
                tool_idx = -1
                
                # 模糊匹配列名
                for i, h in enumerate(headers):
                    h_lower = h.lower()
                    if 'query' in h_lower or '问题' in h_lower:
                        query_idx = i
                    if 'tool' in h_lower or '工具' in h_lower:
                        tool_idx = i
                
                if query_idx == -1 or tool_idx == -1:
                    print(f"错误: 无法自动识别 QUERY 或 TOOL 列。Header: {headers}")
                    # 手动回落：假设 1 是 query, 2 是 tool (基于之前的观察)
                    if len(headers) >= 3:
                        print("尝试使用默认索引: Query=1, Tool=2")
                        query_idx = 1
                        tool_idx = 2
                    else:
                        return
                        
                processed_count = 0
                for row in reader:
                    if len(row) <= max(query_idx, tool_idx):
                        continue
                        
                    csv_q_raw = row[query_idx]
                    csv_tool_raw = row[tool_idx]
                    
                    # 清洗 CSV 问题以匹配 TXT
                    # 这里的逻辑需要和 sort 脚本保持一致，或者更简单地，我们假设 CSV 已经是 sort 好的，
                    # 或者我们只是通过内容匹配
                    
                    # 尝试匹配黄金链
                    # 策略：直接用清洗后的问题去 gold_map 查
                    # 1. 去掉可能的序号
                    csv_q_clean = re.sub(r'^\d+\.\s*', '', csv_q_raw).strip()
                    # 2. 尝试匹配
                    gold_chain = gold_map.get(csv_q_clean)
                    
                    # 如果没匹配到，尝试模糊匹配（或者忽略）
                    if not gold_chain:
                        # 简单的包含尝试
                        for k, v in gold_map.items():
                            if csv_q_clean in k or k in csv_q_clean:
                                gold_chain = v
                                break
                    
                    if not gold_chain:
                        # print(f"跳过: 未找到黄金链 - {csv_q_clean[:10]}...")
                        continue
                        
                    processed_count += 1
                    
                    # 转换 CSV 工具链
                    actual_chain = convert_csv_tool_chain(csv_tool_raw)
                    
                    # 计算长度 (SH 算1个，其他算1个)
                    # 我们的代号里 SH 是两个字符，其他是一个字符
                    # 但在计算“个数”时，SH 应该看作一个整体单元
                    # 分母：csv tool 列转换后的格式（actual_chain） -> 这里的描述有点歧义
                    # 用户说：“分母是csv中的tool列（转换成黄金工具链中的格式），分子是黄金工具链”
                    # 通常准确率 = 匹配数 / 总数。
                    # 如果“分母是csv...”，那意思是：实际生成的工具链中有多少是符合黄金标准的？(Precision?)
                    # 还是说：黄金标准中有多少被实际生成了？(Recall?)
                    # 用户原文：“用于匹配csv(tool列)和txt相同问题的黄金工具链之比，分母是csv中的tool列（转换成黄金工具链中的格式），分子是黄金工具链”
                    # 这句话有点绕。“分子是黄金工具链”通常意味着基准是黄金链？
                    # 但“分母是csv”意味着基准是实际输出？
                    # 让我们重新解读：“比率 = 黄金 / CSV”？这不太像准确率。
                    # 准确率通常是 Correct / Total。
                    # 结合上下文“计算 工具调用准确率”，最合理的解释是：
                    # 比较两个链，计算一致性。
                    # 让我们假设用户的意思是：
                    # 准确率 = (实际链 与 黄金链 匹配的步骤数) / (实际链的总步骤数 或 黄金链的总步骤数)
                    # 让我们再看一眼：“分母是csv中的tool列... 分子是黄金工具链”
                    # 这可能是指： Ratio = Length(Gold) / Length(CSV) ??? 不太可能。
                    # 或者： Ratio = Match(Gold, CSV) / Length(CSV) ? (Precision)
                    
                    # 让我们采用最通用的 Levenshtein Distance 或者最长公共子序列 (LCS) 及其变体？
                    # 或者简单的：如果完全一样就是 100%？
                    # 考虑到用户提到“单位是个数，小写的占一位，SH占一位”，这暗示我们要计算“数量”。
                    
                    # 让我们解析链为 token 列表
                    def tokenize_chain(chain_str):
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
                    
                    gold_tokens = tokenize_chain(gold_chain)
                    actual_tokens = tokenize_chain(actual_chain)
                    
                    # 计算匹配度
                    # 既然是工具链，顺序很重要。
                    # 这里我们计算 Levenshtein Distance (编辑距离) 转换成的相似度？
                    # 或者简单的：相同位置相同元素的个数？
                    # 或者 LCS (最长公共子序列)？
                    
                    # 如果用户想要“准确率”，通常指：生成的链条是否正确。
                    # 如果完全匹配，准确率为1。
                    # 如果错了一个步骤，准确率降低。
                    
                    # 让我们再次阅读：“分母是csv中的tool列（转换成黄金工具链中的格式），分子是黄金工具链”
                    # 这句话可能在定义公式： Score = Count(Gold) / Count(CSV) ？？
                    # 如果我生成了 extra steps，分母变大，分数变低。
                    # 如果我少生成了，分母变小，分数变高？这不合理。
                    
                    # 也许用户的意思是：
                    # 分母 = max(len(gold), len(actual))
                    # 分子 = 匹配的个数
                    
                    # 或者，用户只是想统计：
                    # 总共有多少个步骤是“黄金标准”的。
                    
                    # 让我们做一个最合理的假设：
                    # 计算两个序列的相似度。使用 SequenceMatcher.ratio()
                    # 或者：
                    # 准确率 = (LCS 长度) / (max(len(gold), len(actual)))
                    
                    # 但根据用户的具体描述：“分母是csv... 分子是黄金...”
                    # 也许他想算的是 Recall = (匹配数) / (黄金总数)
                    # 或者 Precision = (匹配数) / (实际总数)
                    
                    # 让我们暂且计算由 difflib.SequenceMatcher 计算出的相似度，
                    # 并在日志中列出详细对比，供用户参考。
                    # 同时计算 tokens 的数量。
                    
                    # 修正理解：
                    # “分母是csv中的tool列（转换成黄金工具链中的格式）” -> 意味着分母是 Actual Chain Length
                    # “分子是黄金工具链” -> 这句话依然很怪。分子通常是“匹配的部分”。
                    # 如果分子直接是“黄金工具链长度”，那公式就是 Len(Gold)/Len(Actual)。
                    # 如果实际链很长（冗余），比值 < 1。
                    # 如果实际链很短（缺失），比值 > 1。
                    # 这更像是“长度比”。
                    
                    # 另一种可能：用户写反了？或者省略了“匹配的”三个字？
                    # “分子是[和]黄金工具链[匹配的部分]”
                    
                    # 让我们提供两个指标：
                    # 1. 完全匹配率 (Exact Match Accuracy): 两个链完全一样的比例。
                    # 2. 步骤覆盖率/相似度 (Step Similarity): 基于 LCS。
                    
                    from difflib import SequenceMatcher
                    matcher = SequenceMatcher(None, gold_tokens, actual_tokens)
                    similarity = matcher.ratio() # 2*M / (T1 + T2)
                    
                    # 还有一种解释：
                    # 用户想要的是 Token 级别的 Precision?
                    # 分母 = len(actual_tokens)
                    # 分子 = len(LCS(gold, actual))  (即实际生成的链中有多少是属于黄金链的有效步骤)
                    
                    # 让我们采用 LCS / len(actual) 作为“准确率”的一个定义 (Precision)
                    # 同时提供 LCS / len(gold) (Recall)
                    
                    # 计算 LCS
                    m, n = len(gold_tokens), len(actual_tokens)
                    dp = [[0] * (n + 1) for _ in range(m + 1)]
                    for i in range(1, m + 1):
                        for j in range(1, n + 1):
                            if gold_tokens[i-1] == actual_tokens[j-1]:
                                dp[i][j] = dp[i-1][j-1] + 1
                            else:
                                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                    lcs_len = dp[m][n]
                    
                    # 按照用户字面意思尝试：
                    # 分母 = len(actual_tokens)
                    # 分子 = len(gold_tokens) ??? -> 这只是长度比。
                    # 猜测用户意图：
                    # 可能是想看 实际生成的步骤里，有多少是对的。
                    # 所以分子应该是 lcs_len。
                    
                    # 让我们输出：
                    # 1. 黄金链 (长度)
                    # 2. 实际链 (长度)
                    # 3. 匹配长度 (LCS)
                    # 4. 准确率 (LCS / Actual)
                    
                    csv_len = len(actual_tokens)
                    gold_len = len(gold_tokens)
                    
                    # 避免除以零
                    acc = 0
                    if csv_len > 0:
                        acc = lcs_len / csv_len
                    
                    diff_records.append({
                        'q': csv_q_clean,
                        'gold': "".join(gold_tokens),
                        'actual': "".join(actual_tokens),
                        'gold_len': gold_len,
                        'actual_len': csv_len,
                        'lcs': lcs_len,
                        'acc': acc
                    })
                    
            except Exception as e:
                print(f"解析CSV行失败: {e}")
                return

    except Exception as e:
        print(f"打开CSV失败: {e}")
        return

    # 4. 汇总输出
    print(f"\n成功匹配并分析了 {len(diff_records)} 个问题。\n")
    
    # 计算平均指标
    avg_acc = sum(r['acc'] for r in diff_records) / len(diff_records) if diff_records else 0
    total_lcs = sum(r['lcs'] for r in diff_records)
    total_actual_len = sum(r['actual_len'] for r in diff_records)
    global_acc = total_lcs / total_actual_len if total_actual_len > 0 else 0
    
    print(f"=== 统计结果 ===")
    print(f"平均单题准确率 (LCS / Actual): {avg_acc:.2%}")
    print(f"全局准确率 (Total LCS / Total Actual Steps): {global_acc:.2%}")
    
    print(f"\n=== 详细差异 (前20条) ===")
    print(f"{'问题':<20} | {'黄金链':<10} | {'实际链':<10} | {'准确率'}")
    print("-" * 60)
    for r in diff_records[:20]:
        q_display = r['q'][:18] + ".." if len(r['q']) > 18 else r['q']
        print(f"{q_display:<20} | {r['gold']:<10} | {r['actual']:<10} | {r['acc']:.2%}")
        
    # 保存详细报告
    report_path = os.path.join(os.path.dirname(csv_path), "accuracy_report.csv")
    try:
        with open(report_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Question', 'Gold_Chain', 'Actual_Chain', 'Gold_Len', 'Actual_Len', 'Matched_Len', 'Accuracy'])
            for r in diff_records:
                writer.writerow([r['q'], r['gold'], r['actual'], r['gold_len'], r['actual_len'], r['lcs'], f"{r['acc']:.4f}"])
        print(f"\n详细报告已保存至: {report_path}")
    except Exception as e:
        print(f"保存报告失败: {e}")

if __name__ == "__main__":
    main()
