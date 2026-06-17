"""
编译脚本 — 将 Python 项目打包为 Windows 独立可执行文件

用法:
    python set_up.py                  # 打包（默认）
    python set_up.py --clean          # 清理临时文件后打包
    python set_up.py --clean-only     # 仅清理，不打包

输出:
    dist/空教室查询.exe
"""

import os
import sys
import shutil
import subprocess
import argparse

BUILD_DIRS = ["build", "dist"]
SPEC_FILE = "空教室查询.spec"


def clean():
    """清理 PyInstaller 构建产物"""
    for d in BUILD_DIRS:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  ✓ 已删除 {d}/")
    if os.path.exists(SPEC_FILE):
        os.remove(SPEC_FILE)
        print(f"  ✓ 已删除 {SPEC_FILE}")
    # 清理 __pycache__
    for root, dirs, _ in os.walk("."):
        for d in dirs:
            if d == "__pycache__":
                path = os.path.join(root, d)
                shutil.rmtree(path)
                print(f"  ✓ 已删除 {path}/")
    print("  ✨ 清理完成")


def build(clean_first: bool = True):
    """执行 PyInstaller 打包"""
    if clean_first:
        clean()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",                  # 无控制台窗口
        "--name", "空教室查询",
        "--add-data", "semester_config.json;.",
        "--collect-data", "ddddocr",   # 包含 OCR 模型文件
        "--collect-data", "onnxruntime",
        "--noconfirm",
        "main.py",
    ]

    print(f"\n  🏗️  正在打包... (耗时约 1-3 分钟)")
    print(f"  {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode == 0:
        print(f"\n  ✅ 打包成功！")
        print(f"  📦 dist/空教室查询.exe")
        size = os.path.getsize("dist/空教室查询.exe") / 1024 / 1024
        print(f"  💾 大小: {size:.0f} MB")
    else:
        print(f"\n  ❌ 打包失败 (返回码 {result.returncode})")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="空教室查询 — 编译脚本"
    )
    parser.add_argument("--clean", action="store_true",
                        help="清理临时文件后重新打包")
    parser.add_argument("--clean-only", action="store_true",
                        help="仅清理临时文件，不打包")
    args = parser.parse_args()

    if args.clean_only:
        clean()
        return

    build(clean_first=args.clean)


if __name__ == "__main__":
    main()
