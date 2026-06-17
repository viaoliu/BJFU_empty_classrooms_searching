"""
================================================================================
 北京林业大学 — 空教室查询工具 ｜ 主入口文件
================================================================================

  【功能】
    通过强智教务系统 API，自动识别验证码，查询空闲教室。
    支持三种运行模式：图形界面（默认）、CLI 交互、快速查询。

  【用法】
    python main.py                    # 默认启动图形界面（GUI）
    python main.py --cli              # 命令行交互模式
    python main.py --quick            # 一键快速查询本周一~周五
    python main.py --vpn              # 强制走 VPN 访问教务系统

  【架构】
    main.py (入口)
      ├── (默认) → gui_mode()   → 创建 BFUClassroomAPI → 直接硬编码登录 → MainWindow
      ├── --cli  → interactive_mode() → 终端交互式查询
      └── --quick → quick_mode()     → 一键快速查询

  【如果你要修改】
    - 想改默认登录账号：找到 gui_mode() 中的 USERNAME / PASSWORD
    - 想添加新的启动参数：修改 main() 中的 parser.add_argument()
    - 想修改 GUI 界面：编辑 gui.py 中的 MainWindow 类
    - 想修改 API 逻辑：编辑 bfu_api.py 中的 BFUClassroomAPI

================================================================================
"""

import sys
import argparse
from bfu_api import BFUClassroomAPI, display_results


# ═══════════════════════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_semester_label(sem_id: str) -> str:
    """
    将学期 ID（如 "2025-2026-2"）转为可读的中文名称。

    规则:
      - "2025-2026-2" → "2025-2026学年第春学期"
      - 末尾数字: 1=秋, 2=春, 3=夏
    """
    season_map = {"1": "秋", "2": "春", "3": "夏"}
    parts = sem_id.split("-")
    season = season_map.get(parts[2], parts[2])
    return f"{parts[0]}-{parts[1]}学年第{season}学期"


# ═══════════════════════════════════════════════════════════════════════════════
#  模式一：CLI 交互模式  (python main.py --cli)
# ═══════════════════════════════════════════════════════════════════════════════

def interactive_mode(force_vpn=False):
    """
    命令行交互式查询 —— 全部在终端里完成。

    流程：
      1. 输入学号、密码 → 登录教务系统
      2. 选择学期、教学楼
      3. 输入查询条件（周次、星期、节次）
      4. 展示查询结果（完全空闲 / 部分空闲）
      5. 可输入教室序号查看该教室 7 个时段的详细排课状态

    参数:
      force_vpn: True = 强制走 VPN 访问
    """
    print()
    print("=" * 60)
    print("  北京林业大学 · 空教室查询工具")
    print("  Powered by BFU Academic Affairs System API")
    print("=" * 60)

    # ── 输入凭据 ──────────────────────────────────────────────────────────────
    username = input("\n  学号: ").strip()
    password = input("  密码: ").strip()

    # ── 登录 ──────────────────────────────────────────────────────────────────
    api = BFUClassroomAPI(username, password, force_vpn=force_vpn)
    print("\n  ⏳ 正在登录系统...", end=" ", flush=True)
    if not api.login():
        msg = "\n  ❌ 登录失败！"
        if api.vpn_mode:
            msg += " VPN 模式下登录失败，请检查账号密码或 VPN 连接状态"
        else:
            msg += " 可能是账号密码错误或验证码识别失败\n"
            msg += "    提示: 使用 --vpn 参数可通过 VPN 连接"
        print(msg)
        return
    print("✅ 登录成功！")

    # ── 获取当前周信息（自动计算） ────────────────────────────────────────────
    current_sem = ""
    for s in api.get_semesters():
        if s["current"]:
            current_sem = s["id"]
            break
    if not current_sem:
        current_sem = api.get_semesters()[0]["id"]

    current_week = api.get_current_week(current_sem)
    current_day = BFUClassroomAPI.get_current_day()
    day_names = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    print(f"\n  当前时间: 第{current_week}周, {day_names[current_day]}")

    # ── 选择学期 ──────────────────────────────────────────────────────────────
    semesters = api.get_semesters()
    current_idx = next((i for i, s in enumerate(semesters) if s["current"]), 0)
    print("\n  ── 学期选择 ──")
    for i, s in enumerate(semesters):
        mark = " ← 当前" if s["current"] else ""
        print(f"    [{i}] {get_semester_label(s['id'])}{mark}")
    choice = input(f"  选择 (0-{len(semesters)-1}, 回车=默认): ").strip()
    sem_idx = int(choice) if choice.isdigit() and 0 <= int(choice) < len(semesters) else current_idx
    xnxqh = semesters[sem_idx]["id"]
    print(f"  → {get_semester_label(xnxqh)}\n")

    # ── 选择教学楼 ────────────────────────────────────────────────────────────
    buildings = api.get_buildings()
    print("  ── 教学楼 ──")
    print("    [0] 全部教学楼")
    for i, b in enumerate(buildings, 1):
        print(f"    [{i}] {b['name']}")
    choice = input("  选择 (0-{}, 回车=全部): ".format(len(buildings))).strip()
    bidx = int(choice) if choice.isdigit() and 0 <= int(choice) <= len(buildings) else 0
    jxlbh = buildings[bidx - 1]["id"] if bidx > 0 else ""
    bld_name = buildings[bidx - 1]["name"] if bidx > 0 else "全部教学楼"
    print(f"  → {bld_name}\n")

    # ── 输入查询条件 ──────────────────────────────────────────────────────────
    print("  ── 查询条件 (回车使用默认值) ──")
    zc_default = str(current_week)
    zc = input(f"  起始周次 (1-30, 默认={zc_default}): ").strip()
    zc = zc if zc else zc_default
    zc2 = input(f"  结束周次 (1-30, 默认={zc}): ").strip()
    zc2 = zc2 if zc2 else zc

    day_default = str(current_day)
    xq = input(f"  起始星期 (1=周一 ~ 7=周日, 默认={day_default}): ").strip()
    xq = xq if xq else day_default
    xq2 = input(f"  结束星期 (1-7, 默认={xq}): ").strip()
    xq2 = xq2 if xq2 else xq

    jc = input(f"  起始节次 (1-12, 默认=1): ").strip()
    jc = jc.zfill(2) if jc else "01"
    jc2 = input(f"  结束节次 (1-12, 默认=12): ").strip()
    jc2 = jc2.zfill(2) if jc2 else "12"

    day_range = day_names[int(xq)] if xq == xq2 else f"{day_names[int(xq)]}~{day_names[int(xq2)]}"

    # ── 执行查询 ──────────────────────────────────────────────────────────────
    print(f"\n  ⏳ 正在查询第{zc}-{zc2}周, {day_range}, 节次{jc}-{jc2}...", end=" ", flush=True)

    rooms = api.query(
        xnxqh=xnxqh, jxlbh=jxlbh,
        zc=zc, zc2=zc2,
        xq=xq, xq2=xq2,
        jc=jc, jc2=jc2,
        jszt="",
    )

    if not rooms:
        print("无数据")
        print("\n  没有查询到教室数据，请检查条件")
        return

    print(f"共 {len(rooms)} 个教室")

    # ── 结果分析 ──────────────────────────────────────────────────────────────
    # periods 数组有 7 个元素，每个元素表示一个时段的状态：
    #   ""（空字符串）= 空闲， "◆" = 上课， "Κ" = 考试，等等
    free_all = [r for r in rooms if all(p.strip() == "" for p in r["periods"])]
    partial = [r for r in rooms if any(p.strip() == "" for p in r["periods"])
               and not all(p.strip() == "" for p in r["periods"])]

    # ── 展示汇总统计 ──────────────────────────────────────────────────────────
    print(f"\n  {'='*56}")
    print(f"  📊 查询结果汇总")
    print(f"  {'='*56}")
    print(f"    总教室数: {len(rooms)}")
    print(f"    ✅ 完全空闲: {len(free_all)}")
    print(f"    ⚠️  部分空闲: {len(partial)}")
    print(f"    ❌ 全部占用: {len(rooms) - len(free_all) - len(partial)}")
    print(f"  {'='*56}")

    # ── 列出完全空闲教室（前 20 个） ──────────────────────────────────────────
    if free_all:
        print(f"\n  📋 完全空闲教室 (前20):")
        display_results(free_all[:20])
        if len(free_all) > 20:
            print(f"  ... 还有 {len(free_all) - 20} 个教室")

    # ── 列出部分空闲教室（前 10 个） ──────────────────────────────────────────
    if partial:
        print(f"\n  📋 部分空闲教室 (前10):")
        display_results(partial[:10])
        if len(partial) > 10:
            print(f"  ... 还有 {len(partial) - 10} 个教室")

    # ── 查看某个教室的详细排课 ────────────────────────────────────────────────
    if free_all:
        print("\n  ── 详细查看 ──")
        print("    输入教室序号查看排课详情，或直接回车退出")
        while True:
            idx = input(f"  查看序号 (1-{min(len(free_all), 20)}, 回车退出): ").strip()
            if not idx:
                break
            if idx.isdigit():
                idx = int(idx) - 1
                if 0 <= idx < len(free_all):
                    r = free_all[idx]
                    print(f"\n  📖 {r['name']} ({r['capacity_total']}人)")
                    periods = r["periods"]
                    period_labels = ["1-2节", "3-4节", "5节", "6-7节", "8-9节", "10-11节", "12节"]
                    status_names = {
                        "": "空闲", "◆": "上课", "Ｌ": "临时调课",
                        "Ｇ": "固定调课", "Κ": "考试", "Ｘ": "锁定", "Ｊ": "借用",
                    }
                    for pi, (label, status) in enumerate(zip(period_labels, periods)):
                        s = status.strip()
                        status_text = status_names.get(s, s if s else "空闲")
                        icon = "✅" if s == "" else "❌"
                        print(f"    {icon} {label}: {status_text}")
                    print()
                else:
                    print("  序号超出范围")


# ═══════════════════════════════════════════════════════════════════════════════
#  模式二：快速查询  (python main.py --quick)
# ═══════════════════════════════════════════════════════════════════════════════

def quick_mode(force_vpn=False):
    """
    快速查询模式 —— 一键查询当前周的周一~周五空教室。

    流程：
      1. 输入学号、密码 → 登录
      2. 自动检测当前学期和当前周
      3. 依次查询周一至周五（全天），输出每日空闲教室数量
      4. 列出前 5 个空闲教室名称

    参数:
      force_vpn: True = 强制走 VPN
    """
    # ── 输入凭据 ──────────────────────────────────────────────────────────────
    username = input("  学号: ").strip()
    password = input("  密码: ").strip()

    # ── 登录 ──────────────────────────────────────────────────────────────────
    api = BFUClassroomAPI(username, password, force_vpn=force_vpn)
    print("  ⏳ 正在登录...", end=" ", flush=True)
    if not api.login():
        print("\n  ❌ 登录失败")
        if api.vpn_mode:
            print("    VPN 模式下登录失败，请检查账号密码或 VPN 连接状态")
        else:
            print("    提示: 使用 --vpn 参数可通过 VPN 连接")
        return
    print("✅")

    # ── 获取学期 & 当前周 ─────────────────────────────────────────────────────
    semesters = api.get_semesters()
    current = next((s for s in semesters if s["current"]), semesters[0])
    xnxqh = current["id"]
    current_week = api.get_current_week(xnxqh)

    print(f"  学期: {get_semester_label(xnxqh)}")
    print(f"  当前周: 第{current_week}周")

    # ── 逐天查询（周一~周五） ─────────────────────────────────────────────────
    for day in range(1, 6):  # 1=周一, 5=周五
        print(f"\n  ⏳ 查询{['', '周一', '周二', '周三', '周四', '周五'][day]}...", end=" ", flush=True)
        rooms = api.query(
            xnxqh=xnxqh, jxlbh="",
            zc=str(current_week), zc2=str(current_week),
            xq=str(day), xq2=str(day),
            jc="01", jc2="12",
            jszt="",
        )
        if not rooms:
            print("无数据")
            continue

        # 过滤完全空闲的教室
        free = [r for r in rooms if all(p.strip() == "" for p in r["periods"])]
        print(f"空闲: {len(free)}/{len(rooms)}")

        # 列出前 5 个
        if free:
            for r in free[:5]:
                print(f"    {r['name']} ({r['capacity_total']}人)")
            if len(free) > 5:
                print(f"    ... 还有 {len(free)-5} 个")

    print("\n  ✅ 查询完成")


# ═══════════════════════════════════════════════════════════════════════════════
#  模式三：图形界面（默认模式） (python main.py)
# ═══════════════════════════════════════════════════════════════════════════════
#  注意：这里直接硬编码了学号密码，跳过了登录界面。
#  如果你想改回手动输入登录的方式：
#    恢复使用 gui.py 中的 LoginWindow 类（参考旧版代码）。
# ═══════════════════════════════════════════════════════════════════════════════

def gui_mode(force_vpn=False):
    """
    启动 tkinter 图形界面（默认入口）。

    流程：
      1. 从 bfu_api 导入 BFUClassroomAPI
      2. 用硬编码的学号/密码直接登录教务系统（跳过登录窗口）
      3. 若登录失败 → 弹错误对话框
      4. 若登录成功 → 创建 MainWindow 并启动主循环

    参数:
      force_vpn: True = 跳过直连尝试，直接走 VPN

    如果你要修改的地方：
      ┌──────────────────────────────────────────────┐
      │  改账号：下面 USERNAME / PASSWORD 两行       │
      │  改回手动登录：参考旧版 LoginWindow 写法     │
      └──────────────────────────────────────────────┘
    """
    try:
        from gui import MainWindow
    except ImportError as e:
        print(f"❌ 无法加载 GUI 模块: {e}")
        print("   请确保 tkinter 已安装 (Python 内置)")
        sys.exit(1)

    # ═════════════════════════════════════════════════════════════════════════
    #  【重要】硬编码的教务系统登录凭据
    #  如果需要更改登录账号，直接修改下面两行的值即可。
    #  注意：这里同时用于教务系统和 VPN 门户（统一身份认证）。
    # ═════════════════════════════════════════════════════════════════════════
    USERNAME = "xxxx"       # ← 改学号请改这里的xxxx
    PASSWORD = "xxxx"      # ← 改密码请改这里的xxxx

    # ── 登录（错误使用弹窗，因为 --windowed 打包后无控制台） ─────────────────
    import tkinter.messagebox as mb

    try:
        api = BFUClassroomAPI(USERNAME, PASSWORD, force_vpn=force_vpn)
        ok = api.login()
    except Exception as e:
        mb.showerror("登录失败", f"登录异常: {e}")
        return

    if not ok:
        msg = "登录失败！请检查账号密码或网络连接。"
        if api.vpn_mode:
            msg += "\n(VPN 模式已启用，请检查 VPN 连接状态)"
        mb.showerror("登录失败", msg)
        return

    # ── 启动主界面 ────────────────────────────────────────────────────────────
    app = MainWindow(api)
    if app._initialized:
        app.run()
    else:
        mb.showerror("初始化失败", "主界面初始化失败，请检查网络连接后重试")


# ═══════════════════════════════════════════════════════════════════════════════
#  参数解析 & 入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """
    程序入口：解析命令行参数，分派到对应的模式函数。

    支持的参数：
      --cli           CLI 交互模式（终端操作）
      --quick, -q     快速查询（本周周一~周五）
      --vpn           强制通过 VPN 访问教务系统
      username        可选位置参数（预留，目前未使用）
      password        可选位置参数（预留，目前未使用）

    默认（不带任何参数）→ 启动图形界面。
    """
    parser = argparse.ArgumentParser(
        description="北京林业大学 - 空教室查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                          启动图形界面（默认）
  python main.py --cli                    CLI 交互模式
  python main.py --quick                  快速查询
  python main.py --vpn                    强制使用 VPN 模式
        """
    )
    parser.add_argument("--cli", action="store_true", help="CLI 交互模式")
    parser.add_argument("--quick", "-q", action="store_true", help="快速查询模式")
    parser.add_argument("--vpn", action="store_true", help="强制使用 VPN 模式")
    parser.add_argument("username", nargs="?", help="学号")
    parser.add_argument("password", nargs="?", help="密码")

    args = parser.parse_args()

    # ── 分派到对应模式 ────────────────────────────────────────────────────────
    if args.cli:
        interactive_mode(args.vpn)
    elif args.quick:
        quick_mode(args.vpn)
    else:
        gui_mode(args.vpn)


if __name__ == "__main__":
    main()
