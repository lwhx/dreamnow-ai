#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即梦 AI 生图工具 - 带 GUI 界面
基于 PyQt6 实现，支持图生图功能
"""

import sys
import os
import json
import base64
import requests
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QFileDialog,
    QGroupBox, QScrollArea, QTabWidget, QFrame, QCheckBox, QSpinBox,
    QDoubleSpinBox, QPlainTextEdit, QMessageBox, QDialog, QGridLayout,
    QListWidget, QListWidgetItem, QMenu
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMimeData, QTimer, QTimer, QPoint
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont, QIcon, QCursor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QFileDialog,
    QGroupBox, QScrollArea, QTabWidget, QFrame, QCheckBox, QSpinBox,
    QDoubleSpinBox, QPlainTextEdit, QMessageBox, QDialog, QGridLayout,
    QListWidget, QListWidgetItem, QMenu, QToolTip
)


# ==================== 自定义控件 ====================

class AutoCloseMessageBox(QMessageBox):
    """自动关闭的消息框"""
    def __init__(self, title, message, parent=None, timeout=3000):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(message)
        self.setIcon(QMessageBox.Icon.Information)
        self.timeout = timeout
        self.remaining_time = timeout // 1000
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.update_button_text()

    def update_countdown(self):
        """更新倒计时"""
        self.remaining_time -= 1
        self.update_button_text()
        if self.remaining_time <= 0:
            self.timer.stop()
            self.accept()

    def update_button_text(self):
        """更新按钮文本显示倒计时"""
        button = self.button(QMessageBox.StandardButton.Ok)
        if button:
            button.setText(f"关闭 ({self.remaining_time}s)")

    def exec(self):
        """显示对话框并启动倒计时"""
        self.timer.start(1000)
        return super().exec()


class ImageListWidget(QListWidget):
    """支持拖拽的图片列表控件"""
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self._preview_cache = {}
        self._preview_label = QLabel()
        self._preview_label.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self._preview_label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._preview_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._preview_label.setStyleSheet("background: #FFFFFF; border: 1px solid #CCCCCC;")
        self._preview_label.hide()
        # 启用多选
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        # 设置选中样式
        self.setStyleSheet("""
            QListWidget::item:selected {
                background-color: #4CAF50;
                color: white;
                border-radius: 3px;
            }
            QListWidget::item:selected:!active {
                background-color: #81C784;
                color: white;
            }
            QListWidget::item {
                padding: 1px 8px;
                border-bottom: 1px solid #EEEEEE;
                min-height: 10px;
            }
            QListWidget::item:hover {
                background-color: #E8F5E9;
            }
        """)
    
    def mouseMoveEvent(self, event):
        """鼠标移动时显示图片预览 tooltip"""
        item = self.itemAt(event.pos())
        if item:
            file_path = item.text()
            if os.path.isfile(file_path) and self.is_image_file(file_path):
                pixmap = self._preview_cache.get(file_path)
                if pixmap is None:
                    raw = QPixmap(file_path)
                    if not raw.isNull():
                        pixmap = raw.scaled(
                            240,
                            240,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self._preview_cache[file_path] = pixmap
                if pixmap:
                    self._preview_label.setPixmap(pixmap)
                    self._preview_label.adjustSize()
                    pos = event.globalPosition().toPoint() + QPoint(16, 16)
                    self._preview_label.move(pos)
                    self._preview_label.show()
                    super().mouseMoveEvent(event)
                    return
        self._preview_label.hide()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """鼠标离开时隐藏预览"""
        self._preview_label.hide()
        super().leaveEvent(event)

    def show_context_menu(self, position):
        """显示右键菜单"""
        menu = QMenu(self)
        
        # 移除选中项
        remove_action = menu.addAction("移除选中")
        remove_action.triggered.connect(self.remove_selected)
        
        # 清空列表
        clear_action = menu.addAction("清空列表")
        clear_action.triggered.connect(self.clear_list)
        
        menu.exec(QCursor.pos())
    
    def remove_selected(self):
        """移除选中的图片"""
        selected_items = self.selectedItems()
        for item in selected_items:
            row = self.row(item)
            self.takeItem(row)
    
    def clear_list(self):
        """清空列表"""
        self.clear()
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """拖拽移动事件"""
        event.accept()
    
    def dropEvent(self, event: QDropEvent):
        """拖拽放下事件"""
        file_paths = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isdir(file_path):
                # 如果是目录，扫描目录下的图片
                file_paths.extend(self.scan_directory_for_images(file_path))
            elif os.path.isfile(file_path):
                # 如果是文件，检查是否是图片
                if self.is_image_file(file_path):
                    file_paths.append(file_path)
        
        if file_paths:
            # 获取当前列表中已有的图片路径
            existing_paths = set()
            for i in range(self.count()):
                existing_paths.add(self.item(i).text())
            
            # 去重：只添加不存在的图片
            new_paths = [p for p in file_paths if p not in existing_paths]
            
            # 添加图片到列表
            for file_path in new_paths:
                self.addItem(file_path)
            
            if new_paths:
                event.accept()
            else:
                event.ignore()
        else:
            event.ignore()
    
    def is_image_file(self, file_path):
        """检查是否是图片文件"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        return os.path.splitext(file_path)[1].lower() in image_extensions
    
    def scan_directory_for_images(self, directory):
        """扫描目录下的图片文件（非递归）"""
        image_files = []
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path) and self.is_image_file(item_path):
                    image_files.append(item_path)
        except Exception as e:
            pass
        return image_files


# ==================== 配置常量 ====================

# API 地址
# API 地址（请在设置中配置）
API_URL = ""

# 可选的宽高比
RATIO_OPTIONS = ["1:1", "3:4", "4:3", "9:16", "16:9", "3:2", "2:3", "21:9"]

# 可选的分辨率
RESOLUTION_OPTIONS = ["1k", "2k", "4k"]

# 配置文件路径 - 保存到 C:\即梦ai配置
CONFIG_DIR = r"C:\即梦ai配置"
CONFIG_FILE = os.path.join(CONFIG_DIR, "jimeng_config.json")


# ==================== 配置管理 ====================

class ConfigManager:
    """配置管理器，负责加载和保存配置"""

    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        # 确保配置目录存在
        config_dir = os.path.dirname(self.config_file)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        self.default_config = {
            "api_url": API_URL,
            "auth_token": "",
            "model": "jimeng-4.0",
            "negative_prompt": "",
            "ratio": "3:4",
            "resolution": "2k",
            "image_list": [],
            "prompt_list": [
                {
                    "name": "正面视角",
                    "prompt": """请严格按照参考图中的沙发进行生成。
保持沙发的款式、形状、颜色、材质、底座、靠枕等所有外观细节完全一致。
将这款沙发放入意式现代高级客厅场景中。
采用正面视角拍摄，沙发居中摆放，正对镜头，展示沙发的完整正面外观。
客厅环境包括木饰面背景墙、地毯、茶几、窗帘、灯光。""",
                    "checked": True
                },
                {
                    "name": "侧面视角",
                    "prompt": """请严格按照参考图中的沙发进行生成。
保持沙发的款式、形状、颜色、材质、底座、靠枕等所有外观细节完全一致。
将这款沙发放入意式现代高级客厅场景中。
采用侧面视角拍摄，从左侧或右侧45度角拍摄，展示沙发的侧面轮廓和深度。
客厅环境包括木饰面背景墙、地毯、茶几、窗帘、灯光。""",
                    "checked": True
                },
                {
                    "name": "斜角视角",
                    "prompt": """请严格按照参考图中的沙发进行生成。
保持沙发的款式、形状、颜色、材质、底座、靠枕等所有外观细节完全一致。
将这款沙发放入意式现代高级客厅场景中。
采用斜角视角拍摄，从角落位置拍摄，同时展示沙发的正面和侧面，突出转角细节。
客厅环境包括木饰面背景墙、地毯、茶几、窗帘、灯光。""",
                    "checked": True
                },
                {
                    "name": "俯视视角",
                    "prompt": """请严格按照参考图中的沙发进行生成。
保持沙发的款式、形状、颜色、材质、底座、靠枕等所有外观细节完全一致。
将这款沙发放入意式现代高级客厅场景中。
采用俯视视角拍摄，从高处向下拍摄，展示沙发的整体布局和客厅空间关系。
客厅环境包括木饰面背景墙、地毯、茶几、窗帘、灯光。""",
                    "checked": True
                }
            ]
        }
    
    def load_config(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return self.default_config.copy()
    
    def save_config(self, config):
        """保存配置"""
        try:
            # 确保目录存在
            config_dir = os.path.dirname(self.config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")


# ==================== 工作线程 ====================

class ImageGeneratorThread(QThread):
    """图片生成工作线程"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._is_running = True
    
    def run(self):
        """运行线程"""
        try:
            # 处理参考图片（每次只用一张参考图）
            image_items = []
            for img_path in self.config.get("image_list", []):
                if os.path.isfile(img_path):
                    base64_url = self.image_to_base64(img_path)
                    image_items.append((img_path, base64_url))
                    self.log_signal.emit(f"📁 本地图片: {img_path} (已转换为 base64)")
                elif img_path.startswith('http://') or img_path.startswith('https://'):
                    image_items.append((img_path, img_path))
                    self.log_signal.emit(f"🌐 网络图片: {img_path}")
            
            if not image_items:
                self.error_signal.emit("没有有效的参考图片！")
                return
            
            # 生成多视角图片（每张参考图配合所有勾选提示词）
            all_saved_paths = []
            prompt_list = [p for p in self.config.get("prompt_list", []) if p.get('checked', True)]
            total_steps = len(image_items) * len(prompt_list)
            current_step = 0
            
            for img_index, (img_path, img_payload) in enumerate(image_items, 1):
                if not self._is_running:
                    break
                
                self.log_signal.emit(f"\n{'='*50}")
                self.log_signal.emit(f"参考图 {img_index}/{len(image_items)}: {img_path}")
                self.log_signal.emit(f"{'='*50}")
                
                for prompt_item in prompt_list:
                    if not self._is_running:
                        break
                    
                    current_step += 1
                    self.progress_signal.emit(current_step, total_steps)
                    self.log_signal.emit(f"生成视角: {prompt_item['name']}")
                    
                    saved_paths = self.generate_single_image(
                        prompt_item['prompt'],
                        [img_payload],
                        img_path if os.path.isfile(img_path) else None
                    )
                    
                    if saved_paths:
                        all_saved_paths.extend(saved_paths)
                        self.log_signal.emit(f"✅ 成功生成 {len(saved_paths)} 张图片")
                    
                    # 避免请求过快
                    if self._is_running:
                        self.msleep(2000)
            
            self.finished_signal.emit(all_saved_paths)
            
        except Exception as e:
            self.error_signal.emit(str(e))
    
    def stop(self):
        """停止线程"""
        self._is_running = False
    
    def image_to_base64(self, image_path):
        """将图片转换为 base64"""
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        ext = Path(image_path).suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/jpeg')
        
        base64_data = base64.b64encode(image_data).decode('utf-8')
        return f"data:{mime_type};base64,{base64_data}"
    
    def generate_single_image(self, prompt, processed_images, ref_image_path=None):
        """生成单张图片"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.config.get("auth_token", "")
        }
        
        data = {
            "model": self.config.get("model", "jimeng-4.0"),
            "prompt": prompt,
            "images": processed_images,
            "ratio": self.config.get("ratio", "3:4"),
            "resolution": self.config.get("resolution", "2k"),
            "negative_prompt": self.config.get("negative_prompt", "")
        }
        
        self.log_signal.emit("正在生成图片...")
        
        try:
            response = requests.post(
                self.config.get("api_url", API_URL),
                headers=headers,
                json=data,
                timeout=60
            )
            
            self.log_signal.emit(f"响应状态码：{response.status_code}")
            
            if response.status_code != 200:
                self.log_signal.emit(f"❌ 请求失败！")
                self.log_signal.emit(f"响应内容：{response.text}")
                return []
            
            result = response.json()
            
            if result.get('code') and result.get('code') != 0:
                self.log_signal.emit(f"❌ API返回错误！")
                self.log_signal.emit(f"错误码：{result.get('code')}")
                self.log_signal.emit(f"错误信息：{result.get('message')}")
                return []
            
            if not result.get('data'):
                self.log_signal.emit("❌ API 返回空数据！")
                return []
            
            # 保存图片（根据参考图片路径自动计算保存目录）
            saved_paths = self.save_images_to_local(result['data'], ref_image_path)
            
            return saved_paths
                
        except Exception as e:
            self.log_signal.emit(f"❌ 错误：{e}")
            return []
    
    def save_images_to_local(self, images_data, ref_image_path=None):
        """保存图片到本地"""
        saved_paths = []
        
        try:
            for i, img in enumerate(images_data, 1):
                if not self._is_running:
                    break
                
                url = img.get('url')
                if url:
                    # 根据参考图片路径计算保存目录
                    if ref_image_path:
                        save_dir = self.get_save_directory_for_image(ref_image_path)
                    else:
                        save_dir = os.path.join(os.getcwd(), "生成图片")

                    # 统一路径格式
                    save_dir = os.path.normpath(save_dir)
                    
                    # 创建保存目录
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir)
                    
                    filepath = self.download_image(url, save_dir)
                    if filepath:
                        saved_paths.append(filepath)
                        self.log_signal.emit(f"✅ 图片 {i}/{len(images_data)} 已保存：{filepath}")
        
        except Exception as e:
            self.log_signal.emit(f"保存图片失败：{e}")
        
        return saved_paths
    
    def get_save_directory_for_image(self, image_path):
        """获取图片的保存目录（上两级目录/生成图片/）"""
        image_dir = os.path.dirname(image_path)
        parent_dir = os.path.dirname(image_dir)
        save_dir = os.path.join(parent_dir, "生成图片")
        return save_dir
    
    def download_image(self, url, save_dir):
        """下载图片"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"image_{timestamp}_{os.urandom(4).hex()}.jpg"
            filepath = os.path.join(save_dir, filename)
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
            
        except Exception as e:
            self.log_signal.emit(f"下载失败 {url}: {e}")
            return None


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        self.generator_thread = None
        self._stop_requested = False
        
        self.init_ui()
        self.load_config_to_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("即梦AI生图")
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            min_w = min(640, avail.width())
            min_h = min(600, avail.height())
            self.setMinimumSize(min_w, min_h)
            target_w = min(650, avail.width())
            target_h = int(avail.height() * 0.85 * (2 / 3))
            self.resize(max(target_w, min_w), max(target_h, min_h))
        else:
            self.resize(650, 600)
            self.setMinimumSize(640, 600)
        
        # 设置全局样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
            QWidget {
                font-family: "Microsoft YaHei";
                font-size: 12px;
            }
            QLabel {
                color: #333333;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4CAF50;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #4CAF50;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3D8B40;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 2px solid #4CAF50;
            }
            QComboBox {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #666666;
            }
            QTabWidget::pane {
                border: 1px solid #4CAF50;
                border-radius: 5px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #E8E8E8;
                color: #666666;
                padding: 8px 20px;
                border: 1px solid #CCCCCC;
                border-bottom: none;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #4CAF50;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #C8E6C9;
            }
            QScrollArea {
                border: none;
            }
            QPlainTextEdit {
                background-color: #FAFAFA;
            }
            QListWidget {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                background-color: white;
            }
        """)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 创建选项卡
        tab_widget = QTabWidget()

        # 基础配置选项卡
        tab_widget.addTab(self.create_basic_config_tab(), "基础配置")

        # 参考图片选项卡
        tab_widget.addTab(self.create_images_tab(), "参考图片")

        # 视角提示词选项卡
        tab_widget.addTab(self.create_prompts_tab(), "视角提示词")

        # 置顶按钮（放在选项卡栏右侧）
        self.pin_btn = QPushButton("📌 置顶")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setFixedWidth(80)
        self.pin_btn.setFixedHeight(28)
        self.pin_btn.setStyleSheet("""
            QPushButton { background-color: #E0E0E0; color: #333; font-size: 11px; padding: 3px 8px; border-radius: 4px; }
            QPushButton:checked { background-color: #4CAF50; color: white; }
        """)
        self.pin_btn.clicked.connect(self.toggle_always_on_top)
        
        # 使用容器包裹按钮，设置合适的边距
        pin_container = QWidget()
        pin_container_layout = QHBoxLayout(pin_container)
        pin_container_layout.setContentsMargins(0, 2, 8, 2)
        pin_container_layout.addStretch()
        pin_container_layout.addWidget(self.pin_btn)
        
        # 将按钮容器放到选项卡的右上角
        tab_widget.setCornerWidget(pin_container, Qt.Corner.TopRightCorner)

        main_layout.addWidget(tab_widget)
        
        # 日志输出
        log_group = QGroupBox("日志输出")
        log_layout = QVBoxLayout()
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(133)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("开始生成")
        self.start_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.start_generation)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止生成")
        self.stop_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
            }
        """)
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        button_layout.addStretch()
        
        # 将状态标签放到按钮同一行右侧
        self.progress_label = QLabel("就绪")
        self.progress_label.setStyleSheet("color: #666666;")
        button_layout.addWidget(self.progress_label)
        
        main_layout.addLayout(button_layout)
        # 让日志输出区优先占用多余的纵向空间，减少底部空白
        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 1)
        main_layout.setStretch(2, 0)

    def create_basic_config_tab(self):
        """创建基础配置选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        scroll_area = QScrollArea()
        scroll_area.setWidget(widget)
        scroll_area.setWidgetResizable(True)
        
        # API 配置组
        api_group = QGroupBox("API 配置")
        api_layout = QVBoxLayout()
        
        api_url_layout = QHBoxLayout()
        api_url_layout.addWidget(QLabel("API 地址:"))
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setText(self.config.get("api_url", API_URL))
        api_url_layout.addWidget(self.api_url_edit)
        api_layout.addLayout(api_url_layout)
        
        auth_token_layout = QHBoxLayout()
        auth_token_layout.addWidget(QLabel("认证 Token:"))
        self.auth_token_edit = QLineEdit()
        # 显示时移除 "Bearer " 前缀
        token = self.config.get("auth_token", "")
        if token.startswith("Bearer "):
            self.auth_token_edit.setText(token[7:])
        else:
            self.auth_token_edit.setText(token)
        self.auth_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        auth_token_layout.addWidget(self.auth_token_edit)
        api_layout.addLayout(auth_token_layout)
        
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型名称:"))
        self.model_edit = QLineEdit()
        self.model_edit.setText(self.config.get("model", "jimeng-4.0"))
        model_layout.addWidget(self.model_edit)
        api_layout.addLayout(model_layout)
        
        api_group.setLayout(api_layout)
        layout.addWidget(api_group)
        
        # 生成参数组
        gen_group = QGroupBox("生成参数")
        gen_layout = QGridLayout()
        gen_layout.setSpacing(5)
        gen_layout.setColumnStretch(1, 1)
        gen_layout.setColumnStretch(3, 1)

        # 第一行：宽高比和分辨率（紧凑排列）
        gen_layout.addWidget(QLabel("宽高比:"), 0, 0)
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItems(RATIO_OPTIONS)
        self.ratio_combo.setCurrentText(self.config.get("ratio", "3:4"))
        gen_layout.addWidget(self.ratio_combo, 0, 1)

        gen_layout.addWidget(QLabel("分辨率:"), 0, 2)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTION_OPTIONS)
        self.resolution_combo.setCurrentText(self.config.get("resolution", "2k"))
        gen_layout.addWidget(self.resolution_combo, 0, 3)

        # 第二行：反向提示词（小框）
        gen_layout.addWidget(QLabel("反向提示词:"), 1, 0, Qt.AlignmentFlag.AlignTop)
        self.negative_prompt_edit = QPlainTextEdit()
        self.negative_prompt_edit.setPlainText(self.config.get("negative_prompt", ""))
        self.negative_prompt_edit.setMinimumHeight(40)
        self.negative_prompt_edit.setMaximumHeight(60)
        gen_layout.addWidget(self.negative_prompt_edit, 1, 1, 1, 3)

        gen_group.setLayout(gen_layout)
        layout.addWidget(gen_group)

        return scroll_area
    
    def create_images_tab(self):
        """创建参考图片选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 图片列表
        image_list_layout = QVBoxLayout()
        image_list_layout.addWidget(QLabel("参考图片列表:"))
        
        self.image_list_widget = ImageListWidget()
        self.image_list_widget.setMinimumHeight(200)
        for img in self.config.get("image_list", []):
            self.image_list_widget.addItem(img)
        image_list_layout.addWidget(self.image_list_widget, stretch=1)
        
        # 说明文字
        image_list_layout.addWidget(QLabel("提示: 支持拖拽图片或目录到列表中"))
        
        image_btn_layout = QHBoxLayout()
        self.add_image_btn = QPushButton("添加图片")
        self.add_image_btn.clicked.connect(self.add_image)
        image_btn_layout.addWidget(self.add_image_btn)
        
        self.add_images_btn = QPushButton("批量添加")
        self.add_images_btn.clicked.connect(self.add_images)
        image_btn_layout.addWidget(self.add_images_btn)
        
        self.remove_image_btn = QPushButton("移除选中")
        self.remove_image_btn.clicked.connect(self.remove_selected_image)
        image_btn_layout.addWidget(self.remove_image_btn)
        
        self.clear_image_btn = QPushButton("清空")
        self.clear_image_btn.clicked.connect(self.clear_images)
        image_btn_layout.addWidget(self.clear_image_btn)
        
        image_list_layout.addLayout(image_btn_layout)
        layout.addLayout(image_list_layout)
        
        return widget
    
    def create_prompts_tab(self):
        """创建视角提示词选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 提示词列表
        # 视角提示词列表垂直布局
        prompt_list_layout = QVBoxLayout()
        # 添加列表标题标签
        prompt_list_layout.addWidget(QLabel("视角提示词列表（勾选参与生成）:"))
        
        # 创建提示词列表控件（带复选框）
        self.prompt_list_widget = QListWidget()
        self.prompt_list_widget.setMinimumHeight(130)
        # 设置单选模式（一次只能选择一个提示词）
        self.prompt_list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        # 设置列表样式：边框、圆角、背景色、选中状态等
        self.prompt_list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #CCCCCC;  /* 边框颜色 */
                border-radius: 4px;  /* 圆角半径 */
                background-color: white;  /* 背景色 */
            }
            QListWidget::item {
                padding: 2px 8px;  /* 内边距 - 调小使列表项更密 */
                min-height: 15px;  /* 最小高度 */
                border-bottom: 1px solid #EEEEEE;  /* 底部分割线 */
                color: #333333;  /* 文字颜色 */
            }
            QListWidget::item:selected {
                background-color: #1565C0;  /* 选中时的背景色 */
                color: white;  /* 选中时的文字颜色 */
            }
            QListWidget::item:selected:!active {
                background-color: #1976D2;  /* 失去焦点时的选中背景色 */
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #E8F5E9;  /* 悬停时的背景色 */
            }
            QListWidget::indicator {
                width: 15px;  /* 复选框宽度 */
                height: 15px;  /* 复选框高度 */
                margin-right: 6px;  /* 右侧间距 */
            }
            QListWidget::indicator:unchecked {
                border: 2px solid #999999;  /* 未选中时的边框色 */
                border-radius: 4px;  /* 圆角 */
                background-color: white;  /* 背景色 */
            }
            QListWidget::indicator:checked {
                border: 2px solid #4CAF50;  /* 选中时的边框色 */
                border-radius: 4px;  /* 圆角 */
                background-color: #4CAF50;  /* 选中时的背景色 */
            }
        """)
        # 加载提示词列表（带复选框），从配置中读取已有提示词
        prompt_list = self.config.get("prompt_list", [])  # 获取提示词列表，默认为空列表
        for item in prompt_list:
            # 为每个提示词创建列表项
            list_item = QListWidgetItem(item['name'])
            # 启用复选框功能（ItemIsUserCheckable）
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # 根据配置设置复选框状态（勾选或未勾选）
            list_item.setCheckState(Qt.CheckState.Checked if item.get('checked', True) else Qt.CheckState.Unchecked)
            # 添加到列表控件
            self.prompt_list_widget.addItem(list_item)
        # 绑定选择变化事件：当用户选择不同提示词时触发
        self.prompt_list_widget.currentItemChanged.connect(self.on_prompt_selection_changed)
        # 绑定复选框状态变化事件：当勾选状态改变时触发
        self.prompt_list_widget.itemChanged.connect(self.on_prompt_item_changed)
        # 将列表控件添加到布局
        prompt_list_layout.addWidget(self.prompt_list_widget)

        # 提示词操作按钮水平布局
        prompt_btn_layout = QHBoxLayout()
        # 添加提示词按钮
        self.add_prompt_btn = QPushButton("添加提示词")
        # 绑定点击事件
        self.add_prompt_btn.clicked.connect(self.add_prompt)
        prompt_btn_layout.addWidget(self.add_prompt_btn)
        
        self.remove_prompt_btn = QPushButton("移除选中")
        self.remove_prompt_btn.clicked.connect(self.remove_selected_prompt)
        prompt_btn_layout.addWidget(self.remove_prompt_btn)
        
        self.edit_prompt_btn = QPushButton("编辑提示词")
        self.edit_prompt_btn.clicked.connect(self.edit_prompt)
        prompt_btn_layout.addWidget(self.edit_prompt_btn)
        
        prompt_list_layout.addLayout(prompt_btn_layout)
        layout.addLayout(prompt_list_layout)
        
        # 提示词编辑区域
        prompt_edit_layout = QVBoxLayout()
        prompt_edit_layout.addWidget(QLabel("提示词内容:"))
        self.prompt_edit_text = QTextEdit()
        prompt_edit_layout.addWidget(self.prompt_edit_text)
        layout.addLayout(prompt_edit_layout)
        
        return widget
    
    def add_image(self):
        """添加单张图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.webp)"
        )
        if file_path:
            self.image_list_widget.addItem(file_path)
    
    def add_images(self):
        """批量添加图片"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.webp)"
        )
        if file_paths:
            self.image_list_widget.addItems(file_paths)
    
    def remove_selected_image(self):
        """移除选中的图片"""
        current_row = self.image_list_widget.currentRow()
        if current_row >= 0:
            self.image_list_widget.takeItem(current_row)
    
    def clear_images(self):
        """清空图片列表"""
        self.image_list_widget.clear()
    
    def add_prompt(self):
        """添加提示词"""
        dialog = PromptDialog(self)
        if dialog.exec():
            name, prompt = dialog.get_data()
            if name and prompt:
                # 同步写入 config
                self.config.setdefault("prompt_list", []).append(
                    {"name": name, "prompt": prompt, "checked": True}
                )
                list_item = QListWidgetItem(name)
                list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                list_item.setCheckState(Qt.CheckState.Checked)
                self.prompt_list_widget.addItem(list_item)
    
    def on_prompt_selection_changed(self, current, _previous):
        """选中提示词时显示内容"""
        if current is None:
            return
        name = current.text()
        for item in self.config.get("prompt_list", []):
            if item['name'] == name:
                self.prompt_edit_text.setPlainText(item.get('prompt', ''))
                return
        self.prompt_edit_text.clear()

    def on_prompt_item_changed(self, item):
        """防止取消最后一个勾选"""
        if item.checkState() == Qt.CheckState.Unchecked:
            checked_count = sum(
                1 for i in range(self.prompt_list_widget.count())
                if self.prompt_list_widget.item(i).checkState() == Qt.CheckState.Checked
            )
            if checked_count == 0:
                self.prompt_list_widget.blockSignals(True)
                item.setCheckState(Qt.CheckState.Checked)
                self.prompt_list_widget.blockSignals(False)
                QMessageBox.warning(self, "提示", "至少需要保留一个勾选的提示词！")

    def remove_selected_prompt(self):
        """移除选中的提示词（需确认）"""
        current_row = self.prompt_list_widget.currentRow()
        if current_row < 0:
            return
        name = self.prompt_list_widget.item(current_row).text()
        reply = QMessageBox.question(
            self, "确认移除",
            f"确定要移除「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.prompt_list_widget.takeItem(current_row)
    
    def edit_prompt(self):
        """编辑提示词"""
        current_row = self.prompt_list_widget.currentRow()
        if current_row >= 0:
            name = self.prompt_list_widget.item(current_row).text()
            prompt = ""
            for item in self.config.get("prompt_list", []):
                if item['name'] == name:
                    prompt = item['prompt']
                    break
            
            dialog = PromptDialog(self, name, prompt)
            if dialog.exec():
                new_name, new_prompt = dialog.get_data()
                if new_name and new_prompt:
                    self.prompt_list_widget.item(current_row).setText(new_name)
                    # 同步更新 config 中的名称和提示词内容
                    for config_item in self.config.get("prompt_list", []):
                        if config_item['name'] == name:
                            config_item['name'] = new_name
                            config_item['prompt'] = new_prompt
                            break
                    # 刷新下方内容框
                    self.prompt_edit_text.setPlainText(new_prompt)
    
    def load_config_to_ui(self):
        """将配置加载到界面"""
        self.api_url_edit.setText(self.config.get("api_url", API_URL))
        self.auth_token_edit.setText(self.config.get("auth_token", ""))
        self.model_edit.setText(self.config.get("model", "jimeng-4.0"))
        self.ratio_combo.setCurrentText(self.config.get("ratio", "3:4"))
        self.resolution_combo.setCurrentText(self.config.get("resolution", "2k"))
        self.negative_prompt_edit.setPlainText(self.config.get("negative_prompt", ""))
        
        # 加载图片列表
        self.image_list_widget.clear()
        for img in self.config.get("image_list", []):
            self.image_list_widget.addItem(img)
        
        # 加载提示词列表（带复选框）
        self.prompt_list_widget.clear()
        prompt_list = self.config.get("prompt_list", [])
        for item in prompt_list:
            list_item = QListWidgetItem(item['name'])
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            list_item.setCheckState(Qt.CheckState.Checked if item.get('checked', True) else Qt.CheckState.Unchecked)
            self.prompt_list_widget.addItem(list_item)
    
    def save_config_from_ui(self):
        """从界面保存配置"""
        self.config["api_url"] = self.api_url_edit.text()

        # 保存 token 时自动添加 "Bearer " 前缀
        token = self.auth_token_edit.text().strip()
        if token and not token.startswith("Bearer "):
            token = f"Bearer {token}"
        self.config["auth_token"] = token

        self.config["model"] = self.model_edit.text()
        self.config["ratio"] = self.ratio_combo.currentText()
        self.config["resolution"] = self.resolution_combo.currentText()
        self.config["negative_prompt"] = self.negative_prompt_edit.toPlainText()

        # 保存图片列表
        image_list = []
        for i in range(self.image_list_widget.count()):
            image_list.append(self.image_list_widget.item(i).text())
        self.config["image_list"] = image_list

        # 保存提示词列表
        prompt_list = []
        for i in range(self.prompt_list_widget.count()):
            item = self.prompt_list_widget.item(i)
            name = item.text()
            checked = item.checkState() == Qt.CheckState.Checked
            prompt = ""
            # 从配置中查找对应的提示词
            for config_item in self.config.get("prompt_list", []):
                if config_item['name'] == name:
                    prompt = config_item.get('prompt', '')
                    break
            prompt_list.append({"name": name, "prompt": prompt, "checked": checked})
        self.config["prompt_list"] = prompt_list
        
        # 保存到文件
        self.config_manager.save_config(self.config)
    
    def start_generation(self):
        """开始生成"""
        self.save_config_from_ui()
        self._stop_requested = False
        
        # 验证必要配置
        if not self.config.get("image_list"):
            QMessageBox.warning(self, "警告", "请添加参考图片！")
            return
        
        # 获取勾选的提示词
        checked_prompts = [p for p in self.config.get("prompt_list", []) if p.get('checked', True)]
        if not checked_prompts:
            QMessageBox.warning(self, "警告", "请至少勾选一个视角提示词！")
            return
        
        if not self.config.get("auth_token"):
            QMessageBox.warning(self, "警告", "请填写认证 Token！")
            return
        
        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # 清空日志
        self.log_text.clear()
        self.log_text.appendPlainText("=" * 60)
        self.log_text.appendPlainText("即梦 AI 生图工具")
        self.log_text.appendPlainText("=" * 60)
        self.log_text.appendPlainText(f"\n开始生成图片...")
        self.log_text.appendPlainText(f"参考图片: {len(self.config.get('image_list', []))} 张")
        self.log_text.appendPlainText(f"提示词数量: {len(checked_prompts)} 个")
        
        # 创建并启动工作线程
        self.generator_thread = ImageGeneratorThread(self.config)
        self.generator_thread.log_signal.connect(self.log_message)
        self.generator_thread.progress_signal.connect(self.update_progress)
        self.generator_thread.finished_signal.connect(self.generation_finished)
        self.generator_thread.error_signal.connect(self.generation_error)
        self.generator_thread.start()
    
    def stop_generation(self):
        """停止生成"""
        if self.generator_thread and self.generator_thread.isRunning():
            self._stop_requested = True
            self.generator_thread.stop()
            self.stop_btn.setEnabled(False)
            self.progress_label.setText("停止中")
            self.log_text.appendPlainText("\n正在停止生成...")
    
    def log_message(self, message):
        """日志消息"""
        self.log_text.appendPlainText(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def update_progress(self, current, total):
        """更新进度"""
        self.progress_label.setText(f"进度: {current}/{total}")
    
    def generation_finished(self, saved_paths):
        """生成完成"""
        if self._stop_requested:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_label.setText("已停止")

            self.log_text.appendPlainText("\n" + "=" * 60)
            self.log_text.appendPlainText("生成已停止")
            self.log_text.appendPlainText("=" * 60)
            self.log_text.appendPlainText(f"已生成图片: {len(saved_paths)} 张")

            if saved_paths:
                self.log_text.appendPlainText(f"\n保存路径:")
                for path in saved_paths:
                    self.log_text.appendPlainText(f"  - {path}")

            self._stop_requested = False
            return

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_label.setText("生成完成")

        self.log_text.appendPlainText("\n" + "=" * 60)
        self.log_text.appendPlainText("生成完成！")
        self.log_text.appendPlainText("=" * 60)
        self.log_text.appendPlainText(f"总共生成图片: {len(saved_paths)} 张")

        if saved_paths:
            self.log_text.appendPlainText(f"\n保存路径:")
            for path in saved_paths:
                self.log_text.appendPlainText(f"  - {path}")

        # 使用自动关闭弹窗
        if saved_paths:
            msg_box = AutoCloseMessageBox(
                "完成",
                f"生成完成！共生成 {len(saved_paths)} 张图片",
                self,
                timeout=3000
            )
            msg_box.exec()
        self._stop_requested = False
    
    def generation_error(self, error_msg):
        """生成错误"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_label.setText("错误")
        
        self.log_text.appendPlainText(f"\n❌ 错误: {error_msg}")
        QMessageBox.critical(self, "错误", f"生成失败: {error_msg}")
    
    def toggle_always_on_top(self):
        """切换窗口置顶"""
        geom = self.geometry()
        was_maximized = self.isMaximized()
        was_minimized = self.isMinimized()
        self.setUpdatesEnabled(False)
        try:
            if self.pin_btn.isChecked():
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                self.pin_btn.setText("📌 已置顶")
            else:
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
                self.pin_btn.setText("📌 置顶")
            self.show()
            if was_maximized:
                self.showMaximized()
            elif was_minimized:
                self.showMinimized()
            else:
                self.setGeometry(geom)
        finally:
            self.setUpdatesEnabled(True)

    def closeEvent(self, event):
        """关闭事件"""
        if self.generator_thread and self.generator_thread.isRunning():
            self.generator_thread.stop()
            self.generator_thread.wait()
        try:
            self.save_config_from_ui()
        except Exception:
            pass
        event.accept()


class PromptDialog(QDialog):
    """提示词编辑对话框"""
    
    def __init__(self, parent=None, name="", prompt=""):
        super().__init__(parent)
        self.setWindowTitle("编辑提示词")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # 名称输入
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("名称:"))
        self.name_edit = QLineEdit(name)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # 提示词输入
        layout.addWidget(QLabel("提示词:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(prompt)
        self.prompt_edit.setMinimumHeight(200)
        layout.addWidget(self.prompt_edit)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
    
    def get_data(self):
        """获取输入数据"""
        return self.name_edit.text(), self.prompt_edit.toPlainText()


# ==================== 主函数 ====================

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
