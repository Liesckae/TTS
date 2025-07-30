import os
import sys
import time
import struct
import numpy as np
import pyaudio
import logging
import soundfile as sf
from datetime import datetime

# ===== 配置区域 =====
# 缓存目录设置
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')

# 日志目录设置
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
LOG_FILE = os.path.join(LOG_DIR, f'tts_player_{datetime.now().strftime("%Y%m%d")}.log')

# 播放器参数
POLLING_INTERVAL = 0.2  # 检测间隔，单位秒
MIN_AUDIO_DURATION = 0.3  # 最小音频时长(秒)，低于此值视为无效
MIN_AUDIO_SIZE = 100  # 最小音频文件大小(字节)
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 0.1  # 重试延迟(秒)
WAV_HEADER_SIZE = 44  # 标准WAV文件头部大小

# GPT-SoVITS音频参数（固定值，不能改！）
GPT_SOVITS_PARAMS = {
    'framerate': 32000,  # 采样率
    'sampwidth': 2,      # 16-bit
    'channels': 1        # 单声道
}

# ===== 初始化日志系统 =====
# 确保日志目录存在
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
        print(f"已创建日志目录: {LOG_DIR}")
    except Exception as e:
        print(f"创建日志目录失败: {str(e)}")
        sys.exit(1)

# 配置日志
logger = logging.getLogger('TTS_PLAYER')
logger.setLevel(logging.DEBUG)

# 文件处理器
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)

# 控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 打印启动信息
print("=" * 60)
print("GPT-SoVITS 音频播放器")
print(f"日志文件: {LOG_FILE}")
print(f"缓存目录: {CACHE_DIR}")
print("按 Ctrl+C 退出")
print("=" * 60)

logger.info("GPT-SoVITS 音频播放器已启动")
logger.debug(f"日志文件: {LOG_FILE}")
logger.debug(f"缓存目录: {CACHE_DIR}")

# ===== 检查缓存目录 =====
if not os.path.exists(CACHE_DIR):
    logger.error(f"缓存目录不存在: {CACHE_DIR}")
    logger.info("尝试使用替代缓存目录...")
    
    # 尝试其他可能的缓存目录位置
    possible_dirs = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache'),
        os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cache')),
        'E:\\DDLCt\\cache'
    ]
    
    for dir_path in possible_dirs:
        if os.path.exists(dir_path):
            CACHE_DIR = dir_path
            logger.info(f"找到缓存目录: {CACHE_DIR}")
            break
    else:
        logger.error("无法找到缓存目录，请检查配置")
        print(f"\n错误：无法找到缓存目录！请检查配置")
        print("按回车键退出...")
        input()
        sys.exit(1)

# 检查缓存目录是否可访问
try:
    test_file = os.path.join(CACHE_DIR, 'tts_player_test.tmp')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    logger.debug(f"缓存目录可写: {CACHE_DIR}")
except Exception as e:
    logger.error(f"缓存目录不可写: {CACHE_DIR} - {str(e)}")
    print(f"\n错误：缓存目录不可写！")
    print("按回车键退出...")
    input()
    sys.exit(1)

# ===== 辅助函数 =====

def is_file_fully_written(file_path, min_size=100):
    """
    检查文件是否已完全写入
    
    参数:
        file_path: 文件路径
        min_size: 最小文件大小(字节)
    
    返回:
        True 如果文件已完全写入，否则 False
    """
    if not os.path.exists(file_path):
        return False
        
    # 检查文件大小
    file_size = os.path.getsize(file_path)
    if file_size < min_size:
        logger.debug(f"文件大小过小: {file_size} bytes (最小要求: {min_size} bytes)")
        return False
    
    # 检查文件是否稳定
    time.sleep(0.05)
    size1 = os.path.getsize(file_path)
    time.sleep(0.05)
    size2 = os.path.getsize(file_path)
    
    return size1 == size2

def play_audio_with_pyaudio(file_path, volume=1.0):
    """
    使用PyAudio直接播放原始音频数据
    
    参数:
        file_path: 音频文件路径
        volume: 播放音量 (0.0-1.0)
    
    返回:
        bool: 播放是否成功
    """
    try:
        print(f"\n--- 尝试使用PyAudio播放: {os.path.basename(file_path)} ---")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"❌ 音频文件不存在: {file_path}")
            return False
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        print(f"音频文件大小: {file_size} bytes")
        
        # 如果文件大小过小，直接返回
        if file_size <= 44:
            print("❌ 音频文件可能为空（只有WAV头部）")
            return False
        
        # GPT-SoVITS音频参数（硬编码）
        channels = 1      # 单声道
        sampwidth = 2     # 16-bit
        framerate = 32000 # 32kHz
        
        # 计算预期的音频数据大小
        expected_audio_size = file_size - 44
        print(f"假设GPT-SoVITS参数: {channels}声道, {sampwidth*8}-bit, {framerate}Hz")
        print(f"预期音频数据大小: {expected_audio_size} bytes")
        
        # 读取整个文件
        with open(file_path, 'rb') as f:
            all_data = f.read()
        
        # 直接提取音频数据（跳过WAV头部）
        audio_data = all_data[44:] if len(all_data) > 44 else all_data
        print(f"提取的音频数据大小: {len(audio_data)} bytes")
        
        # 如果提取的数据为空，尝试其他方法
        if len(audio_data) == 0:
            print("⚠️ 无法通过跳过头部获取音频数据，尝试其他方法...")
            
            # 尝试查找"data"块
            data_pos = all_data.find(b'data')
            if data_pos != -1 and data_pos + 8 < len(all_data):
                # 读取"data"块大小
                chunk_size = struct.unpack('<I', all_data[data_pos+4:data_pos+8])[0]
                # 提取音频数据
                audio_start = data_pos + 8
                audio_end = min(audio_start + chunk_size, len(all_data))
                audio_data = all_data[audio_start:audio_end]
                print(f"通过查找'data'块获取音频数据: {len(audio_data)} bytes")
        
        # 检查数据是否为空
        if len(audio_data) == 0:
            print("❌ 无法提取有效音频数据")
            return False
        
        # 计算RMS值
        if sampwidth == 2:  # 16-bit
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
        else:  # 8-bit
            audio_array = np.frombuffer(audio_data, dtype=np.uint8)
        
        if len(audio_array) > 0:
            rms = np.sqrt(np.mean(np.square(audio_array)))
            print(f"音频RMS值: {rms:.6f}")
            
            # 如果RMS值过低，尝试增强
            if rms < 0.001:
                print(f"⚠️ 检测到极低音量音频 (RMS={rms:.6f})，尝试增强...")
                
                if sampwidth == 2:  # 16-bit
                    # 将数据转换为float32进行处理
                    audio_float = audio_array.astype(np.float32) / 32768.0
                    
                    # 应用增益，但不超过1000倍
                    gain = min(0.5 / max(rms, 0.00001), 1000.0)
                    audio_float = audio_float * gain
                    print(f"应用增益: {gain:.2f}x")
                    
                    # 限制范围 [-1.0, 1.0]
                    audio_float = np.clip(audio_float, -1.0, 1.0)
                    
                    # 转换回int16
                    audio_array = (audio_float * 32767).astype(np.int16)
                    
                    # 转换回字节
                    audio_data = audio_array.tobytes()
                else:
                    print("⚠️ 8-bit音频增强功能尚未实现")
        
        # 计算播放时长
        duration = len(audio_data) / (framerate * channels * sampwidth)
        print(f"预计播放时长: {duration:.2f}秒")
        
        # 初始化PyAudio
        p = pyaudio.PyAudio()
        
        # 打印当前音频设备信息
        try:
            default_device = p.get_default_output_device_info()
            print(f"使用默认音频设备: {default_device['name']} (采样率: {default_device['defaultSampleRate']}Hz)")
        except Exception as e:
            print(f"⚠️ 无法获取默认音频设备信息: {str(e)}")
        
        # 打开音频流
        stream = p.open(
            format=p.get_format_from_width(sampwidth),
            channels=channels,
            rate=framerate,
            output=True
        )
        
        print("▶️ 开始播放...")
        
        # 播放音频
        chunk_size = 1024
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            stream.write(chunk)
        
        # 停止和关闭流
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        print("✅ 播放完成")
        return True
    except Exception as e:
        print(f"❌ PyAudio播放失败: {str(e)}")
        return False

def play_audio(file_path):
    """播放指定的音频文件"""
    try:
        print(f"\n--- 尝试播放音频: {os.path.basename(file_path)} ---")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"❌ 音频文件不存在: {file_path}")
            return False
            
        # 确保文件已完全写入
        if not is_file_fully_written(file_path):
            print(f"⚠️ 音频文件可能未完全写入，等待...")
            time.sleep(0.3)
            
            if not is_file_fully_written(file_path):
                print(f"❌ 音频文件仍未完全写入")
                return False
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        print(f"音频文件大小: {file_size} bytes")
        
        # 如果文件大小过小，直接返回
        if file_size <= 44:
            print("❌ 音频文件可能为空（只有WAV头部）")
            return False
        
        # 直接使用PyAudio播放
        print("\n--- 尝试使用PyAudio直接播放（绕过格式问题）---")
        if play_audio_with_pyaudio(file_path):
            print("✅ 成功使用PyAudio直接播放")
            return True
        
        print("❌ 所有播放方案均失败")
        return False
        
    except Exception as e:
        print(f"❌ 播放音频时发生未处理的异常: {str(e)}")
        return False

# ===== 主循环 =====

def monitor_audio_files():
    """监控音频文件目录"""
    print(f"\n开始监控目录: {CACHE_DIR}")
    print("按 Ctrl+C 退出监控")
    
    if not os.path.exists(CACHE_DIR):
        print(f"\n错误：监控目录不存在: {CACHE_DIR}")
        print("按回车键退出...")
        input()
        return
    
    # 记录已处理的文件
    processed_files = set()
    last_file_count = 0
    
    print("\n已准备就绪，等待新音频文件...")
    
    while True:
        try:
            # 获取当前目录中的所有文件
            current_files = set(os.listdir(CACHE_DIR))
            
            # 检查文件数量变化
            if len(current_files) != last_file_count:
                print(f"\n目录文件数量变化: {last_file_count} -> {len(current_files)}")
                last_file_count = len(current_files)
            
            # 查找新文件（.wav 文件，但排除已处理的）
            new_files = [f for f in current_files 
                         if f.endswith(('.wav',)) and f not in processed_files]
            
            # 记录找到的新文件
            if new_files:
                print(f"\n检测到 {len(new_files)} 个新音频文件: {', '.join(new_files)}")
            
            # 处理新文件
            for file_name in new_files:
                file_path = os.path.join(CACHE_DIR, file_name)
                
                # 确保文件已完全写入
                time.sleep(0.2)
                
                # 播放音频
                if play_audio(file_path):
                    # 标记为已处理
                    processed_files.add(file_name)
                    print(f"✅ 已成功处理音频文件: {file_name}")
                else:
                    print(f"❌ 处理音频文件失败: {file_name}")
            
            # 定期清理已处理的文件记录
            if len(processed_files) > 100:
                processed_files = set(list(processed_files)[-50:])
                print("清理已处理文件记录，保留最近50个")
            
            # 等待下次检查
            time.sleep(POLLING_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n用户中断，程序退出")
            break
        except Exception as e:
            print(f"\n❌ 监控过程中发生未处理的异常: {str(e)}")
            time.sleep(1)

# ===== 主程序 =====

def main():
    """主函数"""
    print("\n" + "="*60)
    print("GPT-SoVITS 音频播放器")
    print(f"Python版本: {sys.version}")
    print(f"操作系统: {sys.platform}")
    print("="*60)
    
    # 检查是否已经有实例在运行
    try:
        import socket
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.bind(('127.0.0.1', 9882))
        test_socket.close()
        print("没有检测到其他TTS播放器实例")
    except:
        print("检测到其他TTS播放器实例正在运行，程序退出")
        sys.exit(1)
    
    # 开始监控
    try:
        monitor_audio_files()
    except KeyboardInterrupt:
        print("\n用户中断，程序退出")
    except Exception as e:
        print(f"\n❌ 主程序发生未处理的异常: {str(e)}")
        sys.exit(1)
    
    print("\n按回车键退出...")
    input()

if __name__ == "__main__":
    # 检查PyAudio是否安装
    try:
        import pyaudio
    except ImportError:
        print("❌ 缺少PyAudio库，请先安装:")
        print("  pip install pyaudio")
        print("\n注意: 在Windows上可能需要先安装Visual Studio Build Tools")
        sys.exit(1)
    
    # 检查soundfile是否安装
    try:
        import soundfile as sf
    except ImportError:
        print("⚠️ 缺少soundfile库，某些功能可能受限:")
        print("  pip install soundfile")
    
    main()