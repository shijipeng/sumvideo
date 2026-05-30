# 捆绑 ffmpeg

将对应平台的 ffmpeg 可执行文件放入：

- `darwin-arm64/ffmpeg` — macOS Apple Silicon
- `win32-x64/ffmpeg.exe` — Windows x64

可从 https://ffmpeg.org/download.html 或 `ffmpeg-static` 获取。未放置时桌面/开发环境回退到系统 `PATH` 中的 `ffmpeg`。
