import shutil
import os
import stat
import threading
import time
import psutil
from pathlib import Path
from ok import Logger, og

def is_game_running():
    """检查游戏进程是否正在运行"""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] == 'Client-Win64-Shipping.exe':
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

# 记录是否由本脚本应用了低画质（用于退出还原的精准判断）
_is_low_applied_by_script = False
_monitor_thread_started = False

logger = Logger.get_logger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
PRESET_DIR = BASE_DIR / "config_presets"
LOW_PATH = PRESET_DIR / "low_efficiency"
ORIGINAL_PATH = PRESET_DIR / "original"

FILES_TO_REPLACE = [
    "Config/WindowsNoEditor/Engine.ini",
    "Config/WindowsNoEditor/GameUserSettings.ini",
    "LocalStorage/LocalStorage.db",
    "LocalStorage/LocalStorage2.db"
]

def get_target_dir(game_path):
    if not game_path:
        return None
    return Path(game_path) / "Wuthering Waves Game" / "Client" / "Saved"

def ensure_presets(game_path):
    PRESET_DIR.mkdir(exist_ok=True)
    LOW_PATH.mkdir(exist_ok=True)
    ORIGINAL_PATH.mkdir(exist_ok=True)
    
    target_dir = get_target_dir(game_path)
    if not target_dir or not target_dir.exists():
        return
        
    for rel_path in FILES_TO_REPLACE:
        original_file = ORIGINAL_PATH / rel_path
        if not original_file.exists():
            game_file = target_dir / rel_path
            if game_file.exists():
                logger.info(f"Backing up original config: {rel_path}")
                original_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(game_file, original_file)
        
        # Ensure low preset existence (even if empty, user should fill it)
        low_file = LOW_PATH / rel_path
        if not low_file.exists():
            logger.info(f"Creating placeholder for {rel_path}")
            low_file.parent.mkdir(parents=True, exist_ok=True)
            with open(low_file, 'w') as f:
                pass

def apply_preset(preset_name, game_path):
    target_dir = get_target_dir(game_path)
    if not target_dir or not target_dir.exists():
        logger.error(f"Game config directory not found: {target_dir}")
        return False
        
    preset_path = LOW_PATH if preset_name == 'low' else ORIGINAL_PATH
    if not preset_path.exists():
        logger.error(f"Preset directory not found: {preset_path}")
        return False
        
    success = True
    for rel_path in FILES_TO_REPLACE:
        src = preset_path / rel_path
        dst = target_dir / rel_path
        
        if not src.exists():
            # If original doesn't exist but game file does, we should have backed it up
            if preset_name != 'low':
                logger.warning(f"Source preset file not found: {src}")
                success = False
            continue

        try:
            # Check for empty files
            if os.path.getsize(src) == 0:
                if preset_name == 'low':
                    # Never copy empty DB or INI for low quality
                    logger.warning(f"Low-efficiency preset {rel_path} is empty, skipping.")
                    continue
            
            # If target exists, make sure it's not read-only so we can overwrite it
            if dst.exists():
                os.chmod(dst, stat.S_IWRITE)
            
            # Make sure destination parent directory exists
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            # Perform copy
            shutil.copy2(src, dst)
            
            # Cleanup journal files for DB to prevent 'distortion'
            if rel_path.endswith('.db'):
                journal = dst.with_name(dst.name + "-journal")
                if journal.exists():
                    os.chmod(journal, stat.S_IWRITE)
                    os.remove(journal)
                    logger.debug(f"Removed SQLite journal: {journal}")

            # Set read-only for low quality INIs
            if preset_name == 'low' and rel_path.endswith('.ini'):
                os.chmod(dst, stat.S_IREAD)
            else:
                os.chmod(dst, stat.S_IWRITE)
                
            logger.info(f"Successfully applied {preset_name} preset: {src}")
        except Exception as e:
            logger.error(f"Error applying {rel_path}: {e}")
            success = False
            
    if success:
        # 如果是成功切换到了低画质，标记一下，方便后续退出还原
        if preset_name == 'low':
            global _is_low_applied_by_script
            _is_low_applied_by_script = True
        elif preset_name == 'original':
            _is_low_applied_by_script = False
            
    return success

def start_exit_monitor():
    """启动全局退出监控线程 (单例)"""
    global _monitor_thread_started
    if _monitor_thread_started:
        return
    _monitor_thread_started = True
    
    def monitor_loop():
        # 给初始化留一点点时间
        time.sleep(5)
        last_game_running = False
        while True:
            time.sleep(2)
            try:
                # 检查游戏进程
                is_running = is_game_running()
                
                # 状态转换：游戏从运行变为停止
                if not is_running and last_game_running:
                    global _is_low_applied_by_script
                    # 只有当我们之前改过画质，且开启了自动还原时才处理
                    config = og.global_config.get_config('画质优化配置')
                    if config and config.get('自动还原 (游戏退出时)') and _is_low_applied_by_script:
                        game_path = config.get('游戏路径')
                        if game_path:
                            og.logger.info("🌱 [后台监控] 游戏已退出，正在将画质撤回到原始状态...")
                            apply_preset('original', game_path)
                            _is_low_applied_by_script = False # 恢复后重置标记
                
                last_game_running = is_running
            except Exception:
                pass

    thread = threading.Thread(target=monitor_loop, name="GraphicsExitMonitor", daemon=True)
    thread.start()

def _on_assistant_exit():
    """当助手退出时（无论是正常关闭还是崩溃），执行最后的清理工作"""
    global _is_low_applied_by_script
    if _is_low_applied_by_script:
        try:
            # 此时 logger 可能已失效，使用 print 记录到控制台
            if og.global_config:
                config = og.global_config.get_config('画质优化配置')
                if config and config.get('自动还原 (游戏退出时)'):
                    game_path = config.get('游戏路径')
                    if game_path:
                        print("🧹 [系统退出] 检测到助手正在关闭，正在紧急还原原始画质配置...")
                        apply_preset('original', game_path)
                        _is_low_applied_by_script = False
        except Exception as e:
            print(f"退出还原失败: {e}")

# 注册退出钩子 (atexit 比 daemon 线程更可靠)
import atexit
atexit.register(_on_assistant_exit)
