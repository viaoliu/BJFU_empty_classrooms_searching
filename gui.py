"""
================================================================================
 空教室查询 GUI — tkinter 实现
================================================================================

  【设计原则】
    GUI 层与 API 层完全分离。
    - GUI 仅通过 BFUClassroomAPI 的公开方法与后端交互
    - API 层（bfu_api.py）不依赖 tkinter，可被其他 GUI 框架（如 Java Swing）
      通过 HTTP 包装器替换

  【类说明】
    MainWindow         主窗口 — 查询条件面板 + 结果表格 + 统计卡片
      └─ _build_ui()        构建界面布局
          ├─ _build_query_panel()    左侧：学期/教学楼/周次/星期选择 + 查询按钮
          └─ _build_result_panel()   右侧：统计卡片 + 教室表格 + 底部详情
      ├─ _auto_fill()       自动填充默认值（当前学期、当前周、今天）
      ├─ _do_query()        执行查询（线程中调用 API）
      ├─ _display_results() 展示查询结果
      └─ _on_row_select()   点击表格行时显示教室详情

  【数据流】
    用户选择条件 → 点击查询
      → _do_query() 在新线程调用 api.query()
      → _display_results() 在主线程更新 UI

  【如果你要修改】
    - 改颜色主题：修改开头的 BFU_GREEN / COLOR_* 等常量
    - 调整界面尺寸：修改 MainWindow.__init__ 中的 geometry()
    - 修改查询选项：修改 _build_query_panel() 中的控件
    - 改结果表格列：修改 columns 和 col_widths 数组
    - 改时段数量/名称：修改 PERIOD_NAMES 和对应的 STATUS_MAP

================================================================================
"""

import re
import tkinter as tk
from tkinter import ttk, messagebox, font
import threading
import requests
from bfu_api import BFUClassroomAPI


# ═══════════════════════════════════════════════════════════════════════════════
#  全局配色常量  —  改这里可以换主题色
# ═══════════════════════════════════════════════════════════════════════════════

# ── 主色调（北林绿） ──────────────────────────────────────────────────────────
BFU_GREEN = "#006633"                  # 主色：深绿色（标题栏、按钮）
BFU_GREEN_LIGHT = "#e8f5e9"            # 浅绿色（按钮悬停背景）
BFU_GREEN_DARK = "#004d26"             # 深绿色（按钮按下颜色）

# ── 基础色 ────────────────────────────────────────────────────────────────────
WHITE = "#ffffff"                       # 白色（卡片背景、文字）
LIGHT_GRAY = "#f5f5f5"                  # 浅灰（整体背景）
BORDER_GRAY = "#e0e0e0"                 # 边框灰
TEXT_DARK = "#212121"                   # 深色文字
TEXT_GRAY = "#757575"                   # 灰色文字

# ── 教室状态色 ────────────────────────────────────────────────────────────────
COLOR_FREE = "#d4edda"                  # 空闲 — 绿色
COLOR_BUSY = "#f8d7da"                  # 占用 — 红色
COLOR_OTHER = "#fff3cd"                 # 其他 — 黄色
COLOR_EXAM = "#f0ad4e"                  # 考试 — 橙色
COLOR_CARD_BG = WHITE                   # 卡片背景

# ── 时段状态符号说明（来自教务系统原始数据） ──────────────────────────────────
#   ""（空字符串）= 空闲      "◆" = 正常上课
#   "Ｌ" = 临时调课           "Ｇ" = 固定调课
#   "Κ" = 考试               "Ｘ" = 锁定
#   "Ｊ" = 借用
STATUS_MAP = {
    "": ("空闲", COLOR_FREE),
    "◆": ("上课", COLOR_BUSY),
    "Ｌ": ("调课", COLOR_OTHER),
    "Ｇ": ("调课", COLOR_OTHER),
    "Κ": ("考试", COLOR_EXAM),
    "Ｘ": ("锁定", COLOR_BUSY),
    "Ｊ": ("借用", COLOR_OTHER),
}

# ── 7 个时段的名称（与教务系统返回的 periods[7] 对应） ───────────────────────
PERIOD_NAMES = ["1-2节", "3-4节", "5节", "6-7节", "8-9节", "10-11节", "12节"]


# ═══════════════════════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_semester_label(sem_id: str) -> str:
    """
    将学期 ID（如 "2025-2026-2"）转为可读的中文名称。

    例如: "2025-2026-2" → "2025-2026学年第春学期"
    """
    season_map = {"1": "秋", "2": "春", "3": "夏"}
    parts = sem_id.split("-")
    season = season_map.get(parts[2], parts[2])
    return f"{parts[0]}-{parts[1]}学年第{season}学期"


def get_status_text(status: str) -> str:
    """
    将状态符号转为中文文字。

    例如: "" → "空" ， "◆" → "上课"
    """
    s = status.strip()
    if s == "":
        return "空"
    return STATUS_MAP.get(s, (s, WHITE))[0]


def get_status_color(status: str) -> str:
    """
    根据状态符号返回对应的背景色。

    例如: "" → 绿色， "◆" → 红色
    """
    s = status.strip()
    if s == "":
        return COLOR_FREE
    return STATUS_MAP.get(s, (s, WHITE))[1]


# ═══════════════════════════════════════════════════════════════════════════════
#  【已废弃】登录窗口  (LoginWindow)
# ═══════════════════════════════════════════════════════════════════════════════
#  当前版本已跳过登录步骤，直接硬编码凭据登录。
#  如果你需要恢复手动输入学号密码的登录界面，取消下面类的注释，
#  并在 main.py 的 gui_mode() 中恢复使用 LoginWindow。
#
#  用法（在 main.py 中）：
#     login = LoginWindow(force_vpn=force_vpn)
#     api, ok = login.show()
#     if ok: 启动 MainWindow(api)
# ═══════════════════════════════════════════════════════════════════════════════
# (保留此区域，如需恢复登录窗口请参考 git 历史或旧版 gui.py)


# ═══════════════════════════════════════════════════════════════════════════════
#  主窗口  (MainWindow)
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow:
    """
    空教室查询主界面。

    布局（左右两栏）：
      ┌──────────────────────────────────────────────────┐
      │  顶部标题栏 (header)                              │
      ├──────────────┬───────────────────────────────────┤
      │  左侧查询条件   │  右侧结果面板                     │
      │  (320px 宽)    │  ├─ 统计卡片 (4个)              │
      │  学期 下拉     │  ├─ 教室表格 (Treeview)         │
      │  教学楼 下拉   │  ├─ 底部详情栏                  │
      │  周次 下拉     │  └─ 底部状态栏                  │
      │  星期 下拉     │                                 │
      │  [查询] 按钮   │                                 │
      └──────────────┴───────────────────────────────────┘

    属性:
      api: BFUClassroomAPI          — 后端 API 实例
      semesters: list[dict]         — 学期列表，每项含 id, name, current
      buildings: list[dict]         — 教学楼列表，每项含 id, name
      classrooms: list[dict]        — 最近一次查询的教室数据
      _current_xnxqh: str           — 当前选中的学期 ID
      _initialized: bool            — 初始化是否成功
    """

    def __init__(self, api: BFUClassroomAPI):
        """
        初始化主窗口。

        参数:
          api: 已登录的 BFUClassroomAPI 实例

        流程:
          1. 从 API 获取学期列表和教学楼列表
          2. 创建 tkinter 根窗口
          3. 构建界面（调用 _build_ui）
          4. 自动填充默认值（调用 _auto_fill）
          5. 若过程中发生异常，显示错误并销毁窗口
        """
        self.api = api

        # ── 初始化时从 API 拉取数据 ──────────────────────────────────────────
        # 注意：这里有可能因为网络问题抛出异常，下面的 try/except 会处理
        try:
            self.semesters = api.get_semesters()
            self.buildings = api.get_buildings()
        except (requests.ConnectionError, requests.Timeout, PermissionError) as e:
            messagebox.showerror("初始化失败",
                f"无法获取学期/教学楼数据:\n{e}\n\n请检查网络连接或 VPN 状态。")
            self.semesters = []
            self.buildings = []
        self.classrooms = []             # 查询结果缓存
        self._current_xnxqh = ""         # 当前选中学期 ID
        self._initialized = False        # 标记初始化是否全部完成

        # ── 创建主窗口 ────────────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("空教室查询 - 北京林业大学")
        self.root.geometry("1100x720")    # 窗口默认尺寸：宽1100 高720
        self.root.configure(bg=LIGHT_GRAY)
        self.root.minsize(900, 600)       # 窗口最小尺寸

        # 居中显示
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 1100) // 2
        y = (self.root.winfo_screenheight() - 720) // 2
        self.root.geometry(f"1100x720+{x}+{y}")

        # ── 界面变量 ──────────────────────────────────────────────────────────
        self.sem_var = tk.StringVar()     # 学期下拉框绑定的变量
        self.bld_var = tk.StringVar()     # 教学楼下拉框绑定的变量
        self.week_var = tk.StringVar()    # 周次下拉框绑定的变量
        self.day_var = tk.StringVar()     # 星期下拉框绑定的变量

        # ── 构建界面 ──────────────────────────────────────────────────────────
        try:
            self._build_ui()
            self._auto_fill()
            self._initialized = True
        except Exception as e:
            messagebox.showerror("初始化错误",
                f"程序初始化时出现异常:\n{e}\n\n请检查网络连接后重试。")
            self.root.destroy()
            self._initialized = False
            return

    # ═══════════════════════════════════════════════════════════════════════════
    #  辅助方法 — 统一控件样式
    # ═══════════════════════════════════════════════════════════════════════════

    def _make_label(self, parent, text, **kw):
        """
        创建一个统一样式的 Label。
        你也可以在这里全局修改所有标签的字体、颜色等。
        """
        defaults = {"fg": TEXT_DARK, "bg": LIGHT_GRAY, "font": ("微软雅黑", 10)}
        defaults.update(kw)
        return tk.Label(parent, text=text, **defaults)

    def _make_card(self, parent, **kw):
        """
        创建一个"卡片"样式的 Frame（带边框）。
        用于分组不同的 UI 区域。
        """
        defaults = {"bg": WHITE, "highlightbackground": BORDER_GRAY,
                     "highlightthickness": 1, "relief": "solid"}
        defaults.update(kw)
        return tk.Frame(parent, **defaults)

    # ═══════════════════════════════════════════════════════════════════════════
    #  界面构建
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        """
        构建整体界面布局。
        分三部分：顶部标题栏、左侧查询面板、右侧结果面板。
        """
        # ── 顶部标题栏 ────────────────────────────────────────────────────────
        # 一个深绿色条，显示标题和 VPN 状态
        header = tk.Frame(self.root, bg=BFU_GREEN, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        # 标题文字
        tk.Label(header, text="🏫 空教室查询", bg=BFU_GREEN, fg=WHITE,
                 font=("微软雅黑", 14, "bold")).pack(side="left", padx=16, pady=8)
        self._make_label(header, "北京林业大学教务系统",
                         fg="#a5d6a7", bg=BFU_GREEN,
                         font=("微软雅黑", 9)).pack(side="left", padx=(0, 16))

        # VPN 连接状态指示（右对齐）
        # 直连显示 🔓 ，VPN 显示 🔒
        vpn_text = "🔒 VPN" if self.api.vpn_mode else "🔓 直连"
        vpn_color = "#ffd54f" if self.api.vpn_mode else "#a5d6a7"
        self.vpn_label = tk.Label(header, text=vpn_text, bg=BFU_GREEN,
                                  fg=vpn_color, font=("微软雅黑", 9))
        self.vpn_label.pack(side="right", padx=16, pady=8)

        # ── 主内容区（左右分栏） ──────────────────────────────────────────────
        main_frame = tk.Frame(self.root, bg=LIGHT_GRAY)
        main_frame.pack(fill="both", expand=True, padx=12, pady=12)

        # ── 左侧面板：查询条件（固定宽度 320px） ──────────────────────────────
        left = tk.Frame(main_frame, bg=LIGHT_GRAY, width=320)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)       # 防止内容撑大宽度

        self._build_query_panel(left)

        # ── 右侧面板：结果展示（自动填充剩余空间） ────────────────────────────
        right = tk.Frame(main_frame, bg=LIGHT_GRAY)
        right.pack(side="right", fill="both", expand=True)

        self._build_result_panel(right)

    # ── 左侧：查询条件面板 ─────────────────────────────────────────────────────

    def _build_query_panel(self, parent):
        """
        构建左侧的查询条件卡片。

        包含控件：
          1. 学期下拉框（从 API 获取的学期列表）
          2. 教学楼下拉框（从 API 获取的教学楼列表）
          3. 周次下拉框（第1周~第30周 + 快捷按钮）
          4. 星期下拉框（周一~周日 + 今天按钮）
          5. 查询按钮

        参数:
          parent: 父容器 Frame
        """
        card = self._make_card(parent)
        card.pack(fill="both", expand=True)

        pad = {"padx": 16, "pady": (16, 4)}  # 统一内边距

        # ── 卡片标题 ──────────────────────────────────────────────────────────
        tk.Label(card, text="查询条件", fg=BFU_GREEN, bg=WHITE,
                 font=("微软雅黑", 12, "bold")).pack(anchor="w", **pad)

        # ═══════════════════════════════════════════════════════════════════════
        #  1. 学期选择
        #  从 api.get_semesters() 获取，当前学期默认选中
        # ═══════════════════════════════════════════════════════════════════════
        self._make_label(card, "学期").pack(anchor="w", **pad)
        sem_frame = tk.Frame(card, bg=WHITE)
        sem_frame.pack(fill="x", padx=16)
        sem_values = [s["id"] for s in self.semesters]
        sem_names = [get_semester_label(s["id"]) for s in self.semesters]
        self._current_xnxqh = sem_values[0]
        self.sem_combo = ttk.Combobox(sem_frame, textvariable=self.sem_var,
                                       values=sem_names, state="readonly",
                                       width=30, font=("微软雅黑", 10))
        self.sem_combo.pack(fill="x")

        # ═══════════════════════════════════════════════════════════════════════
        #  2. 教学楼选择
        #  默认"全部教学楼"，从 api.get_buildings() 获取具体列表
        # ═══════════════════════════════════════════════════════════════════════
        self._make_label(card, "教学楼").pack(anchor="w", **pad)
        bld_frame = tk.Frame(card, bg=WHITE)
        bld_frame.pack(fill="x", padx=16)

        bld_values = ["全部教学楼"] + [b["name"] for b in self.buildings]
        self.bld_combo = ttk.Combobox(bld_frame, textvariable=self.bld_var,
                                       values=bld_values, state="readonly",
                                       width=30, font=("微软雅黑", 10))
        self.bld_combo.pack(fill="x")
        self.bld_combo.current(0)

        # ═══════════════════════════════════════════════════════════════════════
        #  3. 周次选择
        #  下拉框 + 本周/下周/下下周 三个快捷按钮
        # ═══════════════════════════════════════════════════════════════════════
        self._make_label(card, "周次").pack(anchor="w", **pad)
        week_frame = tk.Frame(card, bg=WHITE)
        week_frame.pack(fill="x", padx=16)

        week_values = [f"第{i}周" for i in range(1, 31)]   # 第1周 ~ 第30周
        self.week_var = tk.StringVar()
        self.week_combo = ttk.Combobox(week_frame, textvariable=self.week_var,
                                        values=week_values, state="readonly",
                                        width=10, font=("微软雅黑", 10))
        self.week_combo.pack(side="left")

        # 快捷周次按钮
        quick_frame = tk.Frame(card, bg=WHITE)
        quick_frame.pack(fill="x", padx=16, pady=(6, 0))
        for text, offset in [("本周", 0), ("下周", 1), ("下下周", 2)]:
            btn = tk.Button(quick_frame, text=text,
                            command=lambda o=offset: self._quick_week(o),
                            bg=LIGHT_GRAY, fg=TEXT_DARK, relief="flat",
                            font=("微软雅黑", 9), cursor="hand2",
                            activebackground=BFU_GREEN_LIGHT, padx=8)
            btn.pack(side="left", padx=(0, 6))

        # ═══════════════════════════════════════════════════════════════════════
        #  4. 星期选择
        #  下拉框（周一~周日）+ "今天" 快捷按钮
        # ═══════════════════════════════════════════════════════════════════════
        self._make_label(card, "星期").pack(anchor="w", **pad)
        day_frame = tk.Frame(card, bg=WHITE)
        day_frame.pack(fill="x", padx=16)

        day_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self.day_combo = ttk.Combobox(day_frame, textvariable=self.day_var,
                                       values=day_labels, state="readonly",
                                       width=10, font=("微软雅黑", 10))
        self.day_combo.pack(side="left")

        # "今天" 按钮 — 自动选中当前星期
        today_btn = tk.Button(day_frame, text="📅 今天",
                              command=self._set_today_day,
                              bg=LIGHT_GRAY, fg=TEXT_DARK, relief="flat",
                              font=("微软雅黑", 9), cursor="hand2",
                              activebackground=BFU_GREEN_LIGHT, padx=8)
        today_btn.pack(side="left", padx=(8, 0))

        # ═══════════════════════════════════════════════════════════════════════
        #  5. 查询按钮
        # ═══════════════════════════════════════════════════════════════════════
        btn_frame = tk.Frame(card, bg=WHITE)
        btn_frame.pack(fill="x", padx=16, pady=(16, 16))

        self.query_btn = tk.Button(btn_frame, text="🔍  查 询",
                                    command=self._do_query,
                                    bg=BFU_GREEN, fg=WHITE, relief="flat",
                                    font=("微软雅黑", 12, "bold"),
                                    cursor="hand2", pady=4,
                                    activebackground=BFU_GREEN_DARK,
                                    activeforeground=WHITE)
        self.query_btn.pack(fill="x", ipady=4)

    # ── 右侧：结果面板 ─────────────────────────────────────────────────────────

    def _build_result_panel(self, parent):
        """
        构建右侧的结果展示面板。

        从上到下依次：
          1. 统计卡片行（总教室数、完全空闲、部分空闲、全部占用）
          2. 教室表格（Treeview，7 列对应 7 个时段的状态）
          3. 底部详情栏（点击教室行时显示详细信息）
          4. 底部状态栏（查询状态提示）
        """
        # ── 1. 统计卡片行 ─────────────────────────────────────────────────────
        stats_frame = tk.Frame(parent, bg=LIGHT_GRAY)
        stats_frame.pack(fill="x", pady=(0, 8))

        self.stats_cards = {}        # 存 4 个数值 Label，方便更新
        stat_config = [
            ("total", "总教室数", BFU_GREEN),
            ("free", "完全空闲", "#28a745"),
            ("partial", "部分空闲", "#ffc107"),
            ("busy", "全部占用", "#dc3545"),
        ]
        for key, label, color in stat_config:
            card = self._make_card(stats_frame, width=120, height=60)
            card.pack(side="left", padx=(0, 8))
            card.pack_propagate(False)

            tk.Label(card, text=label, fg=TEXT_GRAY, bg=WHITE,
                     font=("微软雅黑", 8)).pack(anchor="w", padx=8, pady=(6, 0))
            value_label = tk.Label(card, text="—", fg=color, bg=WHITE,
                                    font=("微软雅黑", 20, "bold"))
            value_label.pack(anchor="w", padx=8)
            self.stats_cards[key] = value_label

        # ── 2. 结果表格 ───────────────────────────────────────────────────────
        # 使用 ttk.Treeview 实现，列结构：
        #   教室名称 | 容量 | 1-2节 | 3-4节 | 5节 | 6-7节 | 8-9节 | 10-11节 | 12节
        tree_frame = self._make_card(parent)
        tree_frame.pack(fill="both", expand=True)
        tree_frame.pack_propagate(False)

        # 外层容器（让滚动条正常工作）
        tree_container = tk.Frame(tree_frame, bg=WHITE)
        tree_container.pack(fill="both", expand=True, padx=2, pady=2)

        # 垂直和水平滚动条
        vsb = ttk.Scrollbar(tree_container, orient="vertical")
        hsb = ttk.Scrollbar(tree_container, orient="horizontal")

        # 定义列结构
        columns = ("name", "capacity") + tuple(PERIOD_NAMES)
        self.tree = ttk.Treeview(
            tree_container, columns=columns, show="headings",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set,
            height=18,
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        # 列宽和标题
        # 【调整提示】想增删列或改列宽，修改下面两个数组
        col_widths = [140, 60] + [65] * 7    # 教室名140px, 容量60px, 时段各65px
        headings = ["教室名称", "容量"] + PERIOD_NAMES
        for col, width, heading in zip(columns, col_widths, headings):
            self.tree.column(col, width=width, minwidth=50, anchor="center")
            self.tree.heading(col, text=heading)

        self.tree.column("name", anchor="w")        # 教室名左对齐
        self.tree.column("capacity", anchor="center")

        # Grid 布局（让滚动条和表格对齐）
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # 行选择事件绑定
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        # ── 3. 底部详情栏 ─────────────────────────────────────────────────────
        # 点击表格某行时，这里会显示该教室的详细时段状态
        detail_frame = self._make_card(parent, height=50)
        detail_frame.pack(fill="x", pady=(8, 0))
        detail_frame.pack_propagate(False)

        self.detail_label = tk.Label(detail_frame, text="点击教室查看详情",
                                      fg=TEXT_GRAY, bg=WHITE,
                                      font=("微软雅黑", 9), anchor="w")
        self.detail_label.pack(fill="both", padx=12, pady=6)

        # ── 4. 底部状态栏 ─────────────────────────────────────────────────────
        self.status_bar = tk.Label(parent, text="就绪", anchor="w",
                                    fg=TEXT_GRAY, bg=LIGHT_GRAY,
                                    font=("微软雅黑", 9))
        self.status_bar.pack(fill="x", pady=(4, 0))

    # ═══════════════════════════════════════════════════════════════════════════
    #  自动填充（初始化时调用）
    # ═══════════════════════════════════════════════════════════════════════════

    def _find_best_semester(self) -> int:
        """
        智能检测当前最匹配的学期索引。

        优先级：
          1. 教务系统标记为 current=True 的学期
          2. 周次在 1~30 范围内的学期（即当前日期落在这个学期内）
          3. 列表第一个学期
        """
        # 优先级1：教务系统标记的当前学期
        for i, s in enumerate(self.semesters):
            if s["current"]:
                return i

        # 优先级2：周次在 1~30 之间的学期（说明当前日期在这个学期里）
        for i, s in enumerate(self.semesters):
            try:
                w = self.api.get_current_week(s["id"])
                if 1 <= w <= 30:
                    return i
            except Exception:
                continue

        # 优先级3：默认第一个
        return 0

    def _auto_fill(self):
        """
        在初始化时根据当前时间自动填充查询条件。

        逻辑：
          - 学期：智能检测最匹配的当前学期
          - 周次：调用 api.get_current_week() 计算当前周
          - 星期：调用 BFUClassroomAPI.get_current_day() 设为今天

        如果当前学期是通过 API 的 current=True 标记找到的（第一优先级），
        会自动把开学日期倒退推算出来并保存到 semester_config.json，
        这样下次启动时周次计算就更准了。

        如果获取学期数据失败，禁用查询按钮并提示。
        """
        if not self.semesters:
            self.status_bar.config(text="初始化失败：无法获取学期数据")
            self.query_btn.config(state="disabled")
            return

        # ── 学期：智能检测最匹配的学期 ────────────────────────────────────
        current_idx = self._find_best_semester()
        current_sem = self.semesters[current_idx]
        self.sem_combo.current(current_idx)
        self.sem_var.set(get_semester_label(current_sem["id"]))
        self._current_xnxqh = current_sem["id"]

        # ── 如果这是 API 标记的当前学期，倒退推算开学日期并保存 ─────────
        # 这样后续 get_current_week() 会越来越准，不依赖硬编码的默认日期
        if current_sem["current"]:
            try:
                week = self.api.get_current_week(self._current_xnxqh)
                if 1 <= week <= 30:
                    from datetime import date, timedelta
                    today = date.today()
                    # 倒退：开学日期（第一周周一）= 今天 - (当前周 - 1) * 7天
                    start_date = today - timedelta(weeks=week - 1)
                    # 保存到配置文件
                    self.api.update_semester_start_date(
                        self._current_xnxqh,
                        start_date.isoformat()
                    )
            except Exception:
                pass  # 倒退推算失败也没关系，下次继续尝试

        # ── 周次：自动计算当前是第几周 ────────────────────────────────────────
        # 现在如果学期起始日期已经通过上面的倒退推算保存到配置文件，
        # 这里算出来的周次就是准确的
        try:
            current_week = self.api.get_current_week(self._current_xnxqh)
            week_idx = min(current_week, 30) - 1
            self.week_combo.current(week_idx)
            self.week_var.set(f"第{week_idx + 1}周")
        except Exception:
            self.week_var.set("第1周")

        # ── 星期：默认选中今天 ────────────────────────────────────────────────
        self._set_today_day()

    # ═══════════════════════════════════════════════════════════════════════════
    #  快捷按钮回调
    # ═══════════════════════════════════════════════════════════════════════════

    def _quick_week(self, offset: int):
        """
        "本周/下周/下下周" 按钮回调。

        使用当前下拉框选中的学期计算周次（而不是初始化时的缓存值）。
        如果你改了学期下拉框，"本周"按钮会跟着新学期重新计算。

        参数:
          offset: 相对于当前周的偏移（0=本周, 1=下周, 2=下下周）
        """
        # 用下拉框当前选中的学期计算周次，解决切换学期后"本周"不准的问题
        xnxqh = self._get_selected_semester_id()
        current_week = self.api.get_current_week(xnxqh)
        target = min(current_week + offset, 30)
        self.week_combo.current(target - 1)
        self.week_var.set(f"第{target}周")

    def _set_today_day(self):
        """
        "今天" 按钮回调 — 将星期下拉框设为当前星期。
        """
        day_index = BFUClassroomAPI.get_current_day()  # 1=周一 ~ 7=周日
        day_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self.day_combo.current(day_index - 1)
        self.day_var.set(day_labels[day_index - 1])

    # ═══════════════════════════════════════════════════════════════════════════
    #  查询逻辑
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_selected_semester_id(self) -> str:
        """获取当前下拉框选中的学期 ID"""
        idx = self.sem_combo.current()
        if 0 <= idx < len(self.semesters):
            return self.semesters[idx]["id"]
        return self.semesters[0]["id"]

    def _get_selected_building_id(self) -> str:
        """获取当前下拉框选中的教学楼 ID（"" 表示全部教学楼）"""
        idx = self.bld_combo.current() - 1  # 0 = "全部教学楼"，对应 ID 为 ""
        if idx >= 0 and idx < len(self.buildings):
            return self.buildings[idx]["id"]
        return ""

    def _get_query_params(self) -> dict:
        """
        从界面控件收集所有查询参数，组织成 API 需要的格式。

        返回字典包含:
          xnxqh, jxlbh, zc, zc2, xq, xq2, jc, jc2, jszt
        """
        xnxqh = self._get_selected_semester_id()
        jxlbh = self._get_selected_building_id()

        # 从 "第X周" 格式中提取数字
        week_text = self.week_var.get() or "第1周"
        zc = zc2 = re.sub(r"\D", "", week_text) or "1"

        # 星期映射：中文 → 数字
        day_map = {"周一": "1", "周二": "2", "周三": "3", "周四": "4",
                   "周五": "5", "周六": "6", "周日": "7"}
        day_text = self.day_var.get() or "周一"
        xq = xq2 = day_map.get(day_text, "1")

        return {
            "xnxqh": xnxqh,
            "jxlbh": jxlbh,
            "zc": zc,
            "zc2": zc2,
            "xq": xq,
            "xq2": xq2,
            "jc": "01",       # 默认查全天（第1节 ~ 第12节）
            "jc2": "12",
            "jszt": "",       # 全部状态
        }

    def _do_query(self):
        """
        执行查询 — 在新线程中调用 API，避免阻塞 UI。

        流程：
          1. 从界面收集查询参数
          2. 禁用查询按钮，显示"查询中..."
          3. 新线程中调用 api.query()
          4. 主线程中更新结果（_display_results 或 _query_error）
        """
        params = self._get_query_params()
        self._current_xnxqh = params["xnxqh"]

        # ── UI 状态：禁用按钮、显示提示 ──────────────────────────────────────
        self.query_btn.config(state="disabled", text="查询中...")
        self.status_bar.config(text="正在查询，请稍候...")

        def query_thread():
            """后台线程执行查询"""
            try:
                rooms = self.api.query(**params)
                # 查询完成后回到主线程更新 UI
                self.root.after(0, self._display_results, rooms, params)
            except Exception as e:
                self.root.after(0, self._query_error, str(e))

        threading.Thread(target=query_thread, daemon=True).start()

    def _display_results(self, rooms: list, params: dict):
        """
        在 UI 中展示查询结果。

        参数:
          rooms: api.query() 返回的教室列表
          params: 查询参数字典（用于状态栏信息）

        流程：
          1. 恢复查询按钮状态
          2. 清除表格旧数据
          3. 统计并更新 4 个统计卡片
          4. 遍历教室数据填入表格
          5. 更新状态栏
        """
        self.classrooms = rooms
        self.query_btn.config(state="normal", text="🔍  查 询")

        # ── 清除旧数据 ────────────────────────────────────────────────────────
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not rooms:
            self.status_bar.config(text="未查询到教室数据，请调整查询条件")
            for key in self.stats_cards:
                self.stats_cards[key].config(text="—")
            self.detail_label.config(text="无数据")
            return

        # ── 统计 ──────────────────────────────────────────────────────────────
        # periods 数组有 7 个字符串，"" 表示空闲，非空表示被占用
        free_all = sum(1 for r in rooms
                       if all(p.strip() == "" for p in r["periods"]))
        partial = sum(1 for r in rooms
                      if any(p.strip() == "" for p in r["periods"])
                      and not all(p.strip() == "" for p in r["periods"]))
        busy = len(rooms) - free_all - partial

        # 更新统计卡片
        self.stats_cards["total"].config(text=str(len(rooms)))
        self.stats_cards["free"].config(text=str(free_all))
        self.stats_cards["partial"].config(text=str(partial))
        self.stats_cards["busy"].config(text=str(busy))

        # ── 填入表格 ──────────────────────────────────────────────────────────
        for room in rooms:
            values = [room["name"], f'{room["capacity_total"]}人']
            for p in room["periods"]:
                values.append(get_status_text(p))

            self.tree.insert("", "end", values=values)

        # ── 更新状态栏 ────────────────────────────────────────────────────────
        self.status_bar.config(
            text=f"查询完成 · 第{params['zc']}-{params['zc2']}周 · "
                 f"共 {len(rooms)} 个教室 · "
                 f"空闲 {free_all} · 部分 {partial} · 占用 {busy}"
        )
        self.detail_label.config(text=f"共 {len(rooms)} 个教室 | "
                                      f"🟢空闲 {free_all} | "
                                      f"🟡部分 {partial} | "
                                      f"🔴占用 {busy}")

    def _query_error(self, error_msg: str):
        """
        查询失败时的处理 — 恢复按钮状态并弹窗报错。

        参数:
          error_msg: 异常信息字符串
        """
        self.query_btn.config(state="normal", text="🔍  查 询")
        self.status_bar.config(text=f"查询失败: {error_msg}")
        messagebox.showerror("查询失败", f"查询出错:\n{error_msg}")

    # ═══════════════════════════════════════════════════════════════════════════
    #  行点击事件 — 显示教室详情
    # ═══════════════════════════════════════════════════════════════════════════

    def _on_row_select(self, event):
        """
        表格行被点击时的回调。
        在底部详情栏显示该教室 7 个时段的占用/空闲状态。
        """
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        values = self.tree.item(item, "values")
        if not values:
            return

        name = values[0]
        # 从缓存中找对应的教室数据
        room = None
        for r in self.classrooms:
            if r["name"] == name:
                room = r
                break
        if not room:
            return

        # 构建详情文本
        lines = [f"📖 {room['name']} ({room['capacity_total']}人/{room['capacity_exam']}人)"]
        for i, (pn, status) in enumerate(zip(PERIOD_NAMES, room["periods"])):
            s = status.strip()
            icon = "🟢" if s == "" else "🔴"
            text = get_status_text(status)
            lines.append(f"{icon} {pn}: {text}")

        self.detail_label.config(text=" | ".join(lines))

    # ═══════════════════════════════════════════════════════════════════════════
    #  运行主循环
    # ═══════════════════════════════════════════════════════════════════════════

    def run(self):
        """启动 tkinter 主事件循环。"""
        self.root.mainloop()
