# 图像转 SVG 转换工具 v0.3.6

本工具将黑白线稿矢量化流程封装为一步式“原图 → 最终 SVG”转换，提供
Python 函数接口和命令行接口。运行时使用包内 Potrace 1.16 和 resvg
0.47.0，所有运行路径均根据当前目录解析，不依赖外部环境变量。

## 环境准备

当前交付严格面向 Linux x86-64。Linux resvg 0.47.0 要求 glibc 2.34 或
更高版本；本机验证环境为 Debian 12、glibc 2.36、Python 3.11。先从包
根目录安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

首次部署需要通过 pip 安装 Python 依赖；Potrace 和 resvg 已包含在工具目录中。
本包不支持 Windows、macOS 或非 x86-64 Linux。

## 输入、尺寸和输出规则

- 支持 `.png`、`.jpg`、`.jpeg`，扩展名不区分大小写。
- 文件输入处理单张图片；目录输入只处理第一层，不递归。
- 正式支持尺寸固定为 `2048×2048`。程序读取真实像素尺寸，不自动缩放、
  拉伸、裁剪或补边；其他尺寸会明确报错。
- 输出只保留与输入同名的 `.svg`，例如 `example.png` → `example.svg`。
- 默认禁止覆盖现有同名 SVG；只有显式使用 `overwrite=True` 或
  `--overwrite` 才允许覆盖。
- 同一批次若存在同主名文件（包括大小写冲突），会在写入前标记这些文件
  为失败，不会静默覆盖；其他无冲突文件继续处理。
- 单文件失败不阻止批次继续；批次结果和 CLI 退出码会反映非全部成功。
- mask、BMP、基线 SVG 和内部栅格只存在于临时目录，结束后清理，不作为
  正式输出。

## Python 接口

单图：

```python
from svg_converter import convert_image

output = convert_image(
    "examples/input/002c66bddebfec777e2835d2529bad8c.png",
    "examples/generated",
)
print(output)
```

批量：

```python
from svg_converter import convert_batch

result = convert_batch("examples/input", "examples/generated")
print(result.input_count, result.success_count, result.failure_count)
for failure in result.failures:
    print(failure.input_path, failure.reason)
```

公开接口为：

```python
convert_image(input_path, output_dir, *, overwrite=False) -> pathlib.Path
convert_batch(input_dir, output_dir, *, overwrite=False) -> BatchResult
```

调用者无需配置算法参数。

## 命令行接口

单图：

```bash
python3 convert.py --input examples/input/002c66bddebfec777e2835d2529bad8c.png --output examples/generated
```

目录批量：

```bash
python3 convert.py --input examples/input --output examples/generated
```

需要覆盖已有 SVG 时显式添加：

```bash
python3 convert.py --input examples/input --output examples/generated --overwrite
```

全部成功的退出码为 `0`；参数、工具、尺寸、命名冲突、覆盖冲突或任一图片
失败时退出码非 `0`。

## 固定工具与调用参数

包内位置：

- `tools/potrace/potrace`：Linux x86-64 Potrace 1.16
- `tools/resvg/resvg`：Linux x86-64 resvg 0.47.0

版本自检：

```bash
chmod +x tools/potrace/potrace tools/resvg/resvg
./tools/potrace/potrace --version
./tools/resvg/resvg --version
```

每张图片采用以下固定工具调用：

```text
Potrace 1 次：potrace <mask.bmp> --svg --output <baseline.svg> --turdsize 0 --resolution 72
resvg  1 次：resvg --dpi 72 <baseline.svg> <baseline.png>
```

程序启动转换时会校验工具版本和 SHA-256；不调用系统 PATH 中的同名工具。
完整哈希见 `SHA256SUMS.txt`，来源和许可证见 `THIRD_PARTY_NOTICES.md` 及
`tools/` 子目录。

## 示例目录

- `examples/input/`：固定的三张 2048×2048 示例原图。
- `examples/output/`：三个预生成的同名 SVG 示例输出。
- `examples/example.py`：Python 单图和批量调用示例。

直接运行调用示例：

```bash
python3 examples/example.py
```

运行命令会把新结果写入 `examples/generated/`，不会默认覆盖
`examples/output/` 中的示例输出。

## 常见错误

- `Unsupported input format`：输入扩展名不是 PNG/JPG/JPEG。
- `Unsupported image size`：实际尺寸不是 2048×2048；程序不会自动改尺寸。
- `Output SVG already exists`：默认覆盖保护生效；确认后使用显式覆盖选项。
- `Naming conflict`：同一批次多个输入将映射到同一 SVG 主名。
- `Bundled Linux tool is not executable`：执行 `chmod +x tools/potrace/potrace tools/resvg/resvg`。
- `Bundled tool is missing/hash mismatch/version`：包内工具缺失、被修改或版本
  不符；应从原始交付包恢复，不能改用系统安装版本。
- `GLIBC_2.34 not found`：Linux 系统过旧；请使用 glibc 2.34 或更高版本。

## 交付说明

整个 `v0.3.6-svg-package` 目录可以复制到 Linux 本地目录后运行。若从不保留
Linux 权限的文件系统复制，先为两个工具执行 `chmod +x`。
不要只复制 `convert.py`；必须保留 `svg_converter/`、`tools/`、
`requirements.txt` 和许可证文件的相对目录结构。

已在本机 Debian 12 / Python 3.11 Docker Linux x86-64 环境完成：

- 包内 Potrace 1.16 和 resvg 0.47.0 版本、SHA-256 与执行权限检查；
- Python API 契约测试；
- `examples/example.py` 单图和三图批量调用；
- 54 张标准输入完整批量回归：`54/54` 成功；
- 54 个最终 SVG 与冻结 v0.3.6 参考文件逐字节一致。
