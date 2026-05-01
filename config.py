import os
import re
from pathlib import Path

import numpy as np

from ok import ConfigOption
from qfluentwidgets import FluentIcon
from src.task.process_feature import process_feature

version = "dev"


def calculate_pc_exe_path(running_path):
    game_exe_folder = Path(running_path).parents[3]
    return str(game_exe_folder / "Wuthering Waves.exe")


def make_bottom_right_black(frame):
    """
    Changes a portion of the frame's pixels at the bottom right to black.

    Args:
        frame: The input frame (NumPy array) from OpenCV.

    Returns:
        The modified frame with the bottom-right corner blackened.  Returns the original frame
        if there's an error (e.g., invalid frame).
    """
    try:
        height, width = frame.shape[:2]  # Get height and width

        # Calculate the size of the black rectangle
        black_width = int(0.13 * width)
        black_height = int(0.025 * height)

        # Calculate the starting coordinates of the rectangle
        start_x = width - black_width
        start_y = height - black_height

        # Create a black rectangle (NumPy array of zeros)
        black_rect = np.zeros((black_height, black_width, frame.shape[2]), dtype=frame.dtype)  # Ensure same dtype

        # Replace the bottom-right portion of the frame with the black rectangle
        frame[start_y:height, start_x:width] = black_rect

        return frame
    except Exception as e:
        print(f"Error processing frame: {e}")
        return frame


key_config_option = ConfigOption('Game Hotkey Config', {
    'Echo Key': 'q',
    'Liberation Key': 'r',
    'Resonance Key': 'e',
    'Tool Key': 't',
    'Jump Key': 'space',
    'Dodge Key': 'lshift',
    'Wheel Key': 'tab',
}, description='In Game Hotkey for Skills')

char_config_option = ConfigOption('Character Config', {
    'Iuno C6': False,
    'Verina C2': False,
    'Chisa DPS': False,
}, description='Character Config')

pick_echo_config_option = ConfigOption('Pick Echo Config', {
    'Use OCR': True
}, config_description={
    'Use OCR': 'Turn on if your CPU is Powerful for more accuracy'}, description='Turn on to enable auto pick echo')

monthly_card_config_option = ConfigOption('Monthly Card Config', {
    'Check Monthly Card': True,
    'Monthly Card Time': 4
}, description='Turn on to avoid interruption by monthly card when executing tasks', config_description={
    'Check Monthly Card': 'Check for monthly card to avoid interruption of tasks',
    'Monthly Card Time': 'Your computer\'s local time when the monthly card will popup, hour in (1-24)'
})

def apply_low_quality():
    from src.utils import graphics_helper
    from ok import og
    from ok.gui.util.Alert import alert_info
    
    config = og.global_config.get_config('画质优化配置')
    game_path = config.get('游戏路径')
    
    if not game_path:
        alert_info("❌ 请先填写游戏路径并保存！")
        return
        
    graphics_helper.ensure_presets(game_path)
    if graphics_helper.apply_preset('low', game_path):
        alert_info("✅ 已成功切换为【低画质】！")

def restore_original_quality():
    from src.utils import graphics_helper
    from ok import og
    from ok.gui.util.Alert import alert_info
    
    config = og.global_config.get_config('画质优化配置')
    game_path = config.get('游戏路径')
    
    if not game_path:
        alert_info("❌ 请先填写游戏路径并保存！")
        return
        
    if graphics_helper.apply_preset('original', game_path):
        alert_info("✅ 已成功恢复为【原画质】！")

graphics_config_option = ConfigOption('画质优化配置', {
    '游戏路径': r'',
    '手动即时控制': '',
    '自动优化 (游戏启动时)': True,
    '自动还原 (游戏退出时)': True,
}, description='画质优化全局设置', config_description={
    '游戏路径': '鸣潮游戏安装路径 (例如: E:\\Wuthering Waves)',
    '手动即时控制': '点击右侧按钮立即应用配置，无需启动任务',
    '自动优化 (游戏启动时)': '开启后，当从本应用内启动游戏时，将自动切换为低画质',
    '自动还原 (游戏退出时)': '开启后，当游戏运行结束，将自动恢复原画质配置'
}, config_type={
    '手动即时控制': {
        'type': 'button',
        'buttons': [
            {'text': '切换低画质', 'callback': apply_low_quality},
            {'text': '恢复原画质', 'callback': restore_original_quality}
        ]
    }
})

# --- GUI 启动拦截钩子 (区分手动启动与助手启动) ---
try:
    import ok.gui.StartController as sc
    from ok import og
    import logging
    
    _hook_logger = logging.getLogger("GraphicsHook")
    _original_start_device = sc.StartController.start_device
    
    def _patched_start_device(self):
        try:
            from src.utils import graphics_helper
            # 只有当游戏还没启动时，才执行画质替换
            is_running = graphics_helper.is_game_running()

            # 从全局配置中心读取设置
            if og.global_config:
                graphics_config = og.global_config.get_config('画质优化配置')
                if graphics_config and graphics_config.get('自动优化 (游戏启动时)') and not is_running:
                    game_path = graphics_config.get('游戏路径')
                    if game_path:
                        _hook_logger.info("🚀 [GUI 拦截] 检查到游戏尚未启动，正在同步低画质配置...")
                        graphics_helper.ensure_presets(game_path)
                        graphics_helper.apply_preset('low', game_path)
        except Exception as e:
            _hook_logger.error(f"画质同步拦截失败: {e}")
            
        return _original_start_device(self)

    # 替换原有的启动方法
    sc.StartController.start_device = _patched_start_device
except Exception as e:
    print(f"无法挂载 GUI 启动拦截器: {e}")


config = {
    'debug': False,  # Optional, default: False
    'use_gui': True,
    'config_folder': 'configs',
    'screenshot_processor': make_bottom_right_black,
    'gui_icon': 'icon.png',
    'global_configs': [key_config_option, char_config_option, pick_echo_config_option, monthly_card_config_option, graphics_config_option],
    'ocr': {
        'lib': 'onnxocr',
        'auto_simplify': True,
        'params': {
            'use_openvino': True,
            'use_npu': True,
        }
    },
    'my_app': ['src.globals', 'Globals'],
    'start_timeout': 120,  # default 60
    'wait_until_settle_time': 0,
    # required if using feature detection
    'template_matching': {
        'coco_feature_json': os.path.join('assets', 'coco_annotations.json'),
        'default_horizontal_variance': 0.002,
        'default_vertical_variance': 0.002,
        'default_threshold': 0.8,
        'feature_processor': process_feature,
        'vcenter_features': ['monthly_card'],
        'hcenter_features': ['monthly_card']
    },
    'windows': {  # required  when supporting windows game
        'top_hwnd_class': [re.compile('CAgreementDlg'), re.compile('CLoginDlg_P_'),
                           'CefBrowserWindow', 'Chrome_RenderWidgetHostHWND',
                           re.compile('CNativeLoginDlg'), 'ComboLBox', '#32770'
                           ],
        'calculate_pc_exe_path': calculate_pc_exe_path,
        'exe': 'Client-Win64-Shipping.exe',
        'hwnd_class': 'UnrealWindow',
        'interaction': 'PostMessage',
        'capture_method': ['WGC', 'BitBlt_RenderFull'],  # Windows版本支持的话, 优先使用WGC, 否则使用BitBlt_Full
        'check_hdr': False,
        'force_no_hdr': False,
        'check_night_light': True,
        'force_no_night_light': False,
    },
    'window_size': {
        'width': 1200,
        'height': 800,
        'min_width': 1200,
        'min_height': 800,
    },
    'supported_resolution': {
        'ratio': '16:9',
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],
        'min_size': (1280, 720)
    },
    'links': {
        'default': {
            'github': 'https://github.com/ok-oldking/ok-wuthering-waves',
            'discord': 'https://discord.gg/vVyCatEBgA',
            'sponsor': 'https://patreon.com/ok_oldking',
            'share': 'Download OK-WW from https://github.com/ok-oldking/ok-wuthering-waves/releases/latest',
            'faq': 'https://github.com/ok-oldking/ok-wuthering-waves/blob/master/README_en.md'
        },
        'zh_CN': {
            'github': 'https://github.com/ok-oldking/ok-wuthering-waves',
            'discord': 'https://discord.gg/vVyCatEBgA',
            'sponsor': 'https://afdian.com/a/ok-oldking',
            'share': 'OK-WW 夸克网盘下载：https://pan.quark.cn/s/75b55ef72a34 GitHub下载: https://github.com/ok-oldking/ok-wuthering-waves/releases/latest',
            'faq': 'https://cnb.cool/ok-oldking/ok-wuthering-waves/-/blob/main/README.md',
            'qq_group': 'https://qm.qq.com/q/QUMHZ9IJYO',
            'qq_channel': 'https://pd.qq.com/s/djmm6l44y',
        },
    },
    'about': """
    <p style="color:red;">
    <strong>本软件是免费开源的。</strong> 如果你被收费，请立即退款。请访问QQ频道或GitHub下载最新的官方版本。
    </p>
    <p style="color:red;">
        <strong>本软件仅供个人使用，用于学习Python编程、计算机视觉、UI自动化等。</strong> 请勿将其用于任何营利性或商业用途。
    </p>
    <p style="color:red;">
        <strong>使用本软件可能会导致账号被封。</strong> 请在了解风险后再使用。
    </p>
""",
    'screenshots_folder': "screenshots",
    'gui_title': 'OK-WW',  # Optional
    # 'coco_feature_folder': get_path(__file__, 'assets/coco_feature'),  # required if using feature detection
    'log_file': 'logs/ok-ww.log',  # Optional, auto rotating every day
    'error_log_file': 'logs/ok-ww_error.log',
    'launcher_log_file': 'logs/launcher.log',
    'launcher_error_log_file': 'logs/launcher_error.log',
    'version': version,
    'onetime_tasks': [  # tasks to execute
        ["src.task.DailyTask", "DailyTask"],
        ["src.task.MultiAccountDailyTask", "MultiAccountDailyTask"],
        ["src.task.FarmEchoTask", "FarmEchoTask"],
        ["src.task.AutoRogueTask", "AutoRogueTask"],
        ["src.task.ForgeryTask", "ForgeryTask"],
        ["src.task.NightmareNestTask", "NightmareNestTask"],
        ["src.task.SimulationTask", "SimulationTask"],
        ["src.task.TacetTask", "TacetTask"],
        ["src.task.EnhanceEchoTask", "EnhanceEchoTask"],
        ["src.task.ChangeEchoTask", "ChangeEchoTask"],
        ["src.task.DiagnosisTask", "DiagnosisTask"],
    ], 'trigger_tasks': [
        ["src.task.AutoCombatTask", "AutoCombatTask"],
        ["src.task.AutoPickTask", "AutoPickTask"],
        ["src.task.SkipDialogTask", "AutoDialogTask"],
        ["src.task.AutoLoginTask", "AutoLoginTask"],
        ["src.task.MouseResetTask", "MouseResetTask"],
        ["src.task.FastTravelTask", "FastTravelTask"],
    ], 'scene': ["src.scene.WWScene", "WWScene"],
}

# 启动后台画质监控守护进程
try:
    from src.utils import graphics_helper
    graphics_helper.start_exit_monitor()
except Exception as e:
    print(f"Failed to start graphics exit monitor: {e}")
