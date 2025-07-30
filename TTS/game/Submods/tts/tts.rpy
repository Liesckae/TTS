init -990 python in mas_submod_utils:
    Submod(
        author="Nullblock",
        name="TTS",
        description="让莫妮卡可以说话,需要项目GPT-SoVITS,作者见{a=https://github.com/RVC-Boss/GPT-SoVITS}{i}{u}>Github{/a}{/i}{/u}.",
        version="0.5.1",
    )

init -989 python in mas_submod_utils:
    # 初始化以及定义工具函数 
    import subprocess
    import logging
    import threading
    import sys
    import os
    import time
    import re

    # 创建线程队列
    class SimpleQueue:
        def __init__(self):
            self._items = []
            self._lock = threading.Lock()
        def put(self, item):
            with self._lock:
                self._items.append(item)
        def get_nowait(self):
            with self._lock:
                if self._items:
                    return self._items.pop(0)
                raise Exception("Queue empty")
        def empty(self):
            with self._lock:
                return len(self._items) == 0

    # 全局变量
    _api_process = None
    _tts_thread = None
    _tts_stop_event = threading.Event()
    _audio_queue = SimpleQueue()
    _tts_player_process = None
    tts_initialized = False
    last_dialogue_hash = 0

    # 设置日志
    LOG_DIR = os.path.join(renpy.config.basedir, 'log')
    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR)
        except:
            pass
            
    try:
        logging.basicConfig(
            filename=os.path.join(LOG_DIR, '%s.log' % time.strftime('%Y-%m-%d')),
            format='%(asctime)s - %(name)s - %(message)s',
            level=logging.INFO
        )
    except:
        pass
        
    logger = logging.getLogger('TTS')
    logger.info('TTS模块已初始化')

init -988 python in mas_submod_utils:
    import sys
    import os
    import time
    import subprocess
    import renpy.store as store
    try:
        import ConfigParser as configparser
    except ImportError:
        import configparser

    # ---------- 文本过滤函数 ----------
    def filter_renpy_special_tags(text):
        """
        清理Ren'Py特殊标记的文本过滤函数
        移除所有Ren'Py特殊标记，只保留纯文本内容
        """
        if not text:
            return ""
        try:
            import re
            text = re.sub(r'\{[^}]*\}', '', text)
            text = re.sub(r'<[^>]*>', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            text = text.replace('  ', ' ')
            text = text.replace(' ,', ',')
            text = text.replace(' .', '.')
            if len(text) < 2:
                return ""
            return text
        except:
            return text

    # ---------- 工具 ----------
    def clear_cache():
        cache_dir = os.path.join(renpy.config.basedir, 'cache')
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
                logger.info('创建缓存目录: %s' % cache_dir)
            except Exception, e:
                logger.error('创建缓存目录失败: %s' % str(e))
        else:
            try:
                files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir) 
                        if f.endswith('.wav') and os.path.isfile(os.path.join(cache_dir, f))]
                files.sort(key=lambda x: os.path.getmtime(x))
                for f in files[:-10]:
                    try:
                        os.remove(f)
                        logger.info('已删除旧缓存文件: %s' % f)
                    except Exception, e:
                        logger.error('删除文件失败: %s - %s' % (f, str(e)))
                logger.info('缓存目录已清理，保留最近10个文件')
            except Exception, e:
                logger.error('清理缓存目录失败: %s' % str(e))

    def read_cfg():
        ini = os.path.join(renpy.config.basedir, 'config.ini')
        if not os.path.exists(ini):
            logger.error('配置文件 %s 不存在' % ini)
            return None
        try:
            cp = configparser.ConfigParser()
            cp.read(ini)
            
            if not cp.has_section('GPT_SOVITS'):
                logger.error('配置文件缺少 [GPT_SOVITS] 部分')
                return None
                
            required_keys = ['root_path', 'refer_audio_path', 'refer_text', 'refer_text_language']
            for key in required_keys:
                if not cp.has_option('GPT_SOVITS', key):
                    logger.error('配置文件缺少 %s 选项' % key)
                    return None
            return cp
        except Exception, e:
            logger.error('读取配置文件失败: %s' % str(e))
            return None

    def launch_api(cp):
        global _api_process
        if _api_process:
            try:
                logger.info("检测到已有API进程，正在终止...")
                _api_process.terminate()
                time.sleep(1)
                if _api_process.poll() is None:
                    logger.warning("API进程未正常终止，尝试强制结束")
                    _api_process.kill()
            except Exception, e:
                logger.error("终止旧API进程失败: %s" % str(e))
            finally:
                _api_process = None

        try:
            root = os.path.abspath(cp.get('GPT_SOVITS', 'root_path'))
        except Exception, e:
            logger.error("获取root_path配置失败: %s" % str(e))
            return None

        logger.info('GPT-SoVITS根目录: %s' % root)
        if not os.path.exists(root):
            logger.error('GPT-SoVITS根目录不存在: %s' % root)
            return None

        api_script = os.path.join(root, 'api_v2.py')
        if not os.path.exists(api_script):
            logger.error('API脚本不存在: %s' % api_script)
            return None

        if sys.platform == "win32":
            python_exe = os.path.join(root, 'runtime', 'python.exe')
            if not os.path.exists(python_exe):
                python_exe = os.path.join(root, 'runtime', 'pythonw.exe')
                if not os.path.exists(python_exe):
                    python_exe = 'python.exe'
        else:
            python_exe = 'python'

        cmd = [
            python_exe,
            api_script,
            '-a', '127.0.0.1',
            '-p', '9880'
        ]

        logger.info('启动API命令: %s' % ' '.join(cmd))
        try:
            _api_process = subprocess.Popen(
                cmd,
                cwd=root,
                bufsize=0
            )
            logger.info('API进程已启动，PID: %d' % _api_process.pid)
            return _api_process
        except Exception, e:
            logger.error('启动API进程失败: %s' % str(e))
            return None

    # 新增：自动启动 TTS 播放器（使用系统 Python）
    def start_tts_player():
        """自动启动外部 TTS 播放器脚本（优先使用 Python 3）"""
        global _tts_player_process
        
        # 检查是否已经有运行中的播放器
        if _tts_player_process and _tts_player_process.poll() is None:
            logger.info("TTS播放器已在运行，PID: %d" % _tts_player_process.pid)
            return True
            
        # 获取 tts_player.py 的路径
        tts_player_path = os.path.join(renpy.config.basedir, 'tts_player.py')
        
        # 检查文件是否存在
        if not os.path.exists(tts_player_path):
            # 尝试在游戏目录的 submods/tts 目录中查找
            tts_player_path = os.path.join(renpy.config.basedir, 'game', 'Submods', 'tts', 'tts_player.py')
            if not os.path.exists(tts_player_path):
                logger.error("找不到 tts_player.py 文件，请确保已放置在正确位置")
                return False
        
        # 获取 Python 解释器路径（优先使用 Python 3）
        python_exe = None
        potential_paths = [
            # 优先使用 Python 3（64位）
            'C:\\Python310\\python.exe',
            'C:\\Python39\\python.exe',
            'C:\\Python38\\python.exe',
            'C:\\Python37\\python.exe',
            'C:\\Python36\\python.exe',
            # 其次尝试 Python 3（32位）
            'C:\\Python310-32\\python.exe',
            'C:\\Python39-32\\python.exe',
            'C:\\Python38-32\\python.exe',
            'C:\\Python37-32\\python.exe',
            'C:\\Python36-32\\python.exe',
            # 最后尝试系统 PATH 中的 python
            'python.exe',
            # 作为最后手段才用 Python 2.7
            'C:\\Python27\\python.exe'
        ]
        
        for path in potential_paths:
            if path and os.path.exists(path):
                try:
                    # 验证是否是 Python 3
                    version_output = subprocess.check_output([path, '--version'], stderr=subprocess.STDOUT)
                    version_str = version_output.decode('utf-8', 'ignore')
                    
                    if "Python 3" in version_str:
                        python_exe = path
                        logger.info("找到兼容的 Python 3: %s" % python_exe)
                        break
                except Exception as e:
                    logger.debug("检查 Python 路径 %s 时出错: %s" % (path, str(e)))
        
        if not python_exe:
            logger.error("找不到可用的 Python 3 解释器")
            return False
            
        logger.info("使用 Python 解释器: %s" % python_exe)
        logger.info("尝试启动 TTS 播放器: %s" % tts_player_path)
        
        try:
            # 创建启动信息（Windows 下隐藏窗口）
            startup_info = None
            if sys.platform == "win32":
                startup_info = subprocess.STARTUPINFO()
                startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup_info.wShowWindow = 0  # 隐藏窗口
            
            # 启动 TTS 播放器
            _tts_player_process = subprocess.Popen(
                [python_exe, tts_player_path],
                cwd=os.path.dirname(tts_player_path),
                startupinfo=startup_info
            )
            
            logger.info("TTS 播放器已启动（使用 Python 3），PID: %d" % _tts_player_process.pid)
            return True
        except Exception, e:
            logger.error("启动 TTS 播放器失败: %s" % str(e))
            return False

    # 新增：关闭 TTS 播放器
    def start_tts_player():
        """自动启动外部 TTS 播放器脚本（显示控制台窗口）"""
        global _tts_player_process
        
        logger.info("=== 开始 TTS 播放器启动流程 ===")
        
        # 检查是否已经有运行中的播放器
        if _tts_player_process and _tts_player_process.poll() is None:
            logger.info("TTS播放器已在运行，PID: %d" % _tts_player_process.pid)
            return True
            
        # 获取启动脚本的路径
        start_script = os.path.join(renpy.config.basedir, 'start_tts_player.bat')
        
        # 检查文件是否存在
        if not os.path.exists(start_script):
            # 尝试在游戏目录的 submods/tts 目录中查找
            start_script = os.path.join(renpy.config.basedir, 'game', 'Submods', 'tts', 'start_tts_player.bat')
            if not os.path.exists(start_script):
                logger.error("找不到启动脚本，请确保已放置在正确位置")
                return False
        
        logger.info("找到启动脚本: %s" % start_script)
        
        try:
            # 关键修复：不要隐藏窗口
            # 创建普通进程，显示控制台窗口
            _tts_player_process = subprocess.Popen(
                [start_script],
                cwd=os.path.dirname(start_script),
                creationflags=subprocess.CREATE_NEW_CONSOLE  # 关键：显示新控制台窗口
            )
            
            logger.info("TTS 播放器已启动（显示控制台窗口），PID: %d" % _tts_player_process.pid)
            return True
        except Exception as e:
            logger.exception("启动 TTS 播放器失败")
            return False

    def check_api():
        try:
            import socket
            s = socket.create_connection(('127.0.0.1', 9880), timeout=3)
            s.close()
            return True
        except Exception, e:
            logger.debug('API检查失败: %s' % str(e))
            return False

    def get_tts(text):
        try:
            import urllib2
            import urllib
        except ImportError:
            logger.error("无法导入urllib2模块")
            return None

        cp = read_cfg()
        if not cp:
            return None

        logger.info('准备发送TTS请求 - 原始文本: "%s"' % (text.decode('utf-8', 'ignore')[:100] if isinstance(text, bytes) else text[:100]) + ('...' if len(text) > 100 else ''))
        try:
            if isinstance(text, unicode):
                text = text.encode('utf-8')
        except NameError:
            pass

        params = {
            'ref_audio_path': os.path.abspath(cp.get('GPT_SOVITS', 'refer_audio_path')),
            'prompt_text': cp.get('GPT_SOVITS', 'refer_text'),
            'text': text,
            'prompt_lang': cp.get('GPT_SOVITS', 'refer_text_language'),
            'text_lang': cp.get('GPT_SOVITS', 'text_language', 'zh'),
            'text_split_method': 'cut5',
            'batch_size': '1',
            'media_type': 'wav',
            'streaming_mode': 'true',
            # 直接指定兼容格式
            'sample_rate': '22050',
            'format': 'pcm_16le',
            'channels': '1'
        }

        encoded_params = {}
        for k, v in params.items():
            if isinstance(v, str):
                encoded_params[k] = v
            else:
                encoded_params[k] = v.encode('utf-8')
        query_string = urllib.urlencode(encoded_params)
        url = 'http://127.0.0.1:9880/tts?%s' % query_string

        try:
            return urllib2.urlopen(url, timeout=30).read()
        except Exception, e: 
            logger.error('TTS请求失败: %s' % str(e))
            return None

    def save_wav(data):
        fname = '%d.wav' % int(time.time() * 1e6)
        path = os.path.join(renpy.config.basedir, 'cache', fname)
        logger.info("尝试保存TTS音频到: %s" % path)
        logger.info("数据大小: %d bytes" % len(data))
        try:
            # 直接保存原始数据，不进行任何转换
            f = open(path, 'wb')
            f.write(data)
            f.close()
            
            # 验证文件是否成功写入
            if os.path.exists(path) and os.path.getsize(path) > 0:
                logger.info("成功保存TTS音频，大小: %d bytes" % os.path.getsize(path))
                return path
            else:
                logger.error("音频文件写入失败或为空")
                return None
                
        except Exception, e:
            logger.error("保存音频文件时出错: %s" % str(e))
            return None

    def clean_dialogue(text):
        if not text:
            return ""
        text = filter_renpy_special_tags(text)
        if hasattr(store, 'player_name'):
            player_name = store.player_name or 'Player'
        else:
            player_name = 'Player'
        text = text.replace('[mas_get_player_nickname()]', player_name)
        text = text.replace('[player]', player_name)
        text = text.strip().lstrip('.,!?;:[](){}"\'')
        return text

    def get_current_dialogue():
        """尝试从各种可能位置获取当前对话文本"""
        try:
            if hasattr(store, 'mas') and hasattr(store.mas, 'dialogue'):
                return clean_dialogue(store.mas.dialogue)
        except Exception, e:
            logger.debug('从mas.dialogue获取对话失败: %s' % str(e))
        
        try:
            if hasattr(store, 'dialogue_history') and store.dialogue_history:
                return clean_dialogue(store.dialogue_history[-1])
        except Exception, e:
            logger.debug('从dialogue_history获取对话失败: %s' % str(e))
        
        try:
            if hasattr(store, '_last_say_what'):
                return clean_dialogue(store._last_say_what)
        except Exception, e:
            logger.debug('从_last_say_what获取对话失败: %s' % str(e))
        
        return None

    def process_dialogue():
        """处理对话并生成TTS音频"""
        try:
            # 检查是否有新的对话内容需要处理
            dialogue = get_current_dialogue()
            if not dialogue:
                return False
                
            # 检查是否是新对话
            current_hash = hash(dialogue)
            global last_dialogue_hash
            if current_hash == last_dialogue_hash:
                return False
                
            # 更新对话哈希
            last_dialogue_hash = current_hash
            
            # 过滤无效对话
            if len(dialogue.strip()) <= 1 or dialogue.startswith("【") or dialogue.startswith("["):
                return False
                
            # 处理有效对话
            if len(dialogue) >= 3:
                logger.info('检测到新对话: %s' % (dialogue[:50] + ('...' if len(dialogue) > 50 else '')))
                data = get_tts(dialogue)
                if data and len(data) > 0:
                    audio_path = save_wav(data)
                    if audio_path:
                        logger.info('TTS音频已生成: %s' % audio_path)
                        return True
                    else:
                        logger.error('音频文件保存失败')
                else:
                    logger.warning('TTS请求返回空数据')
            return False
        except Exception, e:
            logger.error("处理对话时出错: %s" % str(e))
            return False

    def initialize_tts_system():
        """在游戏完全加载后安全初始化TTS系统"""
        global tts_initialized
        if tts_initialized:
            return
            
        logger.info("开始初始化TTS系统...")
        try:
            clear_cache()
            cp = read_cfg()
            if not cp:
                logger.error("配置读取失败，无法启动TTS")
                return

            # 启动API
            _api_process = launch_api(cp)
            
            # 等待API就绪
            max_retries = 15
            for i in range(max_retries):
                if check_api():
                    logger.info("API已就绪")
                    break
                time.sleep(1)
            else:
                logger.error('API启动失败')
                return
            
            # 自动启动 TTS 播放器（使用系统 Python）
            logger.info("尝试自动启动 TTS 播放器...")
            start_tts_player()
            
            # 标记TTS系统已初始化
            tts_initialized = True
            logger.info("TTS系统已成功初始化")
        except Exception, e:
            logger.error("TTS初始化失败: %s" % str(e))

    def interact_callback():
        """在Ren'Py每一帧交互时调用的回调函数"""
        try:
            # 确保TTS系统已初始化
            if not tts_initialized:
                return
                
            # 检查并处理对话
            process_dialogue()
        except Exception, e:
            logger.error("交互回调出错: %s" % str(e))

init -987 python in mas_submod_utils:
    # 仅在init阶段注册回调，不做任何实际初始化
    logger.info('TTS初始化设置完成')
    
    # 确保回调系统可用
    if not hasattr(renpy.config, 'interact_callbacks'):
        renpy.config.interact_callbacks = []
    
    # 注册交互回调
    if interact_callback not in renpy.config.interact_callbacks:
        renpy.config.interact_callbacks.append(interact_callback)
        logger.info('TTS系统已添加到交互回调')
    
    # 使用after_load确保TTS系统在游戏加载后初始化
    if hasattr(renpy.config, 'after_load'):
        def delayed_init():
            logger.info("延迟初始化TTS系统...")
            initialize_tts_system()
        
        renpy.config.after_load.append(delayed_init)
        logger.info('TTS系统已添加到加载后回调')
    else:
        # 旧版Ren'Py的备用方案
        logger.warning('旧版Ren\'Py，使用交互回调启动TTS')
        def delayed_init():
            try:
                logger.info("延迟初始化TTS系统...")
                initialize_tts_system()
            except Exception, e:
                logger.error("TTS初始化失败: %s" % str(e))
            if delayed_init in renpy.config.interact_callbacks:
                renpy.config.interact_callbacks.remove(delayed_init)
        
        if not hasattr(renpy.config, 'interact_callbacks'):
            renpy.config.interact_callbacks = []
        renpy.config.interact_callbacks.append(delayed_init)
    
    # 添加游戏退出时的清理回调
    def cleanup_tts_system():
        """游戏退出时清理TTS系统"""
        logger.info("正在清理TTS系统...")
        try:
            # 停止TTS播放器
            stop_tts_player()
            logger.info("TTS系统清理完成")
        except Exception, e:
            logger.error("清理TTS系统时出错: %s" % str(e))
    
    if hasattr(renpy, 'register_quit_function'):
        renpy.register_quit_function(cleanup_tts_system)
        logger.info('TTS清理函数已注册')
    else:
        # 旧版Ren'Py的替代方案
        if not hasattr(renpy.config, 'after_load'):
            renpy.config.after_load = []
        renpy.config.after_load.append(lambda: renpy.register_quit_function(cleanup_tts_system))
        logger.info('TTS清理函数已通过after_load注册')
    
    logger.info('TTS系统已初始化，将在游戏加载后启动')