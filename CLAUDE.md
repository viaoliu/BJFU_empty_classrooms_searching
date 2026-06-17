# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**空教室查询** — 北京林业大学教务系统空教室查询工具。通过登录强智教务系统 API，自动识别验证码，查询指定时间、地点的空闲教室情况。

## 核心文件

| 文件 | 说明 |
|------|------|
| `main.py` | 入口文件，支持 CLI 交互、快速查询、GUI 图形界面 |
| `bfu_api.py` | 教务系统 API 封装，纯逻辑层，可与任意 GUI 框架配合 |
| `gui.py` | tkinter GUI 实现，仅通过 `BFUClassroomAPI` 公开方法与后端交互 |
| `semester_config.json` | 自动生成，存储学期起始日期用于周次计算 |
| `requirements.txt` | 依赖管理 |

## 技术栈

- **Python 3** + `requests` (HTTP 会话)
- **ddddocr** (验证码自动识别)
- **tkinter** (GUI，Python 内置，可被 Java 替换)
- **强智教务系统** (湖南强智科技)

## 使用命令

```bash
# 启动图形界面（默认）
python main.py

# CLI 交互模式
python main.py --cli

# 快速查询当前周
python main.py --quick

# 强制使用 VPN 模式（校园网不可用时）
python main.py --vpn

# CLI 带 VPN
python main.py --cli --vpn
```

## VPN 自动回退

当校园网不可用时自动通过 VPN (`http://vpn1.bjfu.edu.cn`) 访问教务系统。

**工作原理**：
1. 先尝试直连 `newjwxt.bjfu.edu.cn`（超时 5s）
2. 若网络错误（`ConnectionError`/`Timeout`），自动登录 VPN 门户
3. 通过 VPN URL 重写（`/http/newjwxt.bjfu.edu.cn<path>`）访问教务系统
4. 使用与教务系统相同的学号/密码登录 VPN（统一身份认证）

**强制 VPN**：使用 `--vpn` 参数跳过直连，直接走 VPN。

**VPN 门户**：深信服 SSL VPN 典型模式，登录页自动解析 form action。

## 环境配置

- Python 环境管理器: Conda
- 依赖: `pip install ddddocr requests`

## 架构设计

API 层 (`bfu_api.py`) 与 GUI 层 (`gui.py`) 完全分离：

```
main.py (入口)
  ├── (默认) → 启动 gui.py，gui.py 仅调用 BFUClassroomAPI
  ├── --cli → 直接调用 BFUClassroomAPI 方法
  └── --quick → 直接调用 BFUClassroomAPI 方法
```

**未来 Java 迁移**：只需在 `bfu_api.py` 上包裹 HTTP 服务（Flask/FastAPI），
Java GUI 通过 REST API 调用，不需改动 `bfu_api.py` 内部逻辑。

## BFUClassroomAPI 公开方法

| 方法 | 返回 | 说明 |
|------|------|------|
| `login()` | bool | 登录教务系统 |
| `get_semesters()` | list[dict] | 获取学期列表，含 `current` 标记 |
| `get_buildings()` | list[dict] | 获取教学楼列表 |
| `query(xnxqh, jxlbh, zc/zc2, xq/xq2, jc/jc2, jszt)` | list[dict] | 查询空教室，返回结构化教室列表 |
| `find_empty(classrooms, require_all_periods)` | list[dict] | 过滤空闲教室 |
| `get_current_week(xnxqh)` | int | 计算当前教学周 |
| `get_current_day()` | int | 当前星期 (1=周一) |
| `get_current_period()` | tuple[str,str] | 建议的查询节次范围 |
| `update_semester_start_date(xnxqh, date)` | None | 设置学期起始日期 |

## 关键 API 端点

| 端点 | 用途 |
|------|------|
| `POST /jsxsd/xk/LoginToXk` | 登录 (USERNAME, PASSWORD, RANDOMCODE) |
| `GET /jsxsd/verifycode.servlet` | 验证码图片 |
| `GET /jsxsd/kbxx/jsjy_query?Ves632DSdyV=NEW_XSD_PYGL` | 查询页面 (学期/教学楼下拉数据) |
| `POST /jsxsd/kbxx/jsjy_query2` | 提交查询 |

## 数据模型

### 查询参数
- `xnxqh` — 学期标识, 如 `"2025-2026-2"` (春季)
- `jxlbh` — 教学楼, `"001"`=一教, `"003"`=二教, `""`=全部
- `zc/zc2` — 周次起止 (1-30)
- `xq/xq2` — 星期起止 (1=周一 ~ 7=周日)
- `jc/jc2` — 节次起止 (01-12)
- `jszt` — 教室状态, `""`=全部
- `typewhere` — 固定值 `"jszq"`

### 回报数据
每个教室含 `name`, `capacity_total`, `capacity_exam`, `periods[7]`：
- `""` (空) = 空闲
- `◆` = 正常上课 / `Ｌ` / `Ｇ` = 调课
- `Κ` = 考试 / `Ｘ` = 锁定 / `Ｊ` = 借用

## 周次自动检测

通过 `semester_config.json` 配置学期起始日期，计算：
```
当前周 = (今天 - 学期起始日期).days // 7 + 1
```

默认校历：
- 秋季 (X-1): 9月1日
- 春季 (X-2): 2月23日
- 夏季 (X-3): 7月1日

用户可通过 GUI 或直接编辑 JSON 文件校正。
