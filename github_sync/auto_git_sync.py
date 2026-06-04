"""
=================================
   🤖 自动 Git 同步小助手 🤖
=================================
用法：
  1. 双击运行 或 在终端运行: python scripts/auto_git_sync.py
  2. 它会自动把代码保存（commit）并上传（push）到 GitHub
  3. 每次运行都会在 auto_sync_log.txt 里记日志

定时自动运行（Windows 任务计划程序）：
  可以设置每天/每小时自动运行这个脚本，就不用记着手动上传了
"""

import subprocess
import os
from datetime import datetime

# ========== 配置区（您可以根据需要修改） ==========
AUTO_COMMIT_MESSAGE = "🤖 自动同步更新"  # 提交时的默认说明
LOG_FILE = "auto_sync_log.txt"           # 日志文件名
# =================================================

def run_cmd(command, show_output=True):
    """运行一条命令，返回是否成功"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if show_output and result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0 and show_output:
            print(f"⚠️  {result.stderr.strip()}")
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        print(f"❌ 出错了: {e}")
        return False, ""

def log(msg):
    """写日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"📝 日志: {msg}")

def main():
    print("=" * 50)
    print("  🔄 开始自动同步...")
    print(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 第1步：检查是不是 Git 仓库
    success, _ = run_cmd("git rev-parse --git-dir", show_output=False)
    if not success:
        log("❌ 这不是一个 Git 仓库，请先运行 git init")
        print("❌ 这不是一个 Git 仓库！")
        print("💡 请先在 VS Code 里打开终端，运行: git init")
        return

    # 第2步：检查有没有配置远程仓库（GitHub）
    success, remote = run_cmd("git remote get-url origin", show_output=False)
    has_remote = success and "github.com" in remote
    if not has_remote:
        log("⚠️  没有配置 GitHub 远程仓库，跳过上传步骤")
        print("⚠️  还没有连接 GitHub 远程仓库，跳过上传")
        print("💡 如果想上传到 GitHub，需要先设置远程仓库地址")
        print("   在终端运行: git remote add origin https://github.com/你的用户名/仓库名.git")

    # 第3步：添加所有修改过的文件
    print("\n📂 正在检查修改过的文件...")
    run_cmd("git add -A")
    
    # 第4步：检查有没有需要提交的变更
    success, status = run_cmd("git status --porcelain", show_output=False)
    if not status:
        print("\n✅ 没有新修改，所有文件都是最新的！")
        log("✅ 没有新修改，无需提交")
        # 如果有远程仓库，还是尝试拉取一下最新代码
        if has_remote:
            print("\n📥 检查远程仓库有没有更新...")
            run_cmd("git pull --rebase origin main", show_output=False)
        print("\n" + "=" * 50)
        print("  ✅ 同步完成！")
        print("=" * 50)
        return

    # 第5步：提交（commit）修改
    print("\n💾 正在保存修改（commit）...")
    changes = len(status.strip().split('\n')) if status else 0
    commit_msg = f"{AUTO_COMMIT_MESSAGE} ({changes} 个文件变更)"
    success, _ = run_cmd(f'git commit -m "{commit_msg}"')
    
    if success:
        log(f"✅ 提交成功: {commit_msg}")
        print(f"✅ 提交成功！共 {changes} 个文件")
    else:
        log("❌ 提交失败")
        print("❌ 提交失败，可能是没有需要提交的内容")
        return

    # 第6步：上传到 GitHub（如果有配置远程仓库）
    if has_remote:
        print("\n📤 正在上传到 GitHub...")
        success, output = run_cmd("git push origin main")
        if success:
            log("✅ 上传到 GitHub 成功！")
            print("✅ 上传到 GitHub 成功！")
        else:
            log("⚠️  上传可能有问题，请在终端手动运行: git push")
            print("⚠️  上传时遇到问题，可能需要手动处理")
    else:
        print("\n💡 提示: 还没连接 GitHub，只保存在了本地")
        print("   如果想上传到 GitHub，请看 GITHUB_GUIDE.md 说明")

    print("\n" + "=" * 50)
    print("  ✅ 自动同步完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()
