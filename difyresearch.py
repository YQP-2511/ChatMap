import requests
import json
import time
import os
import re
import csv
from datetime import datetime

# 配置信息
# Dify API Base URL
API_BASE_URL = ""

# 模型配置
MODELS = {
    "deepseek": {"name": "DeepSeek (Chat 3.2)", "api_key": ""},
    "qwen": {"name": "千问 (Qwen)", "api_key": ""},
    "glm4": {"name": "GLM4.5", "api_key": ""}
}
# 默认 API KEY (会被 main 函数中的选择覆盖)
API_KEY = MODELS["deepseek"]["api_key"]
# 默认查询目录
TXT_QUERY_DIR = r"f:\geroserverFabu\txtquery"
# 默认文本输出目录 (修改为 logs 目录)
OUTPUT_DIR = r"f:\geroserverFabu\logs"
# CSV 输出目录
CSV_OUTPUT_DIR = r"f:\geroserverFabu\csv"
# 日志目录
LOG_DIR = r"f:\geroserverFabu\logs\difylogs"
# 请求超时配置 (连接超时, 读取超时)
# 调整为 300 秒 (5分钟)，避免服务端无响应时无限等待
REQUEST_TIMEOUT = (10, 300)
# 重试次数
MAX_RETRIES = 3

# 确保日志目录存在
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 动态生成日志文件名
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_DIR, f"dify_run_{timestamp_str}.log")

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

def send_message_streaming(question):
    url = f"{API_BASE_URL}/chat-messages"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": {},
        "query": question,
        "response_mode": "streaming", 
        "user": "research-user-001",
        "conversation_id": "" 
    }
    
    for attempt in range(MAX_RETRIES):
        full_answer = ""
        usage_info = {}
        # 用于去重和整合工具调用信息的临时存储
        thought_steps = {} # id -> {tool, input, observation}
        step_order = []    # 记录 ID 出现顺序
        
        try:
            with requests.post(url, headers=headers, json=payload, stream=True, timeout=REQUEST_TIMEOUT) as response:
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
                                
                                elif event == 'agent_thought':
                                    # 使用 ID 进行聚合去重
                                    step_id = data.get('id')
                                    if not step_id:
                                        continue
                                        
                                    if step_id not in thought_steps:
                                        thought_steps[step_id] = {
                                            "tool": "",
                                            "input": None,
                                            "observation": None
                                        }
                                        step_order.append(step_id)
                                    
                                    # 更新字段 (优先保留非空值，或覆盖)
                                    if data.get('tool'):
                                        thought_steps[step_id]['tool'] = data.get('tool')
                                    if data.get('tool_input'):
                                        thought_steps[step_id]['input'] = data.get('tool_input')
                                    if data.get('observation'):
                                        thought_steps[step_id]['observation'] = data.get('observation')

                                elif event == 'message_end':
                                    # 消息结束，提取 usage
                                    metadata = data.get('metadata', {})
                                    usage_info = metadata.get('usage', {})
                                    
                                elif event == 'error':
                                    error_msg = data.get('message', 'Unknown error')
                                    log_message(f"Stream error: {error_msg}")
                                    return None, None, None
                                    
                            except json.JSONDecodeError:
                                continue
            
            # 流结束后，处理 thought_steps 生成 tool_info
            tool_info = {
                "tools": [],
                "layers": [],
                "urls": []
            }
            
            for step_id in step_order:
                step = thought_steps[step_id]
                tool_name = step['tool']
                
                # 只有当确实有工具名时才记录
                if tool_name:
                    tool_info['tools'].append(tool_name)
                    
                    if tool_name == 'show_layer_on_map':
                        # 提取 layer (name)
                        try:
                            # 优先使用累积到的 input
                            tool_input_raw = step['input']
                            tool_input = {}
                            
                            if isinstance(tool_input_raw, str):
                                try:
                                    tool_input = json.loads(tool_input_raw)
                                except:
                                    pass
                            elif isinstance(tool_input_raw, dict):
                                tool_input = tool_input_raw
                            
                            # 输入结构通常是 {"show_layer_on_map": {"name": "..."}}
                            layer_name = None
                            if 'show_layer_on_map' in tool_input:
                                layer_name = tool_input['show_layer_on_map'].get('name')
                            elif 'name' in tool_input:
                                layer_name = tool_input.get('name')
                            
                            if layer_name:
                                tool_info['layers'].append(layer_name)
                        except Exception:
                            pass

                        # 提取 URL
                        try:
                            observation_str = step['observation']
                            if observation_str:
                                # 尝试先解析为 JSON，因为 observation 通常是 {"show_layer_on_map": "..."}
                                # 这样可以去掉外层转义，得到内层干净的字符串
                                found_url = False
                                try:
                                    obs_data = json.loads(observation_str)
                                    if isinstance(obs_data, dict):
                                        # 遍历所有值查找 URL (通常在 show_layer_on_map 对应的值中)
                                        for val in obs_data.values():
                                            if isinstance(val, str):
                                                # 在内层字符串中查找 "url": "..."
                                                url_match = re.search(r'"url":\s*"([^"]+)"', val)
                                                if url_match:
                                                    tool_info['urls'].append(url_match.group(1))
                                                    found_url = True
                                                    break
                                except:
                                    pass

                                # 如果 JSON 解析失败或没找到，尝试在原始字符串中直接正则匹配
                                # 兼容转义引号 \"url\": \"...\"
                                if not found_url:
                                    # 匹配 "url": "..." 或 \"url\": \"...\"
                                    # 注意：(?:\\)? 匹配可选的反斜杠
                                    url_match = re.search(r'(?:\\)?"url(?:\\)?"\s*:\s*(?:\\)?"([^"]+?)(?:\\)?"', observation_str)
                                    if url_match:
                                        url = url_match.group(1)
                                        # 如果匹配到了末尾的反斜杠（因为 [^"] 包含 \），去掉它
                                        if url.endswith('\\'):
                                            url = url[:-1]
                                        tool_info['urls'].append(url)
                        except Exception:
                            pass
                                
            return full_answer, usage_info, tool_info

        except requests.exceptions.RequestException as e:
            log_message(f"API请求出错 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2) # 重试前等待
            else:
                # 最后一次尝试失败，尝试读取响应内容以便调试
                try:
                    if e.response is not None:
                        log_message(f"服务器返回详情: {e.response.text}")
                except:
                    pass
                return None, None, None
        except Exception as e:
            log_message(f"发生未知错误: {e}")
            return None, None, None

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

def get_last_processed_index(csv_path):
    """从 CSV 文件中获取最后处理的序号"""
    if not os.path.exists(csv_path):
        return 0
    
    last_index = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # 跳过 header
            next(reader, None)
            for row in reader:
                if row and row[0].isdigit():
                    last_index = int(row[0])
    except Exception as e:
        log_message(f"读取 CSV 进度失败: {e}")
    
    return last_index

def check_and_prepare_csv(csv_path):
    """检查 CSV 文件格式，如果 Header 不匹配则备份并重建"""
    expected_header = ["序号", "问题", "耗时(s)", "Total Tokens", "工具链", "图层", "URL"]
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                
            if header != expected_header:
                # 备份旧文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{os.path.splitext(csv_path)[0]}_backup_{timestamp}.csv"
                try:
                    os.rename(csv_path, backup_path)
                    log_message(f"检测到旧 CSV 格式，已备份至: {backup_path}")
                except OSError as e:
                    log_message(f"备份旧文件失败: {e}")
                    # 如果无法重命名，尝试直接覆盖（风险较高，但这是为了保证后续运行正确）
                    pass
        except Exception as e:
            log_message(f"检查 CSV 文件失败: {e}")

    # 初始化新文件（如果文件不存在或已被移走）
    if not os.path.exists(csv_path):
        try:
            with open(csv_path, "w", encoding="utf-8", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(expected_header)
            log_message(f"已创建新的结果文件: {csv_path}")
        except Exception as e:
            log_message(f"初始化 CSV 文件失败: {e}")

def process_batch_run(run_idx, questions, output_file_path_txt, output_file_path_csv, auto_resume=True):
    """处理单个批次运行"""
    log_message(f"=== 开始第 {run_idx} 轮运行 ===")
    log_message(f"文本结果: {output_file_path_txt}")
    log_message(f"CSV 结果: {output_file_path_csv}")

    # 准备 CSV 文件（检查格式并初始化）
    check_and_prepare_csv(output_file_path_csv)

    # 检查 CSV 断点
    last_processed_index = get_last_processed_index(output_file_path_csv)
    default_start_index = last_processed_index + 1
    
    start_index = default_start_index
    if not auto_resume:
        # 非自动模式下，允许用户调整起始序号
        if last_processed_index > 0:
            log_message(f"检测到历史进度，已完成 {last_processed_index} 个问题。")
        
        if len(questions) > 0:
            try:
                prompt = f"请输入起始序号 (默认 {default_start_index}, 最大 {len(questions)}): "
                user_input = input(prompt).strip()
                if user_input:
                    start_index = int(user_input)
            except ValueError:
                print(f"输入无效，将从第 {default_start_index} 个问题开始。")
    else:
        log_message(f"自动从第 {start_index} 个问题开始（接续历史进度）。")
    
    log_message(f"将从第 {start_index} 个问题开始执行。")

    # 准备写入结果文件头部（文本文件）
    if not os.path.exists(output_file_path_txt):
        with open(output_file_path_txt, "w", encoding="utf-8") as f:
            f.write(f"=== 实验结果 (Run {run_idx}) ===\n\n")

    # 依次处理问题
    for index, question in enumerate(questions):
        current_num = index + 1
        if current_num < start_index:
            continue

        log_message(f"[Run {run_idx}] 正在处理第 {current_num}/{len(questions)} 个问题: {question}")
        
        start_time = time.time()
        answer, usage, tool_info = send_message_streaming(question)
        end_time = time.time()
        duration = end_time - start_time
        
        # 提取 token usage
        total_tokens = 0
        if usage:
            total_tokens = usage.get('total_tokens', 0)
            
        # 准备工具链、图层、URL 信息
        tools_str = ""
        layers_str = ""
        urls_str = ""
        
        if tool_info:
            # 去重并转为字符串，或者直接连接
            # 用户要求：多个用逗号隔开
            tools_str = ",".join(tool_info.get("tools", []))
            layers_str = ",".join(tool_info.get("layers", []))
            urls_str = ",".join(tool_info.get("urls", []))
        
        if answer:
            # 1. 写入文本文件 (保持原有格式)
            output_text = (
                f"问题 [{current_num}]: {question}\n"
                f"耗时: {duration:.2f}秒\n"
                f"回答: {answer}\n"
                f"Token消耗: {usage}\n"
                f"工具链: {tools_str}\n"
                f"图层: {layers_str}\n"
                f"URL: {urls_str}\n"
                f"{'-'*50}\n"
            )
            
            try:
                with open(output_file_path_txt, "a", encoding="utf-8") as f:
                    f.write(output_text)
            except Exception as e:
                log_message(f"写入文本结果文件失败: {e}")

            # 2. 写入 CSV 文件 (简化版：序号, 问题, 耗时(s), Total Tokens, 工具链, 图层, URL)
            try:
                with open(output_file_path_csv, "a", encoding="utf-8", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([current_num, question, round(duration, 2), total_tokens, tools_str, layers_str, urls_str])
            except Exception as e:
                log_message(f"写入 CSV 结果文件失败: {e}")
            
            log_message(f"完成。耗时: {duration:.2f}s, Tokens: {total_tokens}, Tools: {tools_str}")
        else:
            log_message("失败：未获取到有效回答")
            # 失败也要记录到文本
            try:
                with open(output_file_path_txt, "a", encoding="utf-8") as f:
                    f.write(f"问题 [{current_num}]: {question}\n状态: 失败\n{'-'*50}\n")
            except:
                pass
            
            # 失败记录到 CSV
            try:
                with open(output_file_path_csv, "a", encoding="utf-8", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([current_num, question, round(duration, 2), 0, tools_str, layers_str, urls_str])
            except Exception as e:
                log_message(f"写入 CSV 结果文件失败: {e}")
        
        # 避免请求过于频繁，稍微等待
        time.sleep(1)

def main():
    log_message("=== 开始实验任务 (Streaming Mode) ===")
    log_message(f"日志文件: {LOG_FILE}")
    
    # 选择输入文件
    input_file_path = select_input_file()
    if not input_file_path:
        log_message("未选择文件或退出任务。")
        return

    # 根据输入文件名生成输出文件名
    input_filename = os.path.basename(input_file_path)
    
    # 读取所有问题
    questions = []
    try:
        with open(input_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 只处理以数字加点开头的行，例如 "1.展示全球湖泊..."
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
    
    # 询问运行次数
    run_count = 1
    try:
        count_input = input("请输入批量运行次数 (默认为 1): ").strip()
        if count_input:
            run_count = int(count_input)
            if run_count < 1:
                run_count = 1
    except ValueError:
        print("输入无效，默认为 1 次。")
    
    # 选择模型
    print("\n请选择要使用的模型:")
    model_keys = list(MODELS.keys())
    for i, key in enumerate(model_keys):
        print(f"{i + 1}. {MODELS[key]['name']}")
    
    selected_model_key = "deepseek" # 默认
    while True:
        try:
            choice = input(f"请输入序号 (默认 1 - DeepSeek): ").strip()
            if not choice:
                break
            
            idx = int(choice) - 1
            if 0 <= idx < len(model_keys):
                selected_model_key = model_keys[idx]
                break
            else:
                print("序号无效，请重新输入")
        except ValueError:
            print("请输入有效的数字")
            
    # 更新全局 API KEY
    global API_KEY
    API_KEY = MODELS[selected_model_key]["api_key"]
    model_name_safe = selected_model_key
    log_message(f"已选择模型: {MODELS[selected_model_key]['name']} (Key: ...{API_KEY[-4:]})")

    # 确保 CSV 目录存在
    if not os.path.exists(CSV_OUTPUT_DIR):
        os.makedirs(CSV_OUTPUT_DIR)
        
    for i in range(run_count):
        run_idx = i + 1
        
        # 确定文件名
        # 命名格式：dify_{模型名}_run{序号}_{输入文件名}.csv
        
        base_name_no_ext = os.path.splitext(input_filename)[0]
        suffix = f"_run{run_idx}"
        
        # 为了兼容之前的习惯，如果只跑一次且默认模型，也许不需要太复杂？
        # 但用户要求明确命名，所以统一使用新格式
        
        output_filename_txt = f"dify_{model_name_safe}_experiment_results_{base_name_no_ext}{suffix}.txt"
        output_file_path_txt = os.path.join(OUTPUT_DIR, output_filename_txt)
        
        csv_filename = f"dify_{model_name_safe}_{base_name_no_ext}{suffix}.csv"
        output_file_path_csv = os.path.join(CSV_OUTPUT_DIR, csv_filename)
        
        # 自动恢复模式：如果是批量运行，默认自动接续，不暂停询问
        auto_resume = (run_count > 1)
        
        process_batch_run(run_idx, questions, output_file_path_txt, output_file_path_csv, auto_resume)

    log_message("=== 所有实验任务结束 ===")

if __name__ == "__main__":
    main()
