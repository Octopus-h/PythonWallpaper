import ast
import sys
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Tuple

from win32com.client import Dispatch

# ===================== 路径函数 =====================
def get_app_root_path():
    """获取程序根目录"""
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后的运行环境
        app_root = os.path.dirname(sys.executable)
    else:
        # 开发环境（脚本运行）
        app_root = os.path.dirname(os.path.abspath(__file__))
    return app_root

# ===================== 日志配置（输出到last.log文件） =====================
# 日志文件路径：程序根目录/last.log
log_file_path = os.path.join(get_app_root_path(), "last.log")
# 配置日志：输出到文件，追加模式，UTF-8编码，不存在则自动创建
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            filename=log_file_path,
            maxBytes=256 * 1024,     # 日志最大大小
            backupCount=1,           # 备份数
            mode='a',                # 追加模式（不会覆盖原有日志）
            encoding='utf-8'         # 确保中文正常显示
        )
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"程序启动，日志文件路径：{log_file_path}")  # 启动时记录日志路径

# ===================== JSON配置相关 =====================
def get_config_path():
    """获取配置文件路径（保存在程序下的resources文件夹）"""
    app_root = get_app_root_path()
    config_dir = os.path.join(app_root, "resources")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.json")
    logger.info(f"配置文件路径：{config_path}")
    return config_path

def init_config_file():
    """初始化配置文件（文件不存在时创建空配置）"""
    try:
        config_path = get_config_path()
        if not os.path.exists(config_path):
            default_config = {
                "last_wallpaper_path": "",
                "update_time": "",
                "type": ""
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            logger.info(f"配置文件不存在，已自动创建：{config_path}")
        return True
    except PermissionError:
        logger.error("创建配置文件失败：没有写入权限！请以管理员身份运行程序")
        return False
    except Exception as e:
        logger.error(f"创建配置文件失败：{e}")
        return False

def update_config(**kwargs):
    """
    更新配置文件中的键值对（追加或修改）。
    可以传入任意数量的关键字参数，每个参数将作为键值对写入配置文件。
    如果配置文件不存在，会自动创建；如果文件已存在，原有键值会被保留，只有传入的键被更新或追加。
    
    示例：
        update_config(last_wallpaper_path="C:\\video.mp4", type="video")
        update_config(volume=80, autoplay=True)
    """
    config_path = get_config_path()
    # 确保配置目录存在（get_config_path 内部已创建，这里再次确保）
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # 读取现有配置（如果文件存在且格式正确）
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"读取配置文件失败，将重建新配置: {e}")
            config = {}   # 文件损坏，重新开始

    # 更新传入的键值对
    config.update(kwargs)

    # 写回文件
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"配置文件已更新: {config_path}，{config}，{f}")
    except PermissionError:
        logger.error("更新配置文件失败：没有写入权限！请以管理员身份运行程序")
    except Exception as e:
        logger.error(f"更新配置文件失败：{e}")

def save_wallpaper_path(wallpaper_path: str, save_type: str,):
    """
    :param wallpaper_path: 壁纸路径
    :type wallpaper_path: str
    :param save_type: 壁纸类型
    :type save_type: str
    :rtype: Any | None
    """
    if not init_config_file():
        return
    try:
        config_path = get_config_path()
        update_config(last_wallpaper_path=wallpaper_path,
                      update_time=str(os.path.getmtime(wallpaper_path)),
                      type=save_type
                      )
        logger.info(f"壁纸路径已保存到程序目录：{config_path}")
    except PermissionError:
        logger.error("保存配置文件失败：没有写入权限！请以管理员身份运行程序")
    except Exception as e:
        logger.error(f"保存配置文件失败：{e}")

def load_wallpaper_path() -> Tuple[Optional[str], Optional[str]]:
    """
    从JSON配置文件读取壁纸路径和类型（不存在则先创建）
    :return: 有效时返回 (wallpaper_path, wallpaper_type)，无效返回 None
    """
    # 确保配置文件存在
    init_config_file()
    config_path = get_config_path()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 读取配置
        wallpaper_path = config_data.get("last_wallpaper_path", "").strip()
        wallpaper_type = config_data.get("type", "").strip()

        # 校验壁纸路径
        if not wallpaper_path or not os.path.isfile(wallpaper_path):
            if wallpaper_path:
                logger.warning(f"配置文件中的路径无效（文件不存在）：{wallpaper_path}")
            else:
                logger.info("配置文件中无有效壁纸路径")
            return None, None

        # 最终校验通过
        logger.info(f"从配置文件加载成功：路径={wallpaper_path}，类型={wallpaper_type}")
        return wallpaper_path, wallpaper_type

    except json.JSONDecodeError:
        logger.error(f"配置文件格式错误（JSON解析失败）：{config_path}，重建配置文件")
        init_config_file()  # 重建配置
        return None, None  # 重建后无有效路径，返回None

    except PermissionError:
        logger.error(f"无权限读取配置文件：{config_path}（请以管理员身份运行）")
        return None, None

    except FileNotFoundError:
        logger.error(f"配置文件不存在（重建失败）：{config_path}")
        return None, None

    except Exception as e:
        logger.error(f"读取配置文件未知错误：\n\t {e} \n\t（路径={config_path}）")
        return None, None


def get_startup_folder():
    """返回当前用户的启动文件夹路径"""
    return os.path.join(os.environ['APPDATA'], 
                        r'Microsoft\\Windows\\Start Menu\\Programs\\Startup')

def get_shortcut_path():
    """返回本程序在启动文件夹中应创建的快捷方式路径"""
    return os.path.join(get_startup_folder(), '动态壁纸.lnk')

def is_autostart_enabled():
    """检查是否已设置开机自启（快捷方式是否存在）"""
    path = get_shortcut_path()
    enabled = os.path.exists(path)
    logger.debug(f"开机自启状态检查: {path} 是否存在 = {enabled}")
    return enabled

def set_autostart(enable: bool):
    shortcut_path = get_shortcut_path()
    try:
        if enable:
            if not os.path.exists(shortcut_path):
                # 使用 win32com.client 创建快捷方式
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = sys.executable
                shortcut.Arguments = f'"{os.path.abspath(sys.argv[0])}"'
                shortcut.WorkingDirectory = os.path.dirname(sys.executable)
                shortcut.Description = '动态壁纸'
                shortcut.save()
                logger.info(f"开机自启已启用，快捷方式创建于: {shortcut_path}")
            else:
                logger.debug("开机自启快捷方式已存在，无需重复创建")
        else:
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                logger.info(f"开机自启已禁用，快捷方式已删除: {shortcut_path}")
            else:
                logger.debug("开机自启快捷方式不存在，无需删除")
    except Exception as e:
        logger.exception(f"设置开机自启失败 (enable={enable})")
        raise

def check_NOT_USE_WX(file_path):
    """检查脚本文件中是否定义了 NOT_USE_WX = True，而不实际执行脚本"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'NOT_USE_WX':
                        if isinstance(node.value, ast.Constant) and node.value.value is True:
                            return True
    except Exception as e:
        logger.warning(f"检查 NOT_USE_WX 时出错: {e}")
    return False