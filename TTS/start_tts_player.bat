@echo off
setlocal


REM 启动 tts_player.py
echo 启动 TTS 播放器...

REM 直接启动，不要重定向输出
"python" "tts_player.py"

REM 检查错误
if %errorlevel% neq 0 (
    echo TTS 播放器启动失败，错误代码: %errorlevel%
    timeout /t 10
)

endlocal