#!/usr/bin/env python3
"""
GeoServer批量图层发布工具 - 交互式版本
支持自动计算边界框，批量发布存储仓库中的图层
"""

import argparse
import requests
import json
import time
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re

class GeoServerBatchPublisher:
    def __init__(self, base_url: str, username: str, password: str):
        """
        初始化GeoServer连接
        
        Args:
            base_url: GeoServer基础URL (如: http://localhost:8080/geoserver)
            username: GeoServer用户名
            password: GeoServer密码
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.rest_url = f"{self.base_url}/rest"
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def _load_json(self, response: requests.Response) -> Any:
        try_encodings = []
        ct = response.headers.get('Content-Type', '')
        m = re.search(r'charset=([\\w\\-]+)', ct, re.IGNORECASE)
        if m:
            try_encodings.append(m.group(1).lower())
        if response.encoding:
            try_encodings.append(response.encoding.lower())
        try_encodings += ['utf-8', 'gbk', 'latin-1']
        tried = set()
        for enc in try_encodings:
            if enc in tried:
                continue
            tried.add(enc)
            try:
                text = response.content.decode(enc)
                return json.loads(text)
            except Exception:
                continue
        return response.json()
        
    def test_connection(self) -> bool:
        """测试GeoServer连接"""
        try:
            response = self.session.get(f"{self.rest_url}/workspaces.json")
            if response.status_code == 200:
                return True
            else:
                print(f"连接失败: HTTP {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"连接失败: {e}")
            return False
    
    def get_datastores(self, workspace: str) -> List[Dict]:
        """获取指定工作空间的数据存储列表"""
        try:
            url = f"{self.rest_url}/workspaces/{workspace}/datastores.json"
            response = self.session.get(url)
            if response.status_code == 200:
                data = self._load_json(response)
                if 'dataStore' in data.get('dataStores', {}):
                    return data['dataStores']['dataStore']
                return []
            else:
                print(f"获取数据存储失败: HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"获取数据存储失败: {e}")
            return []
    
    def get_unpublished_layers(self, workspace: str, datastore: str) -> List[str]:
        """获取未发布的图层列表"""
        try:
            url = f"{self.rest_url}/workspaces/{workspace}/datastores/{datastore}/featuretypes.json?list=available"
            response = self.session.get(url)
            if response.status_code == 200:
                data = self._load_json(response)
                if 'list' in data and 'string' in data['list']:
                    layers = data['list']['string']
                    if isinstance(layers, list):
                        return layers
                    else:
                        return [layers]
                return []
            else:
                print(f"获取未发布图层失败: HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"获取未发布图层失败: {e}")
            return []
    
    def get_published_layers(self, workspace: str, datastore: str) -> List[str]:
        """获取已发布的图层列表"""
        try:
            url = f"{self.rest_url}/workspaces/{workspace}/datastores/{datastore}/featuretypes.json"
            response = self.session.get(url)
            if response.status_code == 200:
                data = self._load_json(response)
                if 'featureTypes' in data and 'featureType' in data['featureTypes']:
                    layers = data['featureTypes']['featureType']
                    if isinstance(layers, list):
                        return [layer['name'] for layer in layers]
                    else:
                        return [layers['name']]
                return []
            else:
                print(f"获取已发布图层失败: HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"获取已发布图层失败: {e}")
            return []
    
    def get_styles(self) -> List[str]:
        """获取所有样式"""
        try:
            url = f"{self.rest_url}/styles.json"
            response = self.session.get(url)
            if response.status_code == 200:
                data = self._load_json(response)
                if 'styles' in data and 'style' in data['styles']:
                    styles = data['styles']['style']
                    if isinstance(styles, list):
                        return [style['name'] for style in styles]
                    else:
                        return [styles['name']]
                return []
            return []
        except Exception as e:
            print(f"获取样式列表失败: {e}")
            return []
    
    def create_layer_xml(self, layer_name: str, native_bounds: Optional[Dict] = None) -> str:
        """
        创建图层配置的XML
        
        Args:
            layer_name: 图层名称
            native_bounds: 原生边界框（如果为None则让GeoServer自动计算）
        """
        # 创建XML根元素
        feature_type = ET.Element("featureType")
        
        # 添加基本元素
        name_elem = ET.SubElement(feature_type, "name")
        name_elem.text = layer_name
        
        title_elem = ET.SubElement(feature_type, "title")
        title_elem.text = layer_name
        
        native_elem = ET.SubElement(feature_type, "nativeName")
        native_elem.text = layer_name
        
        # 设置SRS为EPSG:4326（WGS84）
        srs_elem = ET.SubElement(feature_type, "srs")
        srs_elem.text = "EPSG:4326"
        
        # 设置投影策略
        projection_policy = ET.SubElement(feature_type, "projectionPolicy")
        projection_policy.text = "FORCE_DECLARED"
        
        # 如果提供了原生边界，则设置
        if native_bounds:
            native_bbox = ET.SubElement(feature_type, "nativeBoundingBox")
            
            minx = ET.SubElement(native_bbox, "minx")
            minx.text = str(native_bounds.get('minx', '-180'))
            maxx = ET.SubElement(native_bbox, "maxx")
            maxx.text = str(native_bounds.get('maxx', '180'))
            miny = ET.SubElement(native_bbox, "miny")
            miny.text = str(native_bounds.get('miny', '-90'))
            maxy = ET.SubElement(native_bbox, "maxy")
            maxy.text = str(native_bounds.get('maxy', '90'))
            
            # 设置CRS
            crs = ET.SubElement(native_bbox, "crs")
            crs.text = native_bounds.get('crs', 'EPSG:4326')
        
        # 不在创建时提供 latLonBoundingBox，后续使用 recalculate 计算
        
        # 启用服务
        enabled = ET.SubElement(feature_type, "enabled")
        enabled.text = "true"
        
        # 转换为格式化的XML字符串
        rough_string = ET.tostring(feature_type, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
    
    def recalc_bounds(self, workspace: str, datastore: str, layer_name: str) -> bool:
        try:
            url_xml = f"{self.rest_url}/workspaces/{workspace}/datastores/{datastore}/featuretypes/{layer_name}.xml"
            get_resp = self.session.get(url_xml, headers={'Accept': 'application/xml'})
            if get_resp.status_code != 200:
                return False
            root = ET.fromstring(get_resp.content)
            # 移除可能存在的 bbox，确保服务端重算
            for tag in ['nativeBoundingBox', 'latLonBoundingBox']:
                elem = root.find(tag)
                if elem is not None:
                    root.remove(elem)
            xml_content = ET.tostring(root, encoding='utf-8')
            put_url = f"{url_xml}?recalculate=nativebbox,latlonbbox"
            headers = {'Content-Type': 'application/xml; charset=UTF-8'}
            put_resp = self.session.put(put_url, data=xml_content, headers=headers)
            return put_resp.status_code == 200
        except Exception:
            return False
    
    def publish_layer(self, workspace: str, datastore: str, layer_name: str, 
                     compute_bounds: bool = True, style: Optional[str] = None) -> bool:
        """
        发布单个图层
        
        Args:
            workspace: 工作空间名称
            datastore: 数据存储名称
            layer_name: 图层名称
            compute_bounds: 是否计算边界框
            style: 样式名称
        """
        try:
            # 构建URL
            url = f"{self.rest_url}/workspaces/{workspace}/datastores/{datastore}/featuretypes"
            
            # 创建XML配置
            xml_content = self.create_layer_xml(layer_name)
            
            # 设置请求头为XML
            headers = {'Content-Type': 'application/xml; charset=UTF-8'}
            
            # 发送请求
            response = self.session.post(url, data=xml_content.encode('utf-8'), headers=headers)
            
            if response.status_code in [200, 201]:
                print(f"✓ 成功发布图层: {layer_name}")
                
                if compute_bounds:
                    ok = self.recalc_bounds(workspace, datastore, layer_name)
                    if ok:
                        print("  ✓ 已计算原生边界与经纬度边界")
                    else:
                        print("  ✗ 边界计算失败")
                
                # 如果指定了样式，分配样式
                if style:
                    success = self.assign_style(workspace, layer_name, style)
                    if not success:
                        print(f"  警告: 分配样式失败，但图层已成功发布")
                
                return True
            else:
                error_msg = response.text
                # 尝试解析错误信息
                if "already exists" in error_msg:
                    print(f"✗ 图层已存在: {layer_name}")
                else:
                    print(f"✗ 发布失败 {layer_name}: HTTP {response.status_code} - {error_msg[:200]}")
                return False
                
        except Exception as e:
            print(f"✗ 发布图层 {layer_name} 时出错: {e}")
            return False
    
    def assign_style(self, workspace: str, layer_name: str, style_name: str) -> bool:
        """为图层分配样式"""
        try:
            url = f"{self.rest_url}/workspaces/{workspace}/layers/{layer_name}"
            
            # 获取当前图层配置
            response = self.session.get(url)
            if response.status_code != 200:
                return False
            
            # 解析XML并更新样式
            root = ET.fromstring(response.content)
            
            # 查找或创建defaultStyle元素
            default_style = root.find('defaultStyle')
            if default_style is None:
                default_style = ET.SubElement(root, 'defaultStyle')
            
            # 设置样式名称
            name_elem = default_style.find('name')
            if name_elem is None:
                name_elem = ET.SubElement(default_style, 'name')
            name_elem.text = style_name
            
            # 设置工作空间
            ws_elem = default_style.find('workspace')
            if ws_elem is None:
                ws_elem = ET.SubElement(default_style, 'workspace')
            ws_elem.text = workspace
            
            # 转换回XML
            xml_content = ET.tostring(root, encoding='utf-8').decode()
            
            # 更新图层配置
            headers = {'Content-Type': 'application/xml'}
            put_response = self.session.put(url, data=xml_content, headers=headers)
            
            if put_response.status_code == 200:
                print(f"  ✓ 已分配样式 '{style_name}' 到图层 {layer_name}")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"  分配样式失败: {e}")
            return False
    
    def batch_publish(self, workspace: str, datastore: str, 
                     filter_pattern: Optional[str] = None,
                     compute_bounds: bool = True,
                     style: Optional[str] = None,
                     exclude_published: bool = True) -> Tuple[int, int]:
        """
        批量发布图层
        
        Args:
            workspace: 工作空间名称
            datastore: 数据存储名称
            filter_pattern: 图层名称过滤模式（支持通配符）
            compute_bounds: 是否计算边界框
            style: 默认样式名称
            exclude_published: 是否排除已发布的图层
            
        Returns:
            (成功数, 总数)
        """
        print(f"\n{'='*60}")
        print("开始批量发布图层")
        print(f"{'='*60}")
        print(f"工作空间: {workspace}")
        print(f"数据存储: {datastore}")
        print(f"计算边界: {'是' if compute_bounds else '否'}")
        if style:
            print(f"默认样式: {style}")
        print(f"排除已发布: {'是' if exclude_published else '否'}")
        if filter_pattern:
            print(f"过滤模式: {filter_pattern}")
        print(f"{'-'*60}")
        
        # 获取所有未发布的图层
        all_layers = self.get_unpublished_layers(workspace, datastore)
        
        if not all_layers:
            print("没有找到可发布的图层")
            return 0, 0
        
        print(f"发现 {len(all_layers)} 个可发布的图层")
        
        # 如果需要排除已发布的图层
        if exclude_published:
            published_layers = self.get_published_layers(workspace, datastore)
            unpublished_layers = [layer for layer in all_layers if layer not in published_layers]
            print(f"已发布图层: {len(published_layers)} 个")
            print(f"未发布图层: {len(unpublished_layers)} 个")
        else:
            unpublished_layers = all_layers
        
        # 应用过滤模式
        if filter_pattern:
            import fnmatch
            unpublished_layers = [layer for layer in unpublished_layers 
                                if fnmatch.fnmatch(layer, filter_pattern)]
            print(f"过滤后图层: {len(unpublished_layers)} 个")
        
        if not unpublished_layers:
            print("没有需要发布的图层")
            return 0, 0
        
        # 显示将要发布的图层列表
        print(f"\n即将发布的图层列表:")
        for i, layer in enumerate(unpublished_layers, 1):
            print(f"  {i:3d}. {layer}")
        
        # 确认是否继续
        confirm = input(f"\n确认要发布以上 {len(unpublished_layers)} 个图层吗? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("操作已取消")
            return 0, len(unpublished_layers)
        
        # 开始批量发布
        success_count = 0
        total_count = len(unpublished_layers)
        
        print(f"\n开始发布 {total_count} 个图层...")
        print("=" * 60)
        
        for i, layer_name in enumerate(unpublished_layers, 1):
            print(f"[{i:3d}/{total_count:3d}] 正在发布: {layer_name}")
            
            success = self.publish_layer(
                workspace=workspace,
                datastore=datastore,
                layer_name=layer_name,
                compute_bounds=compute_bounds,
                style=style
            )
            
            if success:
                success_count += 1
            
            # 添加短暂延迟，避免请求过快
            if i < total_count:
                time.sleep(0.3)
        
        print("=" * 60)
        print(f"批量发布完成!")
        print(f"成功: {success_count}/{total_count}")
        
        return success_count, total_count
    
    def list_workspaces(self) -> List[str]:
        """列出所有工作空间"""
        try:
            response = self.session.get(f"{self.rest_url}/workspaces.json")
            if response.status_code == 200:
                data = self._load_json(response)
                workspaces = data.get('workspaces', {}).get('workspace', [])
                if isinstance(workspaces, list):
                    return [ws['name'] for ws in workspaces]
                else:
                    return [workspaces['name']]
            return []
        except Exception as e:
            print(f"获取工作空间失败: {e}")
            return []

class InteractiveGeoServerCLI:
    """交互式GeoServer CLI"""
    
    def __init__(self):
        self.publisher = None
        self.config_file = os.path.expanduser("~/.geoserver_cli_config.json")
        self.saved_configs = self.load_configs()
    
    def load_configs(self) -> Dict:
        """加载保存的配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_configs(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.saved_configs, f, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self, title: str):
        """打印标题"""
        self.clear_screen()
        print("=" * 60)
        print(f"GeoServer批量发布工具 - {title}")
        print("=" * 60)
        print()
    
    def connect_geoserver(self) -> bool:
        """连接GeoServer"""
        self.print_header("连接设置")
        
        print("请选择连接方式:")
        print("  1. 新建连接")
        print("  2. 使用保存的连接")
        
        if self.saved_configs:
            for i, (name, config) in enumerate(self.saved_configs.items(), 3):
                print(f"  {i}. {name} ({config['url']})")
        
        choice = input("\n请选择 (1-2): ").strip()
        
        if choice == "1":
            return self.new_connection()
        elif choice == "2" and self.saved_configs:
            return self.use_saved_connection()
        elif choice.isdigit() and int(choice) >= 3:
            idx = int(choice) - 3
            names = list(self.saved_configs.keys())
            if idx < len(names):
                config_name = names[idx]
                config = self.saved_configs[config_name]
                return self.create_connection_from_config(config_name, config)
        
        return self.new_connection()
    
    def new_connection(self) -> bool:
        """新建连接"""
        self.print_header("新建连接")
        
        url = input("GeoServer URL (例如: http://localhost:8080/geoserver): ").strip()
        if not url:
            print("URL不能为空")
            return False
            
        username = input("用户名: ").strip()
        password = input("密码: ").strip()
        
        # 测试连接
        print("\n正在测试连接...")
        publisher = GeoServerBatchPublisher(url, username, password)
        if publisher.test_connection():
            self.publisher = publisher
            print("✓ 连接成功!")
            
            # 询问是否保存配置
            save = input("\n是否保存此连接配置? (y/N): ").strip().lower()
            if save in ['y', 'yes']:
                config_name = input("配置名称: ").strip()
                if config_name:
                    self.saved_configs[config_name] = {
                        'url': url,
                        'username': username,
                        'password': password
                    }
                    self.save_configs()
                    print(f"✓ 配置 '{config_name}' 已保存")
            
            input("\n按Enter键继续...")
            return True
        else:
            print("✗ 连接失败，请检查URL和凭据")
            input("\n按Enter键返回...")
            return False
    
    def use_saved_connection(self) -> bool:
        """使用保存的连接"""
        self.print_header("选择保存的连接")
        
        if not self.saved_configs:
            print("没有保存的连接配置")
            input("\n按Enter键返回...")
            return False
        
        print("保存的连接配置:")
        for i, (name, config) in enumerate(self.saved_configs.items(), 1):
            print(f"  {i}. {name} ({config['url']})")
        print(f"  {len(self.saved_configs)+1}. 返回")
        
        choice = input(f"\n请选择 (1-{len(self.saved_configs)+1}): ").strip()
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(self.saved_configs):
                config_name = list(self.saved_configs.keys())[idx]
                config = self.saved_configs[config_name]
                return self.create_connection_from_config(config_name, config)
        
        return False
    
    def create_connection_from_config(self, config_name: str, config: Dict) -> bool:
        """从配置创建连接"""
        print(f"\n正在连接 '{config_name}'...")
        publisher = GeoServerBatchPublisher(
            config['url'],
            config['username'],
            config['password']
        )
        
        if publisher.test_connection():
            self.publisher = publisher
            print("✓ 连接成功!")
            input("\n按Enter键继续...")
            return True
        else:
            print("✗ 连接失败")
            input("\n按Enter键返回...")
            return False
    
    def main_menu(self):
        """主菜单"""
        while True:
            self.print_header("主菜单")
            
            print("请选择操作:")
            print("  1. 列出工作空间")
            print("  2. 列出数据存储")
            print("  3. 查看图层状态")
            print("  4. 批量发布图层")
            print("  5. 管理连接配置")
            print("  6. 重新连接")
            print("  0. 退出")
            
            choice = input("\n请选择 (0-6): ").strip()
            
            if choice == "1":
                self.list_workspaces_menu()
            elif choice == "2":
                self.list_datastores_menu()
            elif choice == "3":
                self.view_layers_menu()
            elif choice == "4":
                self.batch_publish_menu()
            elif choice == "5":
                self.manage_configs_menu()
            elif choice == "6":
                if self.connect_geoserver():
                    continue
            elif choice == "0":
                print("再见!")
                sys.exit(0)
    
    def list_workspaces_menu(self):
        """列出工作空间菜单"""
        self.print_header("工作空间列表")
        
        try:
            workspaces = self.publisher.list_workspaces()
            if workspaces:
                print(f"找到 {len(workspaces)} 个工作空间:\n")
                for i, ws in enumerate(workspaces, 1):
                    print(f"  {i:3d}. {ws}")
            else:
                print("没有找到工作空间")
        except Exception as e:
            print(f"获取工作空间失败: {e}")
        
        input("\n按Enter键返回...")
    
    def list_datastores_menu(self):
        """列出数据存储菜单"""
        self.print_header("数据存储列表")
        
        # 选择工作空间
        workspaces = self.publisher.list_workspaces()
        if not workspaces:
            print("没有找到工作空间")
            input("\n按Enter键返回...")
            return
        
        print("请选择工作空间:")
        for i, ws in enumerate(workspaces, 1):
            print(f"  {i}. {ws}")
        
        choice = input(f"\n请选择 (1-{len(workspaces)}): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(workspaces):
                workspace = workspaces[idx]
                
                # 获取数据存储
                self.print_header(f"数据存储列表 - {workspace}")
                datastores = self.publisher.get_datastores(workspace)
                
                if datastores:
                    print(f"找到 {len(datastores)} 个数据存储:\n")
                    for i, ds in enumerate(datastores, 1):
                        ds_name = ds['name'] if isinstance(ds, dict) else str(ds)
                        print(f"  {i:3d}. {ds_name}")
                else:
                    print("没有找到数据存储")
        
        input("\n按Enter键返回...")
    
    def view_layers_menu(self):
        """查看图层菜单"""
        self.print_header("查看图层状态")
        
        # 选择工作空间
        workspaces = self.publisher.list_workspaces()
        if not workspaces:
            print("没有找到工作空间")
            input("\n按Enter键返回...")
            return
        
        print("请选择工作空间:")
        for i, ws in enumerate(workspaces, 1):
            print(f"  {i}. {ws}")
        
        ws_choice = input(f"\n请选择 (1-{len(workspaces)}): ").strip()
        if not ws_choice.isdigit():
            input("\n按Enter键返回...")
            return
            
        ws_idx = int(ws_choice) - 1
        if not (0 <= ws_idx < len(workspaces)):
            input("\n选择无效，按Enter键返回...")
            return
            
        workspace = workspaces[ws_idx]
        
        # 选择数据存储
        datastores = self.publisher.get_datastores(workspace)
        if not datastores:
            print(f"工作空间 '{workspace}' 中没有数据存储")
            input("\n按Enter键返回...")
            return
        
        print(f"\n请选择数据存储:")
        for i, ds in enumerate(datastores, 1):
            ds_name = ds['name'] if isinstance(ds, dict) else str(ds)
            print(f"  {i}. {ds_name}")
        
        ds_choice = input(f"\n请选择 (1-{len(datastores)}): ").strip()
        if not ds_choice.isdigit():
            input("\n按Enter键返回...")
            return
            
        ds_idx = int(ds_choice) - 1
        if not (0 <= ds_idx < len(datastores)):
            input("\n选择无效，按Enter键返回...")
            return
            
        datastore = datastores[ds_idx]['name'] if isinstance(datastores[ds_idx], dict) else str(datastores[ds_idx])
        
        # 显示图层状态
        self.print_header(f"图层状态 - {workspace}.{datastore}")
        
        print("获取图层信息...")
        published = self.publisher.get_published_layers(workspace, datastore)
        unpublished = self.publisher.get_unpublished_layers(workspace, datastore)
        
        print(f"\n已发布图层 ({len(published)} 个):")
        if published:
            for i, layer in enumerate(published, 1):
                print(f"  {i:3d}. {layer}")
        else:
            print("  无")
        
        print(f"\n未发布图层 ({len(unpublished)} 个):")
        if unpublished:
            for i, layer in enumerate(unpublished, 1):
                print(f"  {i:3d}. {layer}")
        else:
            print("  无")
        
        print(f"\n总计: {len(published) + len(unpublished)} 个图层")
        
        input("\n按Enter键返回...")
    
    def batch_publish_menu(self):
        """批量发布菜单"""
        self.print_header("批量发布图层")
        
        # 选择工作空间
        workspaces = self.publisher.list_workspaces()
        if not workspaces:
            print("没有找到工作空间")
            input("\n按Enter键返回...")
            return
        
        print("请选择工作空间:")
        for i, ws in enumerate(workspaces, 1):
            print(f"  {i}. {ws}")
        
        ws_choice = input(f"\n请选择 (1-{len(workspaces)}): ").strip()
        if not ws_choice.isdigit():
            input("\n按Enter键返回...")
            return
            
        ws_idx = int(ws_choice) - 1
        if not (0 <= ws_idx < len(workspaces)):
            input("\n选择无效，按Enter键返回...")
            return
            
        workspace = workspaces[ws_idx]
        
        # 选择数据存储
        datastores = self.publisher.get_datastores(workspace)
        if not datastores:
            print(f"工作空间 '{workspace}' 中没有数据存储")
            input("\n按Enter键返回...")
            return
        
        print(f"\n请选择数据存储:")
        for i, ds in enumerate(datastores, 1):
            ds_name = ds['name'] if isinstance(ds, dict) else str(ds)
            print(f"  {i}. {ds_name}")
        
        ds_choice = input(f"\n请选择 (1-{len(datastores)}): ").strip()
        if not ds_choice.isdigit():
            input("\n按Enter键返回...")
            return
            
        ds_idx = int(ds_choice) - 1
        if not (0 <= ds_idx < len(datastores)):
            input("\n选择无效，按Enter键返回...")
            return
            
        datastore = datastores[ds_idx]['name'] if isinstance(datastores[ds_idx], dict) else str(datastores[ds_idx])
        
        # 发布选项
        self.print_header(f"发布设置 - {workspace}.{datastore}")
        
        # 过滤模式
        filter_pattern = input("过滤模式 (支持通配符，如 'roads_*'，直接回车跳过): ").strip()
        if filter_pattern == "":
            filter_pattern = None
        
        # 计算边界
        compute_bounds = True
        bounds_choice = input("是否计算边界框? (Y/n): ").strip().lower()
        if bounds_choice in ['n', 'no']:
            compute_bounds = False
        
        # 排除已发布
        exclude_published = True
        exclude_choice = input("是否排除已发布的图层? (Y/n): ").strip().lower()
        if exclude_choice in ['n', 'no']:
            exclude_published = False
        
        # 选择样式
        style = None
        style_choice = input("是否分配默认样式? (y/N): ").strip().lower()
        if style_choice in ['y', 'yes']:
            styles = self.publisher.get_styles()
            if styles:
                print(f"\n可用样式:")
                for i, s in enumerate(styles[:20], 1):  # 只显示前20个
                    print(f"  {i}. {s}")
                if len(styles) > 20:
                    print(f"  ... 还有 {len(styles)-20} 个样式未显示")
                
                style_input = input("\n输入样式名称或编号 (直接回车跳过): ").strip()
                if style_input:
                    if style_input.isdigit():
                        idx = int(style_input) - 1
                        if 0 <= idx < len(styles):
                            style = styles[idx]
                    else:
                        style = style_input
        
        # 开始批量发布
        self.publisher.batch_publish(
            workspace=workspace,
            datastore=datastore,
            filter_pattern=filter_pattern,
            compute_bounds=compute_bounds,
            style=style,
            exclude_published=exclude_published
        )
        
        input("\n按Enter键返回...")
    
    def manage_configs_menu(self):
        """管理配置菜单"""
        while True:
            self.print_header("管理连接配置")
            
            if not self.saved_configs:
                print("没有保存的连接配置")
            else:
                print("已保存的配置:")
                for i, (name, config) in enumerate(self.saved_configs.items(), 1):
                    print(f"  {i}. {name} ({config['url']})")
            
            print("\n操作:")
            print("  1. 删除配置")
            print("  2. 重命名配置")
            print("  0. 返回")
            
            choice = input("\n请选择 (0-2): ").strip()
            
            if choice == "1" and self.saved_configs:
                self.delete_config()
            elif choice == "2" and self.saved_configs:
                self.rename_config()
            elif choice == "0":
                break
    
    def delete_config(self):
        """删除配置"""
        self.print_header("删除配置")
        
        print("请选择要删除的配置:")
        config_names = list(self.saved_configs.keys())
        for i, name in enumerate(config_names, 1):
            print(f"  {i}. {name}")
        
        choice = input(f"\n请选择 (1-{len(config_names)}): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(config_names):
                config_name = config_names[idx]
                confirm = input(f"确认删除配置 '{config_name}'? (y/N): ").strip().lower()
                if confirm in ['y', 'yes']:
                    del self.saved_configs[config_name]
                    self.save_configs()
                    print(f"✓ 配置 '{config_name}' 已删除")
                    input("\n按Enter键继续...")
    
    def rename_config(self):
        """重命名配置"""
        self.print_header("重命名配置")
        
        print("请选择要重命名的配置:")
        config_names = list(self.saved_configs.keys())
        for i, name in enumerate(config_names, 1):
            print(f"  {i}. {name}")
        
        choice = input(f"\n请选择 (1-{len(config_names)}): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(config_names):
                old_name = config_names[idx]
                new_name = input(f"输入新名称: ").strip()
                if new_name and new_name != old_name:
                    if new_name in self.saved_configs:
                        print(f"✗ 名称 '{new_name}' 已存在")
                    else:
                        self.saved_configs[new_name] = self.saved_configs[old_name]
                        del self.saved_configs[old_name]
                        self.save_configs()
                        print(f"✓ 配置已重命名为 '{new_name}'")
                input("\n按Enter键继续...")
    
    def run(self):
        """运行交互式CLI"""
        print("=" * 60)
        print("GeoServer批量图层发布工具 - 交互式版本")
        print("=" * 60)
        print()
        
        # 连接GeoServer
        while True:
            if self.connect_geoserver():
                break
            else:
                retry = input("\n是否重试? (Y/n): ").strip().lower()
                if retry in ['n', 'no']:
                    print("再见!")
                    sys.exit(0)
        
        # 显示主菜单
        self.main_menu()

def main():
    parser = argparse.ArgumentParser(
        description='GeoServer批量图层发布工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s publish --url http://localhost:8080/geoserver --user admin --pass geoserver --ws myworkspace --ds mydatastore
  %(prog)s publish --url http://localhost:8080/geoserver --user admin --pass geoserver --ws myworkspace --ds mydatastore --filter "roads_*"
  %(prog)s publish --url http://localhost:8080/geoserver --user admin --pass geoserver --ws myworkspace --ds mydatastore --no-compute-bounds
  %(prog)s list --url http://localhost:8080/geoserver --user admin --pass geoserver --ws myworkspace --ds mydatastore
  %(prog)s --interactive  (进入交互模式)
        '''
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # publish 命令
    publish_parser = subparsers.add_parser('publish', help='批量发布图层')
    publish_parser.add_argument('--url', required=True, help='GeoServer URL (例如: http://localhost:8080/geoserver)')
    publish_parser.add_argument('--user', required=True, help='GeoServer用户名')
    publish_parser.add_argument('--pass', dest='password', required=True, help='GeoServer密码')
    publish_parser.add_argument('--ws', '--workspace', dest='workspace', required=True, help='工作空间名称')
    publish_parser.add_argument('--ds', '--datastore', dest='datastore', required=True, help='数据存储名称')
    publish_parser.add_argument('--filter', help='图层名称过滤模式 (例如: "roads_*")')
    publish_parser.add_argument('--style', help='默认样式名称')
    publish_parser.add_argument('--no-compute-bounds', action='store_false', dest='compute_bounds', 
                               help='不计算边界框')
    publish_parser.add_argument('--include-published', action='store_true', 
                               help='包含已发布的图层（默认跳过已发布的）')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出图层')
    list_parser.add_argument('--url', required=True, help='GeoServer URL')
    list_parser.add_argument('--user', required=True, help='GeoServer用户名')
    list_parser.add_argument('--pass', dest='password', required=True, help='GeoServer密码')
    list_parser.add_argument('--ws', '--workspace', dest='workspace', help='工作空间名称')
    list_parser.add_argument('--ds', '--datastore', dest='datastore', help='数据存储名称')
    list_parser.add_argument('--type', choices=['workspaces', 'datastores', 'layers', 'unpublished'], 
                            default='workspaces', help='列出类型')
    
    # 交互模式选项
    parser.add_argument('--interactive', '-i', action='store_true', help='进入交互模式')
    
    args = parser.parse_args()
    
    try:
        if os.name == 'nt':
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    # 如果指定了交互模式或者没有提供命令，则进入交互模式
    if args.interactive or not args.command:
        cli = InteractiveGeoServerCLI()
        cli.run()
    elif args.command == 'publish':
        # 创建GeoServer连接
        publisher = GeoServerBatchPublisher(args.url, args.user, args.password)
        
        # 测试连接
        if not publisher.test_connection():
            print("错误: 无法连接到GeoServer，请检查URL和凭据")
            sys.exit(1)
        
        # 批量发布图层
        success, total = publisher.batch_publish(
            workspace=args.workspace,
            datastore=args.datastore,
            filter_pattern=args.filter,
            compute_bounds=args.compute_bounds,
            style=args.style,
            exclude_published=not args.include_published
        )
        
        if success == 0 and total > 0:
            sys.exit(1)
            
    elif args.command == 'list':
        # 创建GeoServer连接
        publisher = GeoServerBatchPublisher(args.url, args.user, args.password)
        
        # 测试连接
        if not publisher.test_connection():
            print("错误: 无法连接到GeoServer，请检查URL和凭据")
            sys.exit(1)
        
        if args.type == 'workspaces':
            workspaces = publisher.list_workspaces()
            print("工作空间列表:")
            for ws in workspaces:
                print(f"  - {ws}")
                
        elif args.type == 'datastores' and args.workspace:
            datastores = publisher.get_datastores(args.workspace)
            print(f"工作空间 '{args.workspace}' 的数据存储列表:")
            for ds in datastores:
                if isinstance(ds, dict):
                    print(f"  - {ds['name']}")
                else:
                    print(f"  - {ds}")
                
        elif args.type == 'layers' and args.workspace and args.datastore:
            layers = publisher.get_published_layers(args.workspace, args.datastore)
            print(f"已发布的图层列表 ({args.workspace}.{args.datastore}):")
            for layer in layers:
                print(f"  - {layer}")
                
        elif args.type == 'unpublished' and args.workspace and args.datastore:
            layers = publisher.get_unpublished_layers(args.workspace, args.datastore)
            print(f"未发布的图层列表 ({args.workspace}.{args.datastore}):")
            for layer in layers:
                print(f"  - {layer}")
        else:
            print("错误: 需要指定工作空间和/或数据存储")
            sys.exit(1)

if __name__ == "__main__":
    main()
