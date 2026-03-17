import requests
import json
import time
import os
import re
from datetime import datetime

import csv

# 配置信息
# Dify API Base URL
API_BASE_URL = ""
API_KEY = ""

# 默认查询目录
TXT_QUERY_DIR = r"f:\geroserverFabu\txtquery"
# 代码输出基础目录
BASE_OUTPUT_DIR = r"f:\geroserverFabu\code"
LOG_FILE = r"f:\geroserverFabu\batch_run.log"

def log_message(message):
    """记录日志到控制台和文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_str = f"[{timestamp}] {message}"
    print(log_str)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_str + "\n")
    except Exception as e:
        print(f"写日志文件失败: {e}")

def send_message_streaming(query):
    """发送消息到Dify API (Streaming模式)"""
    url = f"{API_BASE_URL}/chat-messages"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    # Agent Chat App 必须使用 streaming 模式
    payload = {
        "inputs": {},
        "query": query,
        "response_mode": "streaming", 
        "user": "batch-code-generator",
        "conversation_id": "" 
    }
    
    full_answer = ""
    usage_info = {}
    
    try:
        with requests.post(url, headers=headers, json=payload, stream=True) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        json_str = decoded_line[6:] # 去掉 'data: ' 前缀
                        try:
                            data = json.loads(json_str)
                            event = data.get('event')
                            
                            # 处理不同类型的事件
                            if event in ['message', 'agent_message']:
                                # 拼接回答内容
                                answer_chunk = data.get('answer', '')
                                if answer_chunk:
                                    full_answer += answer_chunk
                                    # print(answer_chunk, end="", flush=True) # 可选：实时打印
                            
                            elif event == 'message_end':
                                # 消息结束，提取 usage
                                metadata = data.get('metadata', {})
                                usage_info = metadata.get('usage', {})
                                
                            elif event == 'error':
                                error_msg = data.get('message', 'Unknown error')
                                log_message(f"Stream error: {error_msg}")
                                return None, None
                                
                        except json.JSONDecodeError:
                            continue
                            
        return full_answer, usage_info

    except requests.exceptions.RequestException as e:
        log_message(f"API请求出错: {e}")
        try:
            if e.response is not None:
                log_message(f"服务器返回详情: {e.response.text}")
        except:
            pass
        return None, None

def select_input_file():
    """让用户选择输入文件"""
    if not os.path.exists(TXT_QUERY_DIR):
        log_message(f"错误：目录不存在 {TXT_QUERY_DIR}")
        return None

    files = [f for f in os.listdir(TXT_QUERY_DIR) if f.endswith('.txt')]
    if not files:
        log_message(f"错误：在 {TXT_QUERY_DIR} 下没有找到 .txt 文件")
        return None

    print(f"\n在 {TXT_QUERY_DIR} 发现以下文件:")
    for i, f in enumerate(files):
        print(f"{i + 1}. {f}")
    print("-" * 30)

    while True:
        try:
            choice = input("请选择要处理的文件序号 (输入 q 退出): ").strip()
            if choice.lower() == 'q':
                return None
            
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                selected_file = os.path.join(TXT_QUERY_DIR, files[idx])
                log_message(f"已选择文件: {files[idx]}")
                return selected_file
            else:
                print("序号无效，请重新输入")
        except ValueError:
            print("请输入有效的数字")

def sanitize_filename(name):
    """清理文件名，移除非法字符"""
    # 移除非法字符
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # 替换换行符等为空格
    name = re.sub(r'\s+', " ", name)
    # 限制长度
    return name[:100].strip()

def extract_code(text):
    """从回答中优先提取HTML代码块"""
    # 1. 尝试匹配 ```html ... ``` (最优先)
    pattern_html = r"```html\s+(.*?)```"
    matches = re.findall(pattern_html, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return "\n\n".join(matches), "html"

    # 2. 尝试匹配无语言标识的代码块，但内容像 HTML
    pattern_any = r"```(\w*)\s+(.*?)```"
    matches_any = re.findall(pattern_any, text, re.DOTALL)
    potential_html = []
    for lang, content in matches_any:
        # 如果标记为 html (虽然上面已经匹配过了，防万一) 或内容像 HTML
        if lang.lower() == 'html' or "<html" in content.lower() or "<!doctype" in content.lower() or "<div" in content.lower():
            potential_html.append(content)
    
    if potential_html:
        return "\n\n".join(potential_html), "html"

    # 3. 如果没有代码块，检查全文是否包含 HTML 特征 (例如直接返回了HTML)
    if "<html" in text.lower() or "<!doctype html" in text.lower():
        return text, "html"

    # 4. 如果都找不到，返回空，表示没找到HTML
    return "", None

def get_file_extension(language):
    """根据语言返回对应的文件后缀"""
    # 强制默认为 .html，或者根据提取结果
    if language == 'html':
        return ".html"
    return ".html" # 用户要求只要保留html，所以默认后缀改为html，或者如果没提取到代码就存为空html

def append_to_csv(data, csv_file_path):
    """追加记录到CSV文件"""
    file_exists = os.path.exists(csv_file_path)
    try:
        with open(csv_file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Question", "Duration(s)", "Total Tokens", "Output File"])
            writer.writerow(data)
    except Exception as e:
        log_message(f"写CSV失败: {e}")


def main():
    log_message("=== 开始批量生成代码任务 ===")
    
    # 确保基础输出目录存在
    if not os.path.exists(BASE_OUTPUT_DIR):
        os.makedirs(BASE_OUTPUT_DIR)
        
    # 1. 交互式选择运行轮数
    run_count = 1
    while True:
        try:
            user_input = input("请输入要运行的轮数 (默认 1): ").strip()
            if not user_input:
                break
            count = int(user_input)
            if count > 0:
                run_count = count
                break
            print("请输入大于 0 的整数")
        except ValueError:
            print("请输入有效的整数")

    log_message(f"计划执行 {run_count} 轮任务。")

    # 2. 选择输入文件 (只选择一次)
    input_file_path = select_input_file()
    if not input_file_path:
        log_message("未选择文件或退出任务。")
        return

    # 读取所有问题
    questions = []
    try:
        with open(input_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 只处理以数字加点开头的行
                match = re.match(r'^(\d+)\.(.*)', line)
                if match:
                    # 提取序号后的内容
                    content = match.group(2)
                    
                    # 过滤括号及里面的内容（中英文）
                    if '（' in content:
                        content = content.split('（')[0]
                    if '(' in content:
                        content = content.split('(')[0]
                    
                    content = content.strip()

                    if content:
                        questions.append(content)
    except Exception as e:
        log_message(f"读取输入文件失败: {e}")
        return
    
    log_message(f"共加载 {len(questions)} 个问题。")

    # 3. 交互式选择起始序号 (只选择一次)
    start_index = 1
    if len(questions) > 0:
        try:
            user_input = input(f"请输入起始序号 (默认 1, 最大 {len(questions)}): ").strip()
            if user_input:
                start_index = int(user_input)
        except ValueError:
            print("输入无效，将从第 1 个问题开始。")
    
    log_message(f"将从第 {start_index} 个问题开始执行。")

    # 4. 循环执行任务
    for round_idx in range(1, run_count + 1):
        log_message(f"\n=== 正在开始第 {round_idx}/{run_count} 轮任务 ===")
        
        # 查找下一个可用的编号目录
        run_id = 1
        while True:
            current_output_dir = os.path.join(BASE_OUTPUT_DIR, str(run_id))
            if not os.path.exists(current_output_dir):
                break
            run_id += 1
        
        # 创建本次运行的目录
        os.makedirs(current_output_dir)
        log_message(f"创建本次运行输出目录: {current_output_dir}")
        
        # 定义本次运行的CSV文件路径
        current_csv_file = os.path.join(current_output_dir, "batch_run_stats.csv")

        # 依次处理问题
        for index, question in enumerate(questions):
            current_num = index + 1
            if current_num < start_index:
                continue

            log_message(f"[{round_idx}/{run_count}] 正在处理第 {current_num}/{len(questions)} 个问题: {question}")
            
            start_time = time.time()
            start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            answer, usage = send_message_streaming(question)
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration = end_time - start_time
            
            if answer:
                # 提取代码
                code_content, language = extract_code(answer)
                
                # 生成文件名
                safe_name = sanitize_filename(question)
                if not safe_name:
                    safe_name = f"question_{current_num}"
                
                # 获取后缀
                ext = get_file_extension(language)
                file_name = f"{safe_name}{ext}"
                file_path = os.path.join(current_output_dir, file_name)
                
                # 准备 Token 信息
                if usage is None:
                    usage = {}
                total_tokens = usage.get('total_tokens', 0)
                
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        # 对于非Python文件，注释风格可能不同，这里简单处理，尽量使用通用注释或不加头部注释
                        # 为了保持兼容性，还是加上，但如果不是py文件，可能需要调整注释符号
                        # 简单起见，如果不是py，我们用 python 风格注释写在最前面，用户自己处理，或者根据后缀判断
                        
                        comment_prefix = "#"
                        if ext in ['.c', '.cpp', '.java', '.js', '.ts', '.cs', '.css', '.php', '.swift', '.kt', '.scala', '.go', '.rs']:
                            comment_prefix = "//"
                        elif ext in ['.sql', '.lua']:
                            comment_prefix = "--"
                        elif ext in ['.html', '.xml', '.md']:
                            comment_prefix = "<!--" # HTML注释比较特殊，可能需要闭合，这里暂简化处理或仅针对支持行注释的语言
                        
                        # 对于不支持单行注释的（如HTML），写头部信息可能会破坏文件结构，
                        # 策略：如果是已知支持 // 或 # 的语言，写入头部信息；否则不写入或写在末尾？
                        # 也就是保持原逻辑，但适配注释符。
                        
                        # 针对HTML/XML/Markdown等特殊情况，暂时不写头部Metadata，或者仅在Log/CSV中记录
                        # 用户要求"什么类型的代码就什么格式"，为了不破坏代码（比如JSON），最好只针对编程语言加注释
                        
                        is_script_lang = ext in ['.py', '.sh', '.pl', '.rb', '.r', '.m', '.ps1'] or comment_prefix in ['//', '--']
                        
                        if is_script_lang:
                             f.write(f"{comment_prefix} Question: {question}\n")
                             f.write(f"{comment_prefix} Start Time: {start_time_str}\n")
                             f.write(f"{comment_prefix} End Time: {end_time_str}\n")
                             f.write(f"{comment_prefix} Duration: {duration:.2f}s\n")
                             f.write("\n")
                        
                        f.write(code_content)
                        
                        if not is_script_lang:
                            # 对于json, html等，不写头部注释，以免破坏格式
                            pass
                    
                    log_message(f"已保存代码至: {file_path}")
                    
                    # 记录到CSV
                    append_to_csv([question, f"{duration:.2f}", total_tokens, file_name], current_csv_file)
                    
                except Exception as e:
                    log_message(f"保存文件失败: {e}")
                
            else:
                log_message("失败：未获取到有效回答")
            
            # 避免请求过于频繁，稍微等待
            time.sleep(1)

    log_message("=== 所有轮次任务结束 ===")

if __name__ == "__main__":
    main()
