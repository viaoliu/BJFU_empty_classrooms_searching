"""
北京林业大学 空教室查询 API
支持自动登录、验证码识别、教室查询、当前周次检测

设计原则：API 层与 GUI 层完全分离。
GUI 仅通过 BFUClassroomAPI 公开方法调用后端逻辑。
后续替换为 Java GUI 只需加 HTTP 包装器，不需改动此文件。
"""

import json
import os
import re
from datetime import date, datetime

import requests
import ddddocr


class BFUClassroomAPI:
    """北林教务系统空教室查询API"""

    BASE_URL = "http://newjwxt.bjfu.edu.cn"
    VPN_BASE_URL = "http://vpn1.bjfu.edu.cn"

    # 路径常量（不含 base，供 _url() 动态拼接）
    _PATH_BASE = ""
    _PATH_LOGIN = "/jsxsd/xk/LoginToXk"
    _PATH_CAPTCHA = "/jsxsd/verifycode.servlet"
    _PATH_QUERY_PAGE = "/jsxsd/kbxx/jsjy_query?Ves632DSdyV=NEW_XSD_PYGL"
    _PATH_QUERY = "/jsxsd/kbxx/jsjy_query2"

    CONFIG_FILE = "semester_config.json"

    # 北林节次时间表 (用于自动判断当前节次)
    PERIOD_TIMES = [
        ("01", "1-2节", 7*60, 9*60+40, "08:00-09:40"),
        ("03", "3-4节", 9*60+40, 11*60+40, "10:00-11:40"),
        ("05", "5节", 11*60+40, 12*60+20, "11:40-12:20"),
        ("06", "6-7节", 12*60+20, 15*60+10, "13:30-15:10"),
        ("08", "8-9节", 15*60+10, 17*60, "15:20-17:00"),
        ("10", "10-11节", 17*60, 18*60+50, "17:10-18:50"),
        ("12", "12节", 18*60+50, 21*60, "19:00-19:50"),
    ]

    PERIOD_LABELS = ["0102", "0304", "05", "0607", "0809", "1011", "12"]
    DAY_LABELS = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    def __init__(self, username: str, password: str, force_vpn: bool = False):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })
        self.ocr = ddddocr.DdddOcr()
        self.logged_in = False
        self._vpn_mode = force_vpn       # 是否使用 VPN 回退
        self._vpn_logged_in = False      # VPN 门户是否已登录

    # ── URL 解析 ─────────────────────────────────────────

    def _url(self, path: str) -> str:
        """根据当前模式（直连/VPN）解析完整 URL"""
        if self._vpn_mode:
            return f"{self.VPN_BASE_URL}/http/newjwxt.bjfu.edu.cn{path}"
        return f"{self.BASE_URL}{path}"

    # ── VPN 登录 ─────────────────────────────────────────

    def _vpn_login(self) -> bool:
        """
        登录 VPN 门户 vpn1.bjfu.edu.cn。

        流程:
          1. GET VPN_BASE_URL → 建立会话 cookie
          2. 解析登录页 form action 和隐藏字段
          3. POST 凭据到登录端点
          4. 验证登录是否成功

        注意：VPN 的登录页面结构因深信服版本而异，
        若默认方式失败，可能需要手动调整 url 或 data 参数。
        """
        if self._vpn_logged_in:
            return True

        try:
            # Step 1: 获取登录页（建立会话）
            resp = self.session.get(self.VPN_BASE_URL, timeout=10)

            # Step 2: 从 HTML 解析 form action
            # 深信服 VPN 典型登录端点
            login_url = f"{self.VPN_BASE_URL}/por/login.csp"

            form_match = re.search(
                r'<form[^>]*action=[\'"]([^\'"]+)[\'"][^>]*>',
                resp.text, re.IGNORECASE
            )
            if form_match:
                action = form_match.group(1)
                if action.startswith("http"):
                    login_url = action
                elif action.startswith("/"):
                    login_url = f"{self.VPN_BASE_URL}{action}"

            # Step 3: POST 凭据
            # 深信服典型字段名: username, password, suffix
            login_resp = self.session.post(login_url, data={
                "username": self.username,
                "password": self.password,
                "suffix": "",
            }, timeout=10)

            # Step 4: 验证登录是否成功
            # 成功时 URL 一般会跳转到 por/index.csp 或类似页面
            self._vpn_logged_in = (
                "por/index" in login_resp.url
                or "index.csp" in login_resp.url
                or ("error" not in login_resp.text.lower()
                    and "登录" not in login_resp.text
                    and len(login_resp.text) > 100)
            )
            return self._vpn_logged_in

        except (requests.ConnectionError, requests.Timeout) as e:
            return False

    # ── 验证码识别 ───────────────────────────────────────

    def _get_captcha(self) -> str:
        """获取验证码并自动识别"""
        r = self.session.get(self._url(self._PATH_CAPTCHA), timeout=10)
        return self.ocr.classification(r.content)

    # ── 登录（含自动 VPN 回退） ────────────────────────────

    def login(self) -> bool:
        """
        登录教务系统，返回是否成功。

        自动回退逻辑:
          1. 先尝试直连 newjwxt.bjfu.edu.cn
          2. 若因网络错误失败，自动登录 VPN 门户并走 VPN 重试
          3. 若已设置 force_vpn=True，直接走 VPN
        """
        # 强制 VPN 模式：跳过直连
        if not self._vpn_mode:
            # Step 1: 尝试直连
            try:
                self.session.get(self.BASE_URL, timeout=5)
                captcha = self._get_captcha()
                r = self.session.post(self._url(self._PATH_LOGIN), data={
                    "USERNAME": self.username,
                    "PASSWORD": self.password,
                    "RANDOMCODE": captcha,
                }, timeout=10)
                self.logged_in = "xsMain" in r.url or "main" in r.url
                if self.logged_in:
                    return True
            except (requests.ConnectionError, requests.Timeout):
                print("\n[VPN] 直连教务系统失败，正在尝试 VPN 回退...")

        # Step 2: VPN 回退
        if not self.logged_in:
            if not self._vpn_login():
                print("[VPN] VPN 门户登录失败，请检查网络或账号密码")
                return False

            self._vpn_mode = True
            print("[VPN] VPN 门户登录成功，正在通过 VPN 连接教务系统...")

            # Step 3: 通过 VPN 重试学术系统登录
            try:
                self.session.get(self._url(self._PATH_BASE), timeout=15)
                captcha = self._get_captcha()
                r = self.session.post(self._url(self._PATH_LOGIN), data={
                    "USERNAME": self.username,
                    "PASSWORD": self.password,
                    "RANDOMCODE": captcha,
                }, timeout=15)
                self.logged_in = "xsMain" in r.url or "main" in r.url
            except (requests.ConnectionError, requests.Timeout) as e:
                print(f"[VPN] VPN 模式下登录教务系统失败: {e}")

        return self.logged_in

    @property
    def vpn_mode(self) -> bool:
        """是否正在使用 VPN 连接"""
        return self._vpn_mode

    def get_buildings(self) -> list[dict]:
        """获取教学楼列表"""
        if not self.logged_in:
            raise PermissionError("请先登录")

        r = self.session.get(self._url(self._PATH_QUERY_PAGE), timeout=10)
        r.encoding = "utf-8"

        buildings = re.findall(
            r'<option[^>]*value="(00[^"]*)"[^>]*>\s*([^<]+?)\s*</option>',
            r.text
        )
        return [{"id": b[0], "name": b[1].strip()} for b in buildings]

    def get_semesters(self) -> list[dict]:
        """获取可选学期列表"""
        if not self.logged_in:
            raise PermissionError("请先登录")

        r = self.session.get(self._url(self._PATH_QUERY_PAGE), timeout=10)
        r.encoding = "utf-8"

        # 匹配所有学期 option 标签，捕获完整标签和 value
        option_tags = re.findall(
            r'(<option[^>]*value="(\d{4}-\d{4}-\d)"[^>]*>)',
            r.text
        )
        result = []
        for tag, val in option_tags:
            # selected=true 表示该学期是当前学期
            is_current = "selected" in tag
            # 季节后缀: 1=秋季, 2=春季, 3=夏季
            season_map = {"1": "秋", "2": "春", "3": "夏"}
            season = season_map.get(val[-1], val[-1])
            result.append({
                "id": val,
                "name": f"{val[:9]}学年度第{season}学期",
                "current": is_current,
            })
        return result

    @staticmethod
    def parse_schedule(html_text: str) -> list[dict]:
        """
        解析查询结果HTML，返回教室列表
        每个教室包含: name, capacity, periods(7个时段的状态)
        """
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.DOTALL | re.IGNORECASE)
        classrooms = []

        for row in rows:
            cells = re.findall(
                r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL
            )
            if len(cells) < 8:
                continue

            name_raw = re.sub(r"<[^>]+>", "", cells[0]).strip()

            # 教室行以 "-->" 开头
            if not name_raw.startswith("-->"):
                continue

            name_clean = name_raw.replace("-->", "").strip()

            # 解析教室名和容量: 一教101(180/90)
            capacity_match = re.search(r"\((\d+)/(\d+)\)", name_clean)
            capacity_total = int(capacity_match.group(1)) if capacity_match else 0
            capacity_exam = int(capacity_match.group(2)) if capacity_match else 0
            room_name = re.sub(r"\(\d+/\d+\)", "", name_clean).strip()

            # 解析7个时段的占用情况
            periods = []
            for cell in cells[1:]:
                content = re.sub(r"<[^>]+>", "", cell).strip()
                periods.append(content)

            classrooms.append({
                "name": room_name,
                "raw": name_clean,
                "capacity_total": capacity_total,
                "capacity_exam": capacity_exam,
                "periods": periods,
            })

        return classrooms

    def query(self, xnxqh: str = "", jxlbh: str = "",
              zc: str = "", zc2: str = "",
              xq: str = "", xq2: str = "",
              jc: str = "", jc2: str = "",
              jszt: str = "") -> list[dict]:
        """
        查询空教室

        参数:
            xnxqh: 学期 (如 "2025-2026-2")
            jxlbh: 教学楼编号 (如 "001"=一教, ""=全部)
            zc/zc2: 周次起止 (1-30)
            xq/xq2: 星期起止 (1-7)
            jc/jc2: 节次起止 (01-12)
            jszt: 教室状态 (""=全部, "5"=空闲, "1"=正常上课等)

        返回: 教室列表 (同 parse_schedule)
        """
        if not self.logged_in:
            raise PermissionError("请先登录")

        data = {
            "xnxqh": xnxqh,
            "jxlbh": jxlbh,
            "jsbh": "",
            "bjfh": "=",
            "rnrs": "",
            "jszt": jszt,
            "zc": zc,
            "zc2": zc2,
            "xq": xq,
            "xq2": xq2,
            "jc": jc,
            "jc2": jc2,
            "typewhere": "jszq",
        }

        r = self.session.post(self._url(self._PATH_QUERY), data=data, timeout=15)
        r.encoding = "utf-8"

        return self.parse_schedule(r.text)

    @staticmethod
    def is_free(status: str) -> bool:
        """判断某时段是否空闲"""
        return status.strip() == ""

    def find_empty(self, classrooms: list[dict],
                   require_all_periods: bool = True) -> list[dict]:
        """
        过滤出空闲教室

        Args:
            classrooms: query() 返回的教室列表
            require_all_periods: True=全部时段都空闲, False=任一时段空闲即可
        """
        result = []
        for room in classrooms:
            free_periods = [
                i + 1 for i, p in enumerate(room["periods"])
                if self.is_free(p)
            ]
            if require_all_periods and len(free_periods) == 7:
                result.append({**room, "free_periods": free_periods})
            elif not require_all_periods and free_periods:
                result.append({**room, "free_periods": free_periods})
        return result

    # ================================================================
    # 周次自动检测 (可被 Java 后端复用)
    # ================================================================

    def _load_semester_config(self) -> dict:
        """加载学期起始日期配置"""
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"semesters": {}}

    def _save_semester_config(self, config: dict):
        """保存学期起始日期配置"""
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def get_semester_start_date(self, xnxqh: str) -> date:
        """
        获取学期起始日期（第一周周一）。

        优先从 semester_config.json 读取，不存在则按默认校历返回。

        默认校历:
          - 秋季 (X-1): 9月1日
          - 春季 (X-2): 3月9日
          - 夏季 (X-3): 7月1日
        """
        config = self._load_semester_config()
        if xnxqh in config.get("semesters", {}):
            return date.fromisoformat(config["semesters"][xnxqh])

        season = xnxqh[-1]
        year_start = int(xnxqh[:4])
        year_end = int(xnxqh[5:9])
        # 秋季用第一年，春季/夏季用第二年
        default_map = {
            "1": date(year_start, 9, 1),
            "2": date(year_end, 3, 9),
            "3": date(year_end, 7, 1),
        }
        return default_map.get(season, date.today())

    def update_semester_start_date(self, xnxqh: str, start_date: str):
        """
        更新/设置学期起始日期。start_date 格式: 'YYYY-MM-DD'

        供 GUI 设置页面调用，用户可校正自动检测的周次。
        """
        config = self._load_semester_config()
        config.setdefault("semesters", {})[xnxqh] = start_date
        self._save_semester_config(config)

    def get_current_week(self, xnxqh: str) -> int:
        """
        计算当前教学周。

        公式: (今天 - 学期起始日期).days // 7 + 1
        最小返回 1（开学前也返回 1）。
        """
        start = self.get_semester_start_date(xnxqh)
        delta = (date.today() - start).days
        return max(1, delta // 7 + 1)

    @staticmethod
    def get_current_day() -> int:
        """返回当前星期 (1=周一 ~ 7=周日)"""
        return datetime.now().isoweekday()

    @staticmethod
    def get_current_period() -> tuple[str, str]:
        """
        根据当前时间返回建议的查询节次范围。

        返回: (start_period, end_period)，如 ('01', '12')
        逻辑：取当前时间所在的节次到最后。
        """
        now_minutes = datetime.now().hour * 60 + datetime.now().minute

        for i, (pid, _, start, end, _) in enumerate(BFUClassroomAPI.PERIOD_TIMES):
            if start <= now_minutes < end:
                return (pid, "12")

        return ("01", "12")


def display_results(classrooms: list[dict], day_label: str = ""):
    """友好的结果展示"""
    if not classrooms:
        print("  没有找到符合条件的教室")
        return

    header = f"  教室名称{' ':<12}容量  {'  '.join(BFUClassroomAPI.PERIOD_LABELS)}"
    if day_label:
        header = f"{day_label}\n{header}"
    print(header)
    print("  " + "-" * 60)

    STATUS_SYMBOL = {
        "": "  ",           # 空闲
        "◆": "课",          # 正常上课
        "Ｌ": "调",         # 临时调课
        "Ｇ": "调",         # 固定调课
        "Κ": "考",         # 考试
        "Ｘ": "锁",         # 锁定
        "Ｊ": "借",         # 借用
    }

    for room in classrooms:
        cap = f"{room['capacity_total']}"
        display_periods = []
        for p in room["periods"]:
            p_stripped = p.strip()
            if p_stripped == "":
                display_periods.append("空")
            elif p_stripped in STATUS_SYMBOL:
                display_periods.append(STATUS_SYMBOL[p_stripped])
            else:
                display_periods.append(p_stripped[:1])

        periods_str = "  ".join(f"{s:>2}" for s in display_periods)
        print(f"  {room['name']:<18} {cap:>3}人  {periods_str}")


def main():
    """命令行交互入口"""
    import sys

    print("=" * 60)
    print("  北京林业大学 - 空教室查询工具")
    print("=" * 60)

    # 登录
    username = input("  学号: ").strip()
    password = input("  密码: ").strip()

    api = BFUClassroomAPI(username, password)
    print("\n  正在登录...")
    if not api.login():
        print("  ❌ 登录失败，请检查账号密码或验证码")
        return
    print("  ✅ 登录成功！\n")

    # 获取学期
    semesters = api.get_semesters()
    print("  可选学期:")
    for i, s in enumerate(semesters):
        mark = " [当前]" if s["current"] else ""
        print(f"    {i}: {s['name']}{mark}")

    # 默认选当前学期
    sem_idx = 0
    for i, s in enumerate(semesters):
        if s["current"]:
            sem_idx = i
            break
    sem_input = input(f"\n  选择学期 (0-{len(semesters)-1}, 默认=sem_idx): ").strip()
    if sem_input:
        sem_idx = int(sem_input)

    xnxqh = semesters[sem_idx]["id"]
    print(f"  已选择: {semesters[sem_idx]['name']}")

    # 获取教学楼
    buildings = api.get_buildings()
    buildings.insert(0, {"id": "", "name": "全部教学楼"})
    print("\n  教学楼:")
    for i, b in enumerate(buildings):
        print(f"    {i}: {b['name']}")
    bld_input = input(f"  选择教学楼 (0-{len(buildings)-1}, 默认=0): ").strip()
    bld_idx = int(bld_input) if bld_input else 0
    jxlbh = buildings[bld_idx]["id"]
    print(f"  已选择: {buildings[bld_idx]['name']}")

    # 周次
    zc = input("  起始周次 (1-30, 默认=1): ").strip() or "1"
    zc2 = input("  结束周次 (1-30, 默认=1): ").strip() or "1"

    # 星期
    xq = input("  起始星期 (1=周一, 7=周日, 默认=1): ").strip() or "1"
    xq2 = input("  结束星期 (1-7, 默认=xq): ").strip() or xq

    # 节次
    jc = input("  起始节次 (1-12, 默认=1): ").strip() or "1"
    jc2 = input("  结束节次 (1-12, 默认=12): ").strip() or "12"
    # 节次编号补零
    jc = jc.zfill(2)
    jc2 = jc2.zfill(2)

    print(f"\n  正在查询第{zc}-{zc2}周, 周{xq}-{xq2}, 节次{jc}-{jc2}...")

    # 查询
    classrooms = api.query(
        xnxqh=xnxqh, jxlbh=jxlbh,
        zc=zc, zc2=zc2,
        xq=xq, xq2=xq2,
        jc=jc, jc2=jc2,
        jszt="",
    )

    if not classrooms:
        print("\n  没有查询到教室数据")
        return

    print(f"\n  共查询到 {len(classrooms)} 个教室")

    # 找完全空闲的
    day_idx = int(xq)
    day_label = BFUClassroomAPI.DAY_LABELS.get(day_idx, "")
    free = api.find_empty(classrooms, require_all_periods=True)
    partial = api.find_empty(classrooms, require_all_periods=False)

    print(f"\n  ✅ 完全空闲: {len(free)} 个教室")
    if free:
        display_results(free[:20], f"=== 完全空闲教室 (第{zc}-{zc2}周 {day_label}) ===")
        if len(free) > 20:
            print(f"  ... 还有 {len(free)-20} 个教室")

    print(f"\n  ⚠️  部分空闲: {len(partial) - len(free)} 个教室")
    if partial:
        display_results(partial[:10],
                        f"=== 部分空闲教室 (第{zc}-{zc2}周 {day_label}) ===")
        if len(partial) > 10:
            print(f"  ... 还有 {len(partial)-10} 个教室")


if __name__ == "__main__":
    main()
