import requests
import json
import uuid
import os
import sys
import time
import re
import csv
from urllib.parse import unquote
from datetime import datetime

# --- Configuration ---
# cherrystudioAPI服务器key
API_KEY = ""
# cherrystudioAPI地址
BASE_URL = "http://localhost:23333/v1"
# cherryMCP服务器id
MCP_SERVER_ID = ""

# 路径配置
TXT_QUERY_DIR = r"f:\geroserverFabu\txtquery"
OUTPUT_DIR = r"f:\geroserverFabu\cherry-studio"
CSV_OUTPUT_DIR = r"f:\geroserverFabu\csv"
LOG_FILE = os.path.join(OUTPUT_DIR, "run.log")

SYSTEM_PROMPT = """# 图层可视化助手工作准则
## 根本原则
**过滤后的临时图层不支持字段和值的查看并且不能二次字段过滤（包含单图层空间过滤，但支持叠加过滤）**
## 基本原则
- 尊重客观事实，叠加分析显示0个结果属正常现象，不用增加缓冲区范围
- 输出链接使用超链接格式
- 未指定模式时，默认使用normal模式
- 过滤时，图层名不使用@
- 可视化图层工具只能使用一次

## 工作流程
### 第一步：查找图层
- 使用 `get_layers_for_ai_selection` 查看原始图层，分析用户的问题是否需要二、三步操作，如果不需要，可以直接跳到第四步。
### 第二步：过滤图层
- 1、使用 ` get_layer_schema` 查看原始图层的字段；
- 2、使用 ` get_field_values` 查看原始图层的**字段值**，输出部分参考值，辅助判断字段是否为用户需要的；

#### 情况A：存在空间关系，对单个原始非过滤图层进行空间过滤
- **过滤单图层存在空间关系的要素，某个图层中某个图形相邻和不相邻的情况**使用 `filter_features_to_temp_layer`，cql_filter格式：空间谓词(the_geom, querySingle('原始图层名不带符号', 'the_geom', '字段=''字段值'''))。支持的空间谓词：INTERSECTS、DISJOINT。比如查看A图层中某个地方相邻的地方，name:A；cql_filter格式：INTERSECTS(the_geom, querySingle('A', 'the_geom', '地方名=''某地'''))，其中的A是原始图层，只能对原始图层进行空间关系的过滤。
#### 情况B：单纯原始图层非过滤字段过滤
- 单图层字段过滤：优先使用 ` filter_features_to_temp_layer` 根据原始图层的字段和以及用户所需值设计过滤公式进行过滤。过滤器操作符：=, <>, >, <, >=, <=, BETWEEN, LIKE, IN, IS NULL, AND, OR, NOT。
#### 情况C：图层没有对应字段时对原始图层和过滤图层进行叠加过滤活得区域性图层
- 多图层过滤：**在图层没有对应字段时，根据需求选择原始图层或过滤后的图层进行过滤**，优先使用 `overlay_analysis_tool` 叠加过滤(支持intersection, union, difference, symmetric_difference)。比如过滤A国的湖泊，湖泊没有国家字段时，使用A国和湖泊进行叠加取交集得到结果；比如过滤A国的盐水湖，则使用3.1对湖泊进行过滤，得出盐水湖，再使用A国与盐水湖进行过滤得出结果。
### 第三步：处理图层
- 可选用 ` buffer_analysis` 对原始图层或过滤图层进行缓冲区创建。(单位是meters或kilometers)
- 可选用 ` overlay_analysis_tool` 对原始图层或过滤图层进行叠加分析(支持intersection, union, difference, symmetric_difference)。
- 可选用距离工具`calculate_layer_distance`：对原始图层或过滤图层进行距离计算，对单图层的各个要素距离的计算，要将各个要素都过滤出来，比如对A图层某字段的x、y、z三要素进行距离计算，要过滤出单独的x、y、z，再根据用户需求进行对应的距离计算。
- 可选用面积工具`calculate_layer_metrics`：对原始图层或过滤图层进行面积计算。
### 第四步：可视化图层
- **最终步骤，只运行一次，以上所有操作都要在可视化之前完成**，使用 `show_layer_on_map` 可视化主要图层（包括：**目标原始图层** - **最终过滤图层** - **缓冲区** - **处理后的图层，比如面积和距离等**，**图层之间用,隔开**）
"""

# --- Logging Helper ---

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
            # 确保目录存在
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            with open(csv_path, "w", encoding="utf-8", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(expected_header)
            log_message(f"已创建新的结果文件: {csv_path}")
        except Exception as e:
            log_message(f"初始化 CSV 文件失败: {e}")

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

# --- Classes (The 5 Endpoints/Entities) ---

class Error(Exception):
    """自定义 API 交互异常类"""
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"Error {code}: {message}")

class ChatMessage:
    """表示聊天中的消息结构"""
    def __init__(self, role, content, tool_calls=None, tool_call_id=None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id

    def to_dict(self):
        data = {"role": self.role}
        if self.content is not None:
            data["content"] = self.content
        elif self.role == "assistant" and self.tool_calls:
            # 对于包含工具调用的助手消息，内容可以是 null，但部分 API (如 Cherry Studio/Qwen) 校验要求 content 必须存在且为字符串
            # 因此这里强制使用空字符串而不是 None
            data["content"] = ""
        else:
            # 其他情况确保 content 至少是空字符串
            data["content"] = ""

        # 针对 Tool 消息的额外保护：如果 content 是空字符串，部分严格 API 可能也会报错
        # 尝试将其替换为 " " 或 JSON 空对象，视情况而定
        if self.role == "tool" and (data["content"] == "" or data["content"] is None):
             data["content"] = " " # 使用一个空格代替完全为空，规避 "content is required" 校验

        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        return data

class Model:
    """表示模型端点"""
    def __init__(self, model_id):
        self.id = model_id

    def check_availability(self):
        """检查模型是否可用"""
        url = f"{BASE_URL}/models"
        headers = {"Authorization": f"Bearer {API_KEY}"}
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                models = res.json().get("data", [])
                for m in models:
                    if m["id"] == self.id:
                        return True
            return False
        except Exception as e:
            log_message(f"模型检查失败: {e}")
            return False

class MCPServer:
    """表示 MCP 服务端点"""
    def __init__(self, server_id):
        self.id = server_id
        self.base_url = f"{BASE_URL}/mcps/{server_id}"
        self.rpc_url = f"{self.base_url}/mcp"
        self.headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session_id = None
        self.initialized = False

    def _update_session(self, response):
        """从响应中提取并更新 Session ID"""
        sid = response.headers.get("mcp-session-id")
        if sid and sid != self.session_id:
            self.session_id = sid
            self.session.headers.update({"mcp-session-id": sid})

    def _parse_sse_response(self, text):
        """解析 SSE 响应文本"""
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if "result" in data:
                        return data["result"]
                    if "error" in data:
                        return f"Error: {data['error']}"
                except json.JSONDecodeError:
                    continue
        return text

    def get_info(self):
        """获取服务器信息"""
        try:
            res = self.session.get(self.base_url)
            self._update_session(res)
            if res.status_code == 200:
                data = res.json()
                return data.get("data", {})
        except Exception as e:
            log_message(f"获取服务器信息失败: {e}")
        return {}

    def list_tools(self):
        """使用元数据端点获取工具列表"""
        disabled_tools = {
            "show_timeseries_map",
            "show_pollution_at_time",
            "register_external_function",
            "search_external_functions",
            "invoke_external_function",
            "register_ogc_service",
            "intersection_analysis",
            "get_semantic_cache_stats",
            "show_emission_at_time",
            "check_spatial_relation",
            "dissolve_analysis",
            "register_coordinate_temp_layer_by_address",
            "register_coordinate_temp_layer_by_coordinates",
            "show_emission_timeseries_map",
            "spatial_join",
            "calculate_feature_distance",
            "get_cached_visualization_url"
        }

        try:
            res = self.session.get(self.base_url)
            self._update_session(res)
            if res.status_code == 200:
                data = res.json()
                if "data" in data and "tools" in data["data"]:
                    all_tools = data["data"]["tools"]
                    active_tools = [t for t in all_tools if t['name'] not in disabled_tools]
                    log_message(f"MCP 服务共提供 {len(all_tools)} 个工具，根据配置已禁用 {len(all_tools) - len(active_tools)} 个。")
                    return active_tools
            log_message(f"从元数据获取工具失败: {res.status_code}")
            return []
        except Exception as e:
            log_message(f"获取工具列表异常: {e}")
            return []

    def _ensure_initialized(self):
        """确保 MCP 连接已初始化"""
        if self.initialized:
            return

        if not self.session_id:
            self.get_info()

        try:
            init_payload = {
                "jsonrpc": "2.0", 
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "batch-script", "version": "1.0"}}
            }
            r1 = self.session.post(self.rpc_url, json=init_payload)
            self._update_session(r1)
            
            self.session.post(self.rpc_url, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            
            self.initialized = True
        except Exception as e:
            log_message(f"MCP 初始化失败: {e}")

    def call_tool(self, name, arguments):
        """使用 JSON-RPC 执行工具"""
        self._ensure_initialized()
        
        call_payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }
        
        try:
            response = self.session.post(self.rpc_url, json=call_payload)
            self._update_session(response)
            
            if response.status_code == 200:
                # 强制使用 utf-8 解码，防止 requests 猜错编码导致乱码 (Mojibake)
                text = response.content.decode("utf-8")
                result = self._parse_sse_response(text)
                return result
            else:
                return f"Execution failed: {response.text}"
        except Exception as e:
            return f"RPC Call Error: {e}"

class ChatCompletionRequest:
    """表示聊天补全请求"""
    def __init__(self, model, messages, tools=None):
        self.model = model
        self.messages = messages
        self.tools = tools

    def execute(self):
        url = f"{BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model.id,
            "messages": [m.to_dict() for m in self.messages],
            "stream": True,
            "temperature": 0
        }
        
        if self.tools:
            openai_tools = []
            for t in self.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("inputSchema", {})
                    }
                })
            payload["tools"] = openai_tools

        try:
            response = requests.post(url, headers=headers, json=payload, stream=True)
            if response.status_code != 200:
                # 尝试解析错误信息，如果是 400 且包含 'content is required'，则记录警告并抛出
                error_body = response.text
                log_message(f"API Error ({response.status_code}): {error_body}")
                raise Error(response.status_code, error_body)
            
            # 流式响应处理与重组
            full_content = ""
            tool_calls_map = {} # {index: {"id": "", "name": "", "args": ""}}
            
            print(f"[{self.model.id}] ", end="", flush=True)
            
            # 初始化 usage 统计
            usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            
                            # 尝试从 chunk 中提取 usage 信息 (OpenAI 兼容接口通常在最后一个 chunk 或每个 chunk 包含)
                            if "usage" in chunk and chunk["usage"]:
                                usage_data = chunk["usage"]

                            if not chunk.get("choices"):
                                continue
                                
                            delta = chunk["choices"][0]["delta"]
                            
                            # 1. 处理内容流
                            content_chunk = delta.get("content")
                            if content_chunk:
                                full_content += content_chunk
                                print(content_chunk, end="", flush=True)
                                
                            # 2. 处理工具调用流
                            if delta.get("tool_calls"):
                                for tc in delta["tool_calls"]:
                                    idx = tc["index"]
                                    if idx not in tool_calls_map:
                                        tool_calls_map[idx] = {"id": "", "name": "", "args": ""}
                                    
                                    if tc.get("id"):
                                        tool_calls_map[idx]["id"] = tc["id"]
                                    if tc.get("function"):
                                        if tc["function"].get("name"):
                                            tool_calls_map[idx]["name"] = tc["function"]["name"]
                                        if tc["function"].get("arguments"):
                                            tool_calls_map[idx]["args"] += tc["function"]["arguments"]
                                            
                        except json.JSONDecodeError:
                            continue
            
            print("") # 换行
            
            # 重组为完整的响应对象，以兼容后续逻辑
            final_response = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": full_content if full_content else None
                    }
                }],
                "usage": usage_data 
            }
            
            # 如果有工具调用，添加到 message
            if tool_calls_map:
                tool_calls_list = []
                for idx in sorted(tool_calls_map.keys()):
                    tc_data = tool_calls_map[idx]
                    tool_calls_list.append({
                        "id": tc_data["id"],
                        "type": "function",
                        "function": {
                            "name": tc_data["name"],
                            "arguments": tc_data["args"]
                        }
                    })
                final_response["choices"][0]["message"]["tool_calls"] = tool_calls_list
                # 为了日志美观，如果是工具调用，打印一下提示
                if not full_content:
                    log_message(f"(工具调用: {[t['function']['name'] for t in tool_calls_list]})")

            return final_response

        except Exception as e:
            if isinstance(e, Error):
                raise e
            raise Error(-1, str(e))

# --- File Selection and Processing ---

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

# --- Main Logic ---

def process_batch_run(run_idx, questions, output_file_path, output_file_path_csv, model, mcp_server, tools, auto_resume=True):
    """处理单个批次运行"""
    log_message(f"=== 开始第 {run_idx} 轮运行 ===")
    log_message(f"文本结果: {output_file_path}")
    log_message(f"CSV 结果: {output_file_path_csv}")

    # 准备 CSV 文件
    check_and_prepare_csv(output_file_path_csv)

    # 5. 选择起始位置
    # 检查 CSV 断点
    last_processed_index = get_last_processed_index(output_file_path_csv)
    default_start_index = last_processed_index + 1
    
    start_index = default_start_index
    
    if auto_resume:
        log_message(f"自动从第 {start_index} 个问题开始（接续历史进度）。")
    else:
        if last_processed_index > 0:
            log_message(f"检测到历史进度，已完成 {last_processed_index} 个问题。")
        
        # 交互式选择起始序号
        if len(questions) > 0:
            try:
                prompt = f"请输入起始序号 (默认 {default_start_index}, 最大 {len(questions)}): "
                user_input = input(prompt).strip()
                if user_input:
                    start_index = int(user_input)
            except ValueError:
                print(f"输入无效，将从第 {default_start_index} 个问题开始。")
    
    log_message(f"将从第 {start_index} 个问题开始执行。")

    if not os.path.exists(output_file_path):
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(f"=== 实验结果 (Run {run_idx}) ===\n\n")

    # 6. 处理问题
    total_start_time = time.time()
    
    for index, q_text in enumerate(questions):
        current_num = index + 1
        if current_num < start_index:
            continue
            
        log_message(f"正在处理第 {current_num}/{len(questions)} 个问题: {q_text}")
        q_start_time = time.time()
        
        accumulated_tokens = 0 # 初始化 token 计数
        
        # 构建对话历史
        conversation = []
        if SYSTEM_PROMPT and SYSTEM_PROMPT.strip():
            conversation.append(ChatMessage("system", SYSTEM_PROMPT))
        conversation.append(ChatMessage("user", q_text))
        
        final_content = ""
        error_msg = None
        
        tools_used = []
        layers_shown = []
        urls_generated = []
        
        try:
            max_turns = 100
            turn = 0
            
            while turn < max_turns:
                turn += 1
                try:
                    req = ChatCompletionRequest(model, conversation, tools)
                    resp = req.execute()
                except Error as e:
                    # 尝试自动修复 400 content required 错误并重试
                    if e.code == 400 and "content is required" in str(e.message):
                         log_message(f"检测到 'content is required' 错误，尝试修复历史消息并重试...")
                         fixed = False
                         for msg in conversation:
                             if msg.role == "tool" and not msg.content:
                                 msg.content = " " # 修复空 tool content
                                 fixed = True
                             if msg.role == "assistant" and not msg.content:
                                 msg.content = " " # 修复空 assistant content (虽然 to_dict 已处理，但对象本身可能为 None)
                                 fixed = True
                         
                         if fixed:
                             log_message("已修复消息内容，重试请求...")
                             req = ChatCompletionRequest(model, conversation, tools)
                             resp = req.execute()
                         else:
                             raise e
                    else:
                        raise e

                # 累积 Token
                if isinstance(resp, dict) and 'usage' in resp:
                    accumulated_tokens += resp['usage'].get('total_tokens', 0)
                
                choice = resp['choices'][0]
                msg_data = choice['message']
                
                if msg_data.get("tool_calls"):
                    conversation.append(ChatMessage(
                        role="assistant", 
                        content=msg_data.get("content"),
                        tool_calls=msg_data.get("tool_calls")
                    ))
                    
                    for tc in msg_data['tool_calls']:
                        func_name = tc['function']['name']
                        try:
                            func_args = json.loads(tc['function']['arguments'])
                        except json.JSONDecodeError:
                            func_args = {}
                        call_id = tc['id']
                        
                        tools_used.append(func_name)
                        if func_name == "show_layer_on_map":
                            layer_name = func_args.get("name")
                            if layer_name:
                                layers_shown.append(unquote(layer_name))
                        
                        log_message(f"  -> [Turn {turn}] 调用工具: {func_name}")
                        
                        if mcp_server:
                            tool_res = mcp_server.call_tool(func_name, func_args)
                        else:
                            tool_res = f"Error: MCP server is not connected. Cannot execute tool '{func_name}'."
                        
                        # 简化日志输出
                        res_preview = str(tool_res)
                        if len(res_preview) > 100:
                            res_preview = res_preview[:100] + "..."
                        log_message(f"  <- 结果: {res_preview}")
                        
                        content_str = ""
                        if isinstance(tool_res, str):
                            content_str = tool_res
                        else:
                            if isinstance(tool_res, dict) and "content" in tool_res:
                                for c in tool_res.get("content", []):
                                    if c["type"] == "text":
                                        content_str += c["text"]
                            else:
                                content_str = json.dumps(tool_res, ensure_ascii=False)
                        
                        if func_name == "show_layer_on_map":
                            # 增强的 URL 提取逻辑 (参考 difyresearch.py)
                            try:
                                if content_str:
                                    # 尝试先解析为 JSON，因为 observation 通常是 {"show_layer_on_map": "..."}
                                    # 这样可以去掉外层转义，得到内层干净的字符串
                                    found_url = False
                                    try:
                                        obs_data = json.loads(content_str)
                                        if isinstance(obs_data, dict):
                                            # 遍历所有值查找 URL (通常在 show_layer_on_map 对应的值中)
                                            for val in obs_data.values():
                                                if isinstance(val, str):
                                                    # 在内层字符串中查找 "url": "..."
                                                    url_match = re.search(r'"url":\s*"([^"]+)"', val)
                                                    if url_match:
                                                        urls_generated.append(url_match.group(1))
                                                        found_url = True
                                                        break
                                    except:
                                        pass

                                    # 如果 JSON 解析失败或没找到，尝试在原始字符串中直接正则匹配
                                    # 兼容转义引号 \"url\": \"...\"
                                    if not found_url:
                                        # 匹配 "url": "..." 或 \"url\": \"...\"
                                        # 注意：(?:\\)? 匹配可选的反斜杠
                                        url_match = re.search(r'(?:\\)?"url(?:\\)?"\s*:\s*(?:\\)?"([^"]+?)(?:\\)?"', content_str)
                                        if url_match:
                                            url = url_match.group(1)
                                            # 如果匹配到了末尾的反斜杠（因为 [^"] 包含 \），去掉它
                                            if url.endswith('\\'):
                                                url = url[:-1]
                                            urls_generated.append(url)
                            except Exception:
                                pass
                        
                        conversation.append(ChatMessage(
                            role="tool",
                            content=content_str,
                            tool_call_id=call_id
                        ))
                    continue
                else:
                    final_content = msg_data['content']
                    break
            
            if turn >= max_turns:
                log_message(f"  警告: 达到最大对话轮数 ({max_turns})")
                
        except Exception as e:
            error_msg = str(e)
            log_message(f"处理出错: {e}")
        
        q_duration = time.time() - q_start_time
        log_message(f"完成。耗时: {q_duration:.2f} 秒")
        
        # 写入结果
        try:
            with open(output_file_path, "a", encoding="utf-8") as out_f:
                out_f.write(f"问题 [{current_num}]: {q_text}\n")
                if error_msg:
                    out_f.write(f"状态: 失败 ({error_msg})\n")
                else:
                    out_f.write(f"回答: {final_content}\n")
                out_f.write(f"耗时: {q_duration:.2f} 秒\n")
                out_f.write("-" * 50 + "\n")
        except Exception as e:
            log_message(f"写入结果文件失败: {e}")
        
        # 写入 CSV 结果
        try:
            with open(output_file_path_csv, "a", encoding="utf-8", newline='') as f:
                writer = csv.writer(f)
                tools_str = ",".join(tools_used)
                layers_str = ",".join(layers_shown)
                urls_str = ",".join(urls_generated)
                writer.writerow([current_num, q_text, round(q_duration, 2), accumulated_tokens, tools_str, layers_str, urls_str])
        except Exception as e:
            log_message(f"写入 CSV 结果文件失败: {e}")
            
        # 避免请求过于频繁
        time.sleep(1)

    total_duration = time.time() - total_start_time
    log_message(f"=== Run {run_idx} 完成，总耗时: {total_duration:.2f} 秒 ===")

def main():
    log_message("=== 开始 Cherry Batch Ask 任务 ===")
    
    # 1. 初始化模型和 MCP
    model_id = "deepseek:deepseek-chat"
    model = Model(model_id)
    if not model.check_availability():
        log_message(f"警告: 模型 {model.id} 未在 /models 列表中找到。")
    log_message(f"当前连接模型: {model.id}")
    
    # 询问是否连接 MCP
    mcp_server = None
    tools = []
    
    print("\n是否连接 MCP 服务器? (输入 y/yes 连接，其他键跳过)")
    mcp_choice = input("请输入: ").strip().lower()
    
    if mcp_choice in ['y', 'yes']:
        try:
            mcp_server = MCPServer(MCP_SERVER_ID)
            server_info = mcp_server.get_info()
            server_name = server_info.get("name", "未知服务")
            log_message(f"当前连接 MCP 服务: {server_name} (ID: {mcp_server.id})")
            
            tools = mcp_server.list_tools()
            log_message(f"发现 {len(tools)} 个 MCP 工具。")
        except Exception as e:
            log_message(f"连接 MCP 服务器失败: {e}")
            mcp_server = None
    else:
        log_message("用户选择跳过 MCP 连接，将仅进行纯文本对话。")
        global SYSTEM_PROMPT
        # 提示词为空，避免模型尝试使用不存在的工具
        SYSTEM_PROMPT = ""
        log_message("注意：当前 System Prompt 已设置为空。")
    
    # 2. 选择输入文件
    input_file_path = select_input_file()
    if not input_file_path:
        log_message("未选择文件或退出任务。")
        return

    # 读取并过滤问题
    questions = []
    try:
        with open(input_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 匹配 "数字.内容" 格式
                match = re.match(r'^(\d+)\.(.*)', line)
                if match:
                    content = match.group(2)
                    # 过滤括号内容
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
    
    input_filename = os.path.basename(input_file_path)
    base_name_no_ext = os.path.splitext(input_filename)[0]
    file_ext = os.path.splitext(input_filename)[1]

    for i in range(run_count):
        run_idx = i + 1
        suffix = f"_run{run_idx}"
            
        if run_count == 1:
             output_filename = f"cherry_results_{input_filename}"
        else:
             output_filename = f"cherry_results_{base_name_no_ext}{suffix}{file_ext}"

        output_file_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # CSV 文件名必须明确是 Cherry 结果以及第几轮
        csv_filename = f"cherry_{base_name_no_ext}{suffix}.csv"
        output_file_path_csv = os.path.join(CSV_OUTPUT_DIR, csv_filename)
        
        auto_resume = (run_count > 1)
        
        process_batch_run(run_idx, questions, output_file_path, output_file_path_csv, model, mcp_server, tools, auto_resume)

    log_message("=== 所有实验任务结束 ===")

if __name__ == "__main__":
    main()
