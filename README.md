# 专业发展智诊系统 (Academic Report)

> 信息与机电工程系 · AI赋能专业建设质量监测平台

## 项目简介

专业发展智诊系统是一款面向高职院校专业建设的质量监测与诊断平台，通过数据可视化和AI智能分析，帮助管理部门实时掌握各专业发展状况，及时发现预警指标并生成改进建议。

## 功能特性

### 📊 数据总览
- 专业健康度综合评分排行
- 四色预警体系（🔴红色 / 🟡黄色 / 🔵蓝色 / 🟢绿色）
- 各专业指标卡片式展示

### 🚨 预警中心
- 全系预警指标汇总表
- 预警分布饼图分析
- 指标变化趋势追踪

### 📈 专业对比
- 多专业雷达图横向对比
- 单项指标条形图排行

### 🏆 排行榜
- 综合健康度排名
- 各指标独立排行

### 📋 诊断报告
- AI生成专业发展诊断报告
- 支持网页打印 / PDF下载
- 包含总体评价、预警分析、综合建议

## 技术架构

```
├── frontend/           # 前端 (HTML + ECharts)
│   └── index.html
├── backend/            # 后端 API
│   ├── main.py         # FastAPI 应用
│   ├── app.py          # 路由与业务逻辑
│   └── requirements.txt
└── data/
    └── indicators.json # 指标配置与模拟数据
```

| 层级 | 技术选型 |
|------|---------|
| 前端框架 | 原生 HTML/CSS/JS + ECharts 5.4 |
| 后端框架 | FastAPI 0.110+ |
| 数据格式 | JSON（支持 Excel 数据导入） |
| PDF生成 | ReportLab |
| 认证方式 | JWT (HS256) |

## 核心指标体系

系统内置 15 项专业建设核心指标，涵盖：

| 类别 | 指标 |
|------|------|
| 招生就业 | 招生计划完成率、年终就业率、就业去向落实率、专业相关度 |
| 教学满意 | 课程优良率、校内实训基地满意度、就业单位满意度 |
| 师资队伍 | 生师比、双师型专任教师占比、高级职称专任教师占比、高技术技能人才占比 |
| 产教融合 | 企业订单学生占比、教师人均企业实践时间 |
| 科研成果 | 师均论文著作课题数 |

## 快速部署

### 环境要求
- Python 3.9+
- Windows / Linux / macOS

### 安装步骤

```bash
# 1. 克隆代码
git clone https://gitee.com/xingjian_1/academic-report.git
cd academic-report

# 2. 安装后端依赖
cd backend
pip install -r requirements.txt

# 3. 启动服务
python main.py
```

### 访问地址

启动后访问 http://localhost:8089

**默认登录账号：**
- 用户名：`admin`
- 密码：`admin123`

## 目录结构

```
academic-report/
├── backend/
│   ├── main.py              # 应用入口，API 路由注册
│   ├── app.py               # 核心业务逻辑（数据计算、报告生成、PDF导出）
│   └── requirements.txt     # Python 依赖
├── frontend/
│   └── index.html           # 前端单页应用
├── data/
│   └── indicators.json      # 指标阈值配置与模拟数据
├── .gitignore
└── README.md
```

## 数据来源

系统支持两种数据加载模式：

1. **Excel 导入模式**（生产环境）：读取 `指标、阈值及数据0408.xlsx`，自动解析多专业多年份数据
2. **内置模拟数据**（开发/演示模式）：`data/indicators.json` 内置 5 个专业、3 个学年完整模拟数据，开箱即用

如需接入真实数据，请将 Excel 文件放置于 backend 读取路径，并确保表结构符合规范。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/dashboard` | 仪表盘数据 |
| GET | `/api/major/{id}` | 专业详情 |
| GET | `/api/major/{id}/trends` | 专业趋势 |
| GET | `/api/warnings` | 预警列表 |
| GET | `/api/compare` | 专业对比 |
| GET | `/api/ranking` | 排行榜 |
| GET | `/api/report/{id}` | 生成诊断报告 |
| GET | `/api/report/{id}/pdf` | 下载PDF报告 |

## 四色预警规则

| 颜色 | 含义 | 处置建议 |
|------|------|---------|
| 🔴 红色 | 指标严重不达标 | 立即启动专项改进 |
| 🟡 黄色 | 指标未达优秀 | 制定针对性改进计划 |
| 🔵 蓝色 | 正常但有负向趋势 | 持续监测防止恶化 |
| 🟢 绿色 | 指标达标且趋势向上 | 保持巩固 |

## 开源许可

本项目基于 [Mulan PSL-2.0](https://license.coscl.org.cn/MulanPSL2/) 开源许可。

---

📌 **项目地址**：https://gitee.com/xingjian_1/academic-report
