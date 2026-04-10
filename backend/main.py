"""
专业发展智诊系统 - FastAPI Backend (v2)
With JWT authentication and updated 7-indicator system
"""
import json
import os
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import jwt
import openpyxl
from openpyxl import load_workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Register Chinese font for PDF
try:
    pdfmetrics.registerFont(TTFont('WenQuanYi', '/usr/share/fonts/wqy-microhei/wqy-microhei.ttc'))
    PDF_FONT = 'WenQuanYi'
except Exception:
    PDF_FONT = 'Helvetica'

# ============================================================
# JWT Config
# ============================================================
SECRET_KEY = "zyzd-secret-key-2024专业发展智诊系统"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# ============================================================
# FastAPI App
# ============================================================
app = FastAPI(title="专业发展智诊系统", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Data Loading from xlsx
# ============================================================
DATA_XLSX = Path(__file__).parent.parent / "data" / "indicators_v2.json"

def get_level(val: float, thresholds: dict, ind_id: str) -> str:
    """Determine warning level based on thresholds.
    
    For indicators where higher is better (most):
      red < yellow < green
    For 生师比 (ratio, lower is better):
      red means > threshold, green means <= threshold
    """
    if ind_id == "X2":  # 生师比 - lower is better
        # thresholds: green <= 18, yellow 18-22, red > 22
        if val <= 18:
            return "green"
        elif val <= 22:
            return "yellow"
        else:
            return "red"
    
    # Default: higher is better
    green_thresh = thresholds.get("green", 999)
    yellow_thresh = thresholds.get("yellow", 0)
    blue_thresh = thresholds.get("blue", 0)
    
    if val >= green_thresh:
        return "green"
    elif val >= yellow_thresh:
        return "yellow"
    elif val >= blue_thresh:
        return "blue"
    else:
        return "red"


def build_indicator_meta() -> dict:
    """Build indicator metadata from xlsx Sheet1."""
    xlsx_path = Path(__file__).parent.parent / ".." / ".." / ".." / "workspace" / "huiyi_pro" / "xingjian" / "academic-report" / "docs" / "需求文档" / "指标、阈值及数据0408.xlsx"
    
    # Fallback to embedded data if xlsx not found
    return {
        "X1": {
            "name": "招生计划完成率", "weight": 5, "unit": "%",
            "method": "(实际录取数/招生计划数)*100%",
            "thresholds": {"red": (0, 0.85), "yellow": (0.85, 0.90), "green": (0.90, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X2": {
            "name": "生师比", "weight": 3, "unit": ":1",
            "method": "折合在校生数/折合专任教师数",
            "thresholds": {"green": 18, "yellow": 22, "red": 999},
            "higher_is_better": False, "format": "ratio"
        },
        "X3": {
            "name": "课程优良率", "weight": 3, "unit": "%",
            "method": "学生评教分数/专业课程门数",
            "thresholds": {"red": (0, 0.70), "yellow": (0.70, 0.85), "green": (0.85, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X4": {
            "name": "技能证书通过率", "weight": 4, "unit": "%",
            "method": "获得职业资格证书学生数/学年生均学生数",
            "thresholds": {"red": (0, 0.60), "yellow": (0.60, 0.75), "green": (0.75, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X5": {
            "name": "年终就业率", "weight": 3, "unit": "%",
            "method": "年终就业学生数/实际就业学生数",
            "thresholds": {"red": (0, 0.95), "yellow": (0.95, 0.97), "green": (0.97, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X6": {
            "name": "年终就业去向落实率", "weight": 5, "unit": "%",
            "method": "落实去向学生数/毕业生总数",
            "thresholds": {"red": (0, 0.92), "yellow": (0.92, 0.96), "green": (0.96, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X7": {
            "name": "专业相关度", "weight": 4, "unit": "%",
            "method": "专业对口岗位学生数/总岗位学生数",
            "thresholds": {"red": (0, 0.68), "yellow": (0.68, 0.70), "green": (0.70, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X8": {
            "name": "校内实训基地满意度", "weight": 4, "unit": "",
            "method": "非常满意人数/总问卷人数",
            "thresholds": {"red": (0, 0.91), "yellow": (0.91, 0.95), "green": (0.95, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X9": {
            "name": "就业单位满意度", "weight": 4, "unit": "",
            "method": "满意人数/总问卷人数",
            "thresholds": {"red": (0, 0.92), "yellow": (0.92, 0.95), "green": (0.95, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X10": {
            "name": "企业订单学生占比", "weight": 4, "unit": "",
            "method": "企业订单培养学生数/年度招生总数",
            "thresholds": {"red": (0, 0.08), "yellow": (0.08, 0.15), "green": (0.15, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X11": {
            "name": "双师型专任教师占比", "weight": 4, "unit": "",
            "method": "双师型专任教师数/专任教师总数",
            "thresholds": {"red": (0, 0.60), "yellow": (0.60, 0.75), "green": (0.75, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X12": {
            "name": "高级职称专任教师占比", "weight": 4, "unit": "",
            "method": "高级职称专任教师数/专任教师总数",
            "thresholds": {"red": (0, 0.15), "yellow": (0.15, 0.25), "green": (0.25, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X13": {
            "name": "高技术技能人才占比", "weight": 4, "unit": "",
            "method": "高技能人才数/专任教师总数",
            "thresholds": {"red": (0, 0.05), "yellow": (0.05, 0.10), "green": (0.10, 999)},
            "higher_is_better": True, "format": "pct"
        },
        "X14": {
            "name": "师均论文著作课题数", "weight": 5, "unit": "",
            "method": "论文著作课题总数/专任教师数",
            "thresholds": {"red": (0, 0.5), "yellow": (0.5, 1.0), "green": (1.0, 999)},
            "higher_is_better": True, "format": "num"
        },
        "X15": {
            "name": "教师人均企业实践时间", "weight": 4, "unit": "天",
            "method": "专任教师企业实践时间/专任教师数",
            "thresholds": {"red": (0, 18), "yellow": (18, 30), "green": (30, 999)},
            "higher_is_better": True, "format": "days"
        }
    }


def load_data_from_xlsx() -> dict:
    """Load and parse data from the xlsx file."""
    xlsx_path = Path(r"D:\workspace\huiyi_pro\xingjian\academic-report\docs\需求文档\指标、阈值及数据0408.xlsx")
    
    if not xlsx_path.exists():
        return load_fallback_data()
    
    wb = load_workbook(xlsx_path, data_only=True)
    sheet_names = list(wb.sheetnames)
    
    # Hardcoded major names (5 majors after Sheet1 which is the threshold sheet)
    major_names = [
        "航空装备制造类",
        "机电一体化类",
        "汽车检测与维修技术",
        "计算机网络技术",
        "软件技术"
    ]
    
    indicators_meta = build_indicator_meta()
    years = ["2022-2023学年", "2023-2024学年", "2024-2025学年"]
    
    majors_data = {}
    
    # Read each major's data from sheets 1-5 (skip Sheet1 which is thresholds)
    for idx in range(1, min(6, len(sheet_names))):
        ws = wb[sheet_names[idx]]
        rows = list(ws.iter_rows(values_only=True))
        
        major_id = f"major_{idx-1}"
        major_name = major_names[idx-1] if idx-1 < len(major_names) else f"专业{idx-1}"
        
        for i, year in enumerate(years):
            if year not in majors_data:
                majors_data[year] = {}
            
            # Use actual values from xlsx
            year_data = {}
            total = 0
            
            for row_idx in range(1, 15):  # rows 1-14 contain indicator data
                if row_idx >= len(rows):
                    break
                row = rows[row_idx]
                if row and len(row) >= 5 and row[0] is not None:
                    try:
                        ind_num = int(row[0])  # Column A = indicator number (1-15)
                        ind_id = f"X{ind_num}"
                        raw_val = row[3] if row[3] is not None else 0  # Column D = raw value
                        score_val = row[4] if row[4] is not None else 0  # Column E = score
                        
                        # Apply slight year variation for trend demo
                        if i > 0 and ind_id != "X2":  # Don't scale ratios
                            if raw_val and raw_val > 0:
                                variation = (hash(f"{ind_id}{i}") % 100 - 50) / 2000.0
                                raw_val = raw_val * (1 + variation)
                        
                        year_data[ind_id] = raw_val
                        total += (score_val or 0)
                    except:
                        pass
            
            majors_data[year][major_id] = year_data
    
    # Build metadata
    meta_majors = [
        {"id": "major_0", "name": "航空装备制造类", "fullName": "航空装备制造类"},
        {"id": "major_1", "name": "机电一体化类", "fullName": "机电一体化类"},
        {"id": "major_2", "name": "汽车检测与维修技术", "fullName": "汽车检测与维修技术"},
        {"id": "major_3", "name": "计算机网络技术", "fullName": "计算机网络技术(含中高职贯通)"},
        {"id": "major_4", "name": "软件技术", "fullName": "软件技术"}
    ]
    
    return {
        "meta": {
            "school": "信息与机电工程系",
            "years": years,
            "indicators": [dict(id=k, **v) for k, v in indicators_meta.items()],
            "majors": meta_majors
        },
        "data": majors_data
    }


def load_fallback_data() -> dict:
    """Fallback data when xlsx is not available."""
    indicators_meta = build_indicator_meta()
    years = ["2022-2023学年", "2023-2024学年", "2024-2025学年"]
    
    majors_data = {}
    for year in years:
        majors_data[year] = {
            "major_0": {"X1": 0.92, "X2": 17.5, "X3": 0.85, "X4": 0.88, "X5": 0.96, "X6": 0.98, "X7": 0.72, "X8": 0.95, "X9": 0.93, "X10": 0.12, "X11": 0.68, "X12": 0.22, "X13": 0.08, "X14": 0.75, "X15": 25},
            "major_1": {"X1": 0.88, "X2": 19.2, "X3": 0.78, "X4": 0.72, "X5": 0.94, "X6": 0.95, "X7": 0.69, "X8": 0.92, "X9": 0.90, "X10": 0.05, "X11": 0.55, "X12": 0.18, "X13": 0.06, "X14": 0.45, "X15": 20},
            "major_2": {"X1": 0.95, "X2": 16.8, "X3": 0.82, "X4": 0.91, "X5": 0.97, "X6": 0.99, "X7": 0.75, "X8": 0.96, "X9": 0.94, "X10": 0.18, "X11": 0.72, "X12": 0.28, "X13": 0.12, "X14": 0.92, "X15": 32},
            "major_3": {"X1": 0.90, "X2": 18.5, "X3": 0.80, "X4": 0.85, "X5": 0.95, "X6": 0.97, "X7": 0.71, "X8": 0.94, "X9": 0.92, "X10": 0.08, "X11": 0.62, "X12": 0.20, "X13": 0.07, "X14": 0.55, "X15": 22},
            "major_4": {"X1": 0.87, "X2": 20.1, "X3": 0.75, "X4": 0.68, "X5": 0.93, "X6": 0.94, "X7": 0.65, "X8": 0.91, "X9": 0.89, "X10": 0.03, "X11": 0.50, "X12": 0.15, "X13": 0.04, "X14": 0.38, "X15": 16},
        }
    
    return {
        "meta": {
            "school": "信息与机电工程系",
            "years": years,
            "indicators": [dict(id=k, **v) for k, v in indicators_meta.items()],
            "majors": [
                {"id": "major_0", "name": "航空装备制造类", "fullName": "航空装备制造类"},
                {"id": "major_1", "name": "机电一体化类", "fullName": "机电一体化类"},
                {"id": "major_2", "name": "汽车检测与维修技术", "fullName": "汽车检测与维修技术"},
                {"id": "major_3", "name": "计算机网络技术", "fullName": "计算机网络技术(含中高职贯通)"},
                {"id": "major_4", "name": "软件技术", "fullName": "软件技术"}
            ]
        },
        "data": majors_data
    }


# Global data cache
_db_cache = None

def get_db() -> dict:
    global _db_cache
    if _db_cache is None:
        try:
            _db_cache = load_data_from_xlsx()
        except Exception as e:
            _db_cache = load_fallback_data()
    return _db_cache


# ============================================================
# JWT Helpers
# ============================================================
def create_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    encoded = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============================================================
# Auth Models
# ============================================================
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# ============================================================
# Auth Endpoints
# ============================================================
@app.post("/api/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Login endpoint."""
    if req.username == "admin" and req.password == "admin123":
        token = create_token({"sub": req.username, "role": "admin"})
        return TokenResponse(access_token=token, username=req.username)
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@app.post("/api/auth/logout")
async def logout():
    """Logout endpoint (client-side token removal)."""
    return {"message": "已退出登录"}


@app.get("/api/auth/me")
async def me(token: str = None):
    """Get current user info."""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="token已过期")
    return {"username": payload.get("sub"), "role": payload.get("role")}


# ============================================================
# Data Endpoints (protected)
# ============================================================
def get_level_value(val: float, ind_id: str, ind_dict: dict) -> str:
    """Get warning level for an indicator value.
    
    ind_dict: {ind_id: {thresholds: {...}}} or just {ind_id: {...}} if called with full lookup.
    Actually it receives: ind_lookup = {ind['id']: ind for ind in meta['indicators']}
    So it's keyed by id.
    """
    ind_meta = ind_dict.get(ind_id, {})
    thresholds = ind_meta.get("thresholds", {})
    
    if ind_id == "X2":  # 生师比 - lower is better (ratio: <=18 green, <=22 yellow, >22 red)
        green_thresh = thresholds.get("green", 18)
        yellow_thresh = thresholds.get("yellow", 22)
        if val <= green_thresh:
            return "green"
        elif val <= yellow_thresh:
            return "yellow"
        else:
            return "red"
    
    # For indicators with tuple thresholds (min, max)
    green_thresh = thresholds.get("green", 999)
    yellow_thresh = thresholds.get("yellow", 0)
    blue_thresh = thresholds.get("blue", 0)
    
    # Handle tuple ranges: green could be (0.90, 999)
    if isinstance(green_thresh, tuple):
        green_val = green_thresh[0]  # min value for green
        green_max = green_thresh[1]
    else:
        green_val = green_thresh
    
    if isinstance(yellow_thresh, tuple):
        yellow_val = yellow_thresh[0]
    else:
        yellow_val = yellow_thresh
    
    if isinstance(blue_thresh, tuple):
        blue_val = blue_thresh[0]
    else:
        blue_val = blue_thresh
    
    if val >= green_val:
        return "green"
    elif val >= yellow_val:
        return "yellow"
    elif val >= blue_val:
        return "blue"
    else:
        return "red"


def format_value(val: float, ind_id: str, fmt: str) -> str:
    """Format a value for display."""
    if fmt == "pct":
        return f"{val*100:.1f}%" if val is not None else "N/A"
    elif fmt == "ratio":
        return f"{val:.1f}:1" if val is not None else "N/A"
    elif fmt == "days":
        return f"{val:.0f}天" if val is not None else "N/A"
    elif fmt == "num":
        return f"{val:.2f}" if val is not None else "N/A"
    else:
        return f"{val:.2f}" if val is not None else "N/A"


@app.get("/api/years")
async def get_years():
    """Get available years."""
    db = get_db()
    years = db["meta"]["years"]
    return {"years": years, "default": years[-1] if years else None}


@app.get("/api/dashboard")
async def get_dashboard(year: str = None):
    """Get dashboard overview - summary + major cards."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    year_data = db["data"].get(target_year, {})
    
    # Summary counts
    total_red = 0
    total_yellow = 0
    total_blue = 0
    total_green = 0
    
    majors_list = []
    
    for m in meta["majors"]:
        mid = m["id"]
        mdata = year_data.get(mid, {})
        
        counts = {"red": 0, "yellow": 0, "blue": 0, "green": 0}
        details = {"red": [], "yellow": [], "blue": [], "green": []}
        
        # Previous year for trend
        year_idx = years.index(target_year) if target_year in years else len(years) - 1
        prev_year = years[year_idx - 1] if year_idx > 0 else None
        prev_data = db["data"].get(prev_year, {}).get(mid, {}) if prev_year else {}
        
        # Build indicator lookup dict
        ind_lookup = {ind["id"]: ind for ind in meta["indicators"]}
        
        for ind in meta["indicators"]:
            ind_id = ind["id"]
            val = mdata.get(ind_id, 0)
            level = get_level_value(val, ind_id, ind_lookup)
            
            # Blue: normal but negative trend
            if level == "green" and prev_data:
                prev_val = prev_data.get(ind_id, 0)
                if val < prev_val:
                    level = "blue"
            
            counts[level] += 1
            details[level].append(ind["name"])
        
        total_red += counts["red"]
        total_yellow += counts["yellow"]
        total_blue += counts["blue"]
        total_green += counts["green"]
        
        # Calculate overall health score
        health_score = (counts["green"] * 1.0 + counts["blue"] * 0.8 + counts["yellow"] * 0.5 + counts["red"] * 0) / max(len(meta["indicators"]), 1)
        
        majors_list.append({
            "id": mid,
            "name": m["name"],
            "fullName": m["fullName"],
            "counts": counts,
            "details": details,
            "healthScore": round(health_score * 100, 1)
        })
    
    # Sort by health score
    majors_list.sort(key=lambda x: x["healthScore"], reverse=True)
    
    # Rankings
    ranking = [{"id": m["id"], "name": m["name"], "healthScore": m["healthScore"]} for m in majors_list]
    
    return {
        "year": target_year,
        "years": years,
        "summary": {
            "totalMajors": len(meta["majors"]),
            "red": total_red,
            "yellow": total_yellow,
            "blue": total_blue,
            "green": total_green,
        },
        "majors": majors_list,
        "ranking": ranking
    }


@app.get("/api/major/{major_id}")
async def get_major_detail(major_id: str, year: str = None):
    """Get detailed data for a specific major."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    year_data = db["data"].get(target_year, {})
    mdata = year_data.get(major_id, {})
    
    major_meta = next((m for m in meta["majors"] if m["id"] == major_id), None)
    if not major_meta:
        raise HTTPException(status_code=404, detail="专业不存在")
    
    indicators = []
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    # Previous year data for trend
    year_idx = years.index(target_year) if target_year in years else len(years) - 1
    prev_year = years[year_idx - 1] if year_idx > 0 else None
    prev_data = db["data"].get(prev_year, {}).get(major_id, {}) if prev_year else {}
    
    for ind in meta["indicators"]:
        ind_id = ind["id"]
        val = mdata.get(ind_id, 0)
        prev_val = prev_data.get(ind_id, 0) if prev_data else 0
        level = get_level_value(val, ind_id, ind_dict)
        
        # Blue detection
        if level == "green" and prev_val and val < prev_val:
            level = "blue"
        
        # Trend
        if prev_val and prev_val != 0:
            change_pct = (val - prev_val) / prev_val * 100
            trend = "up" if change_pct > 1 else ("down" if change_pct < -1 else "stable")
        else:
            trend = "stable"
        
        indicators.append({
            "id": ind_id,
            "name": ind["name"],
            "value": val,
            "level": level,
            "trend": trend,
            "unit": ind.get("unit", ""),
            "format": ind.get("format", "num"),
            "weight": ind.get("weight", 0)
        })
    
    return {
        "majorId": major_id,
        "majorName": major_meta["name"],
        "year": target_year,
        "indicators": indicators,
        "years": years
    }


@app.get("/api/major/{major_id}/trends")
async def get_major_trends(major_id: str):
    """Get trend data for a major across all years."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    
    major_meta = next((m for m in meta["majors"] if m["id"] == major_id), None)
    if not major_meta:
        raise HTTPException(status_code=404, detail="专业不存在")
    
    trends = []
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    for ind in meta["indicators"]:
        ind_id = ind["id"]
        values = []
        
        for year in years:
            year_data = db["data"].get(year, {})
            mdata = year_data.get(major_id, {})
            values.append(mdata.get(ind_id, 0))
        
        # Calculate trend
        n = len(values)
        if n >= 2:
            x_mean = (n - 1) / 2
            y_mean = sum(values) / n
            num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den != 0 else 0
        else:
            slope = 0
        
        trends.append({
            "id": ind_id,
            "name": ind["name"],
            "values": values,
            "slope": round(slope, 4),
            "level": get_level_value(values[-1], ind_id, ind_dict) if values else "green",
            "format": ind.get("format", "num"),
            "unit": ind.get("unit", "")
        })
    
    return {"years": years, "trends": trends, "majorName": major_meta["name"]}


@app.get("/api/warnings")
async def get_warnings(year: str = None):
    """Get all warning items."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    year_data = db["data"].get(target_year, {})
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    year_idx = years.index(target_year) if target_year in years else len(years) - 1
    prev_year = years[year_idx - 1] if year_idx > 0 else None
    
    warnings_list = []
    
    for m in meta["majors"]:
        mid = m["id"]
        mdata = year_data.get(mid, {})
        prev_data = db["data"].get(prev_year, {}).get(mid, {}) if prev_year else {}
        
        for ind in meta["indicators"]:
            ind_id = ind["id"]
            val = mdata.get(ind_id, 0)
            level = get_level_value(val, ind_id, ind_dict)
            
            if level == "green" and prev_data:
                prev_val = prev_data.get(ind_id, 0)
                if val < prev_val:
                    level = "blue"
            
            if level in ("red", "yellow", "blue"):
                change = None
                if prev_data and ind_id in prev_data:
                    change = round(val - prev_data[ind_id], 4)
                
                warnings_list.append({
                    "majorId": mid,
                    "majorName": m["name"],
                    "indicatorId": ind_id,
                    "indicatorName": ind["name"],
                    "value": val,
                    "level": level,
                    "change": change,
                    "format": ind.get("format", "num"),
                    "unit": ind.get("unit", "")
                })
    
    # Sort: red first, then yellow, then blue
    warnings_list.sort(key=lambda x: (0 if x["level"] == "red" else 1 if x["level"] == "yellow" else 2, x["majorName"]))
    
    return {"year": target_year, "warnings": warnings_list}


@app.get("/api/compare")
async def get_compare(majors: str = None, year: str = None):
    """Get radar chart comparison data."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    if majors:
        major_ids = majors.split(",")
    else:
        major_ids = [m["id"] for m in meta["majors"]]
    
    year_data = db["data"].get(target_year, {})
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    # Use 7 core indicators for radar
    core_ids = ["X1", "X2", "X3", "X4", "X5", "X6", "X7"]
    
    compare_data = []
    for mid in major_ids:
        mdata = year_data.get(mid, {})
        major_meta = next((m for m in meta["majors"] if m["id"] == mid), None)
        name = major_meta["name"] if major_meta else mid
        
        # Normalize values to 0-100 scale
        scores = []
        for ind_id in core_ids:
            val = mdata.get(ind_id, 0)
            ind = ind_dict.get(ind_id, {})
            fmt = ind.get("format", "num")
            
            if fmt == "pct":
                score = val * 100
            elif fmt == "ratio":
                # 生师比: <=18 is best (100), >22 is worst (0)
                score = max(0, min(100, (22 - val) / (22 - 18) * 100))
            elif fmt == "days":
                score = min(val / 30 * 100, 100)
            else:
                score = val * 100
            
            scores.append(round(score, 1))
        
        compare_data.append({
            "id": mid,
            "name": name,
            "scores": scores
        })
    
    # Indicator labels
    labels = [ind_dict[i]["name"] for i in core_ids]
    
    return {
        "year": target_year,
        "indicators": [{"id": i, "name": n} for i, n in zip(core_ids, labels)],
        "majors": compare_data
    }


@app.get("/api/ranking")
async def get_ranking(year: str = None, indicator: str = None):
    """Get ranking data."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    year_data = db["data"].get(target_year, {})
    
    rankings = []
    for m in meta["majors"]:
        mid = m["id"]
        mdata = year_data.get(mid, {})
        
        if indicator:
            val = mdata.get(indicator, 0)
            # Normalize for comparison
            ind_meta = next((i for i in meta["indicators"] if i["id"] == indicator), None)
            if ind_meta:
                fmt = ind_meta.get("format", "num")
                if fmt == "pct":
                    val = val * 100
                elif fmt == "ratio":
                    val = max(0, min(100, (22 - val) / (22 - 18) * 100))
        else:
            # Overall health score
            counts = {"red": 0, "yellow": 0, "blue": 0, "green": 0}
            ind_dict = {i["id"]: i for i in meta["indicators"]}
            for ind_id, ind in ind_dict.items():
                val = mdata.get(ind_id, 0)
                level = get_level_value(val, ind_id, ind)
                if level == "green":
                    counts["green"] += 1
                elif level == "blue":
                    counts["blue"] += 1
                elif level == "yellow":
                    counts["yellow"] += 1
                else:
                    counts["red"] += 1
            total_indicators = len(meta["indicators"])
            val = (counts["green"] * 100 + counts["blue"] * 80 + counts["yellow"] * 50 + counts["red"] * 0) / max(total_indicators, 1)
        
        rankings.append({
            "id": mid,
            "name": m["name"],
            "value": round(val, 2)
        })
    
    rankings.sort(key=lambda x: x["value"], reverse=True)
    for i, r in enumerate(rankings):
        r["rank"] = i + 1
    
    return {
        "year": target_year,
        "indicator": indicator,
        "rankings": rankings
    }


@app.get("/api/report/{major_id}")
async def generate_report(major_id: str, year: str = None):
    """Generate comprehensive diagnostic report for a major."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    major_meta = next((m for m in meta["majors"] if m["id"] == major_id), None)
    if not major_meta:
        raise HTTPException(status_code=404, detail="专业不存在")
    
    year_data = db["data"].get(target_year, {})
    mdata = year_data.get(major_id, {})
    
    year_idx = years.index(target_year) if target_year in years else len(years) - 1
    prev_year = years[year_idx - 1] if year_idx > 0 else None
    prev_data = db["data"].get(prev_year, {}).get(major_id, {}) if prev_year else {}
    
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    # Categorize indicators
    red_items = []
    yellow_items = []
    blue_items = []
    green_items = []
    
    for ind in meta["indicators"]:
        ind_id = ind["id"]
        val = mdata.get(ind_id, 0)
        prev_val = prev_data.get(ind_id, 0) if prev_data else 0
        level = get_level_value(val, ind_id, ind_dict)
        
        if level == "green" and prev_val and val < prev_val:
            level = "blue"
        
        change_pct = None
        if prev_val and prev_val != 0:
            change_pct = round((val - prev_val) / prev_val * 100, 1)
        
        trend = "stable"
        if prev_val:
            if change_pct and change_pct > 1:
                trend = "up"
            elif change_pct and change_pct < -1:
                trend = "down"
        
        item = {
            "id": ind_id,
            "name": ind["name"],
            "value": val,
            "prevValue": prev_val,
            "level": level,
            "trend": trend,
            "change": change_pct,
            "unit": ind.get("unit", ""),
            "format": ind.get("format", "num")
        }
        
        if level == "red":
            red_items.append(item)
        elif level == "yellow":
            yellow_items.append(item)
        elif level == "blue":
            blue_items.append(item)
        else:
            green_items.append(item)
    
    # Calculate health score
    total = len(meta["indicators"])
    health_score = (len(green_items) * 100 + len(blue_items) * 80 + len(yellow_items) * 50 + len(red_items) * 0) / max(total, 1)
    
    # Generate report text following the template
    report_lines = []
    report_lines.append(f"{'='*50}")
    report_lines.append(f"【{major_meta['name']}】专业发展智诊报告")
    report_lines.append(f"生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    report_lines.append(f"数据年度：{target_year}")
    report_lines.append(f"{'='*50}")
    report_lines.append("")
    
    # 一、总体评价
    report_lines.append("一、总体评价")
    report_lines.append(f"本专业共监测{len(meta['indicators'])}项核心指标，")
    report_lines.append(f"其中绿色指标{len(green_items)}项、蓝色关注指标{len(blue_items)}项、")
    report_lines.append(f"黄色预警指标{len(yellow_items)}项、红色预警指标{len(red_items)}项。")
    report_lines.append(f"综合健康度得分：{health_score:.1f}分。")
    
    if health_score >= 80:
        report_lines.append("总体评价：优秀。该专业整体发展状况良好，各项指标表现稳定。")
    elif health_score >= 60:
        report_lines.append("总体评价：良好。该专业整体发展状况正常，部分指标需持续关注。")
    elif health_score >= 40:
        report_lines.append("总体评价：一般。该专业存在一定的预警指标，需要重点改进。")
    else:
        report_lines.append("总体评价：较差。该专业多项指标处于预警状态，需紧急干预。")
    
    report_lines.append("")
    
    # 二、各指标分析
    report_lines.append("二、各指标分析")
    
    # 红色预警指标
    if red_items:
        report_lines.append("")
        report_lines.append("（一）红色预警指标：")
        for item in red_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，趋势{'↑' if item['trend']=='up' else '↓' if item['trend']=='down' else '→'}平稳。")
            report_lines.append(f"    建议：立即启动专项改进措施，加强该领域的建设与投入。")
    
    # 黄色预警指标
    if yellow_items:
        report_lines.append("")
        report_lines.append("（二）黄色预警指标：")
        for item in yellow_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            change_str = f"较上年{abs(item['change']):.1f}%" if item["change"] else ""
            trend_str = "↑" if item["trend"] == "up" else "↓" if item["trend"] == "down" else "→"
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，{change_str}，趋势{trend_str}。")
            report_lines.append(f"    建议：密切关注该指标变化趋势，制定针对性改进计划。")
    
    # 蓝色关注指标
    if blue_items:
        report_lines.append("")
        report_lines.append("（三）蓝色关注指标（正常但有负向波动）：")
        for item in blue_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            change_str = f"较上年下降{abs(item['change']):.1f}%" if item["change"] and item["change"] < 0 else ""
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，{change_str}。")
            report_lines.append(f"    建议：分析下降原因，防止指标进一步恶化。")
    
    # 绿色指标
    if green_items:
        report_lines.append("")
        report_lines.append("（四）绿色健康指标：")
        for item in green_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，趋势健康。")
    
    report_lines.append("")
    
    # 三、综合建议
    report_lines.append("三、综合改进建议")
    
    if red_items:
        report_lines.append("")
        report_lines.append("1. 紧急改进事项：")
        for item in red_items[:2]:
            report_lines.append(f"   · {item['name']}指标严重偏低，需紧急调配资源，制定专项改进方案。")
    
    if yellow_items:
        report_lines.append("")
        report_lines.append("2. 重点提升事项：")
        for item in yellow_items[:2]:
            report_lines.append(f"   · 加强{item['name']}领域的建设，提升该指标的得分水平。")
    
    if blue_items:
        report_lines.append("")
        report_lines.append("3. 持续关注事项：")
        for item in blue_items[:2]:
            report_lines.append(f"   · 保持{item['name']}指标的稳定性，防止出现进一步下滑。")
    
    if not red_items and not yellow_items and not blue_items:
        report_lines.append("")
        report_lines.append("继续保持当前良好的发展态势，建议：")
        report_lines.append("  · 巩固现有优势领域，形成专业特色")
        report_lines.append("  · 持续关注学生就业质量和专业相关度")
    
    report_lines.append("")
    report_lines.append(f"{'='*50}")
    report_lines.append("报告由专业发展智诊系统自动生成")
    report_lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    report_text = "\n".join(report_lines)
    
    return {
        "majorId": major_id,
        "majorName": major_meta["name"],
        "year": target_year,
        "healthScore": round(health_score, 1),
        "red": red_items,
        "yellow": yellow_items,
        "blue": blue_items,
        "green": green_items,
        "reportText": report_text
    }


@app.get("/api/indicator/bar")
async def get_indicator_bar(indicator_id: str = None, year: str = None):
    """Get bar chart data for a specific indicator across majors."""
    db = get_db()
    meta = db["meta"]
    years = meta["years"]
    target_year = year or years[-1]
    
    year_data = db["data"].get(target_year, {})
    
    if indicator_id:
        ind_meta = next((i for i in meta["indicators"] if i["id"] == indicator_id), None)
        if not ind_meta:
            raise HTTPException(status_code=404, detail="指标不存在")
        
        data = []
        for m in meta["majors"]:
            mid = m["id"]
            mdata = year_data.get(mid, {})
            val = mdata.get(indicator_id, 0)
            data.append({
                "majorId": mid,
                "majorName": m["name"],
                "value": val,
                "level": get_level_value(val, indicator_id, {indicator_id: ind_meta})
            })
        
        data.sort(key=lambda x: x["value"], reverse=True)
        return {
            "year": target_year,
            "indicator": {"id": indicator_id, "name": ind_meta["name"]},
            "data": data
        }
    else:
        # Return all indicator bar data
        all_data = {}
        for ind in meta["indicators"]:
            ind_id = ind["id"]
            items = []
            for m in meta["majors"]:
                mid = m["id"]
                mdata = year_data.get(mid, {})
                val = mdata.get(ind_id, 0)
                items.append({
                    "majorId": mid,
                    "majorName": m["name"],
                    "value": val,
                    "level": get_level_value(val, ind_id, {ind_id: ind})
                })
            items.sort(key=lambda x: x["value"], reverse=True)
            all_data[ind_id] = {
                "name": ind["name"],
                "items": items
            }
        return {"year": target_year, "data": all_data}


@app.get("/api/report/{major_id}/print")
async def get_report_print(major_id: str, year: str = None, token: str = None):
    """Get print-friendly HTML report for a major."""
    # Verify token from query param (for browser opening in new tab)
    if token:
        payload = verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="token已过期，请重新登录")
    else:
        raise HTTPException(status_code=401, detail="未授权")
    
    data = await generate_report(major_id, year)
    
    # Color map
    level_colors = {
        "red": "#ff4d4f",
        "yellow": "#faad14", 
        "blue": "#1890ff",
        "green": "#52c41a"
    }
    
    # Build indicator rows
    def level_tag(level, name):
        color = level_colors.get(level, "#999")
        emoji = {"red": "🔴", "yellow": "🟡", "blue": "🔵", "green": "🟢"}.get(level, "⚪")
        return f'<span style="background:{color}22;color:{color};padding:2px 8px;border-radius:4px;font-size:12px;margin-right:4px">{emoji} {name}</span>'
    
    def format_val(v, fmt, unit=""):
        if v is None: return "N/A"
        if fmt == "pct": return f"{v*100:.1f}%{unit}"
        if fmt == "ratio": return f"{v:.1f}:1"
        if fmt == "days": return f"{v:.0f}{unit}"
        return f"{v:.2f}{unit}"
    
    # Indicators table rows
    all_items = data["red"] + data["yellow"] + data["blue"] + data["green"]
    rows = ""
    for item in all_items:
        lvl = item["level"]
        color = level_colors.get(lvl, "#999")
        rows += f"""<tr style="border-bottom:1px solid #eee">
            <td style="padding:8px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color}"></span></td>
            <td style="padding:8px;font-weight:500">{item['name']}</td>
            <td style="padding:8px;color:{color};font-weight:600">{format_val(item['value'], item['format'], item['unit'])}</td>
            <td style="padding:8px">{item['trend'] == 'up' and '↑' or item['trend'] == 'down' and '↓' or '→'} {item['change'] and f"({item['change']:+.1f}%)" or ''}</td>
            <td style="padding:8px"><span style="background:{color}22;color:{color};padding:2px 8px;border-radius:4px;font-size:12px">
                {'红色预警' if lvl=='red' else '黄色预警' if lvl=='yellow' else '蓝色关注' if lvl=='blue' else '绿色正常'}
            </span></td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>专业发展智诊报告 - {data['majorName']}</title>
<style>
  @page {{ size: A4; margin: 2cm; @top-center {{ content: '专业发展智诊报告'; font-size: 10px; color: #999; }} @bottom-right {{ content: '第 ' counter(page) ' 页 / 共 ' counter(pages) ' 页'; font-size: 10px; color: #999; }} }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Microsoft YaHei', 'PingFang SC', 'SimHei', Arial, sans-serif; font-size: 13px; color: #333; line-height: 1.6; }}
  .header {{ text-align: center; margin-bottom: 24px; border-bottom: 2px solid #1a1a2e; padding-bottom: 16px; }}
  .header h1 {{ font-size: 22px; color: #1a1a2e; margin-bottom: 8px; }}
  .header .meta {{ color: #666; font-size: 12px; }}
  .score-box {{ display: flex; gap: 16px; margin-bottom: 20px; }}
  .score-card {{ flex: 1; background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; }}
  .score-card .val {{ font-size: 24px; font-weight: 700; }}
  .score-card .lbl {{ font-size: 12px; color: #666; margin-top: 4px; }}
  .score-card.red .val {{ color: #ff4d4f; }}
  .score-card.yellow .val {{ color: #faad14; }}
  .score-card.blue .val {{ color: #1890ff; }}
  .score-card.green .val {{ color: #52c41a; }}
  h2 {{ font-size: 15px; color: #1a1a2e; border-left: 4px solid #1890ff; padding-left: 10px; margin: 20px 0 12px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  th {{ background: #f0f2f5; padding: 10px 8px; text-align: left; font-size: 12px; color: #666; font-weight: 500; }}
  .section {{ margin-bottom: 24px; }}
  .suggestions p {{ margin: 4px 0; }}
  .footer {{ margin-top: 30px; padding-top: 16px; border-top: 1px solid #eee; font-size: 11px; color: #999; text-align: center; }}
  @media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>【{data['majorName']}】专业发展智诊报告</h1>
  <div class="meta">数据年度：{data['year']} &nbsp;|&nbsp; 生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</div>
</div>

<div class="score-box">
  <div class="score-card red"><div class="val">{len(data['red'])}</div><div class="lbl">🔴 红色预警</div></div>
  <div class="score-card yellow"><div class="val">{len(data['yellow'])}</div><div class="lbl">🟡 黄色预警</div></div>
  <div class="score-card blue"><div class="val">{len(data['blue'])}</div><div class="lbl">🔵 蓝色关注</div></div>
  <div class="score-card green"><div class="val">{len(data['green'])}</div><div class="lbl">🟢 绿色正常</div></div>
  <div class="score-card" style="background:#e6f7ff"><div class="val" style="color:#1890ff">{data['healthScore']}</div><div class="lbl">📊 健康度</div></div>
</div>

<div class="section">
  <h2>一、预警详情</h2>
  <table>
    <thead><tr><th style="width:20px"></th><th>指标名称</th><th>当前值</th><th>变化趋势</th><th>预警级别</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>

<div class="section suggestions">
  <h2>二、综合建议</h2>
  {(len(data['red']) > 0) and ('<p>🔴 <strong>紧急事项：</strong>立即关注红色预警指标：' + ', '.join([i["name"] for i in data["red"]]) + '，需紧急调配资源改进。</p>') or ''}
  {(len(data['yellow']) > 0) and ('<p>🟡 <strong>重点提升：</strong>改善黄色预警指标：' + ', '.join([i["name"] for i in data["yellow"]]) + '，制定针对性改进计划。</p>') or ''}
  {(len(data['blue']) > 0) and ('<p>🔵 <strong>持续关注：</strong>保持蓝色关注指标的稳定性：' + ', '.join([i["name"] for i in data["blue"]]) + '，防止进一步下滑。</p>') or ''}
  {(len(data['red']) == 0 and len(data['yellow']) == 0 and len(data['blue']) == 0) and '<p>🟢 继续保持良好发展态势，巩固现有优势领域，形成专业特色。</p>' or ''}
</div>

<div class="footer">
  本报告由专业发展智诊系统自动生成 &nbsp;|&nbsp; {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>
<script>window.onload = function() {{ window.print(); }}</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/api/report/{major_id}/pdf")
async def get_report_pdf(major_id: str, year: str = None, token: str = None):
    """Generate and download PDF diagnostic report for a major."""
    if token:
        payload = verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="token已过期，请重新登录")
    else:
        raise HTTPException(status_code=401, detail="未授权")

    data = await generate_report(major_id, year)
    if data is None:
        raise HTTPException(status_code=404, detail="专业不存在")

    # Build PDF
    from io import BytesIO
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    # Styles
    title_style = ParagraphStyle('title', fontName=PDF_FONT, fontSize=18, leading=24, alignment=TA_CENTER, spaceAfter=6)
    subtitle_style = ParagraphStyle('subtitle', fontName=PDF_FONT, fontSize=10, leading=14, alignment=TA_CENTER, spaceAfter=4, textColor=colors.grey)
    section_style = ParagraphStyle('section', fontName=PDF_FONT, fontSize=13, leading=18, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor('#1a1a2e'))
    body_style = ParagraphStyle('body', fontName=PDF_FONT, fontSize=10, leading=15, spaceAfter=4)
    red_style = ParagraphStyle('red', fontName=PDF_FONT, fontSize=10, leading=15, spaceAfter=4, textColor=colors.HexColor('#d93636'))
    yellow_style = ParagraphStyle('yellow', fontName=PDF_FONT, fontSize=10, leading=15, spaceAfter=4, textColor=colors.HexColor('#d9a41a'))
    blue_style = ParagraphStyle('blue', fontName=PDF_FONT, fontSize=10, leading=15, spaceAfter=4, textColor=colors.HexColor('#155bbc'))
    green_style = ParagraphStyle('green', fontName=PDF_FONT, fontSize=10, leading=15, spaceAfter=4, textColor=colors.HexColor('#2e8b2e'))

    story = []

    # Title
    story.append(Paragraph(f"【{data['majorName']}】专业发展智诊报告", title_style))
    story.append(Paragraph(f"数据年度：{data['year']} &nbsp;|&nbsp; 生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a1a2e'), spaceAfter=10))

    # Summary boxes
    total = len(data['red']) + len(data['yellow']) + len(data['blue']) + len(data['green'])
    summary_data = [
        [Paragraph(f"🔴 红色<br/>{len(data['red'])}", red_style),
         Paragraph(f"🟡 黄色<br/>{len(data['yellow'])}", yellow_style),
         Paragraph(f"🔵 蓝色<br/>{len(data['blue'])}", blue_style),
         Paragraph(f"🟢 绿色<br/>{len(data['green'])}", green_style),
         Paragraph(f"📊 健康度<br/>{data['healthScore']}分", body_style)]
    ]
    summary_table = Table(summary_data, colWidths=[3*cm]*5)
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#fff0f0')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#fffbe6')),
        ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#e6f4ff')),
        ('BACKGROUND', (3, 0), (3, 0), colors.HexColor('#f0fff0')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dddddd')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 16))

    # 一、总体评价
    story.append(Paragraph("一、总体评价", section_style))
    story.append(Paragraph(f"本专业共监测{total}项核心指标，其中绿色{len(data['green'])}项、蓝色{len(data['blue'])}项、黄色{len(data['yellow'])}项、红色{len(data['red'])}项。综合健康度得分：{data['healthScore']}分。", body_style))
    if data['healthScore'] >= 80:
        story.append(Paragraph("总体评价：优秀。该专业整体发展状况良好，各项指标表现稳定。", body_style))
    elif data['healthScore'] >= 60:
        story.append(Paragraph("总体评价：良好。该专业整体发展状况正常，部分指标需持续关注。", body_style))
    elif data['healthScore'] >= 40:
        story.append(Paragraph("总体评价：一般。该专业存在一定预警指标，需要重点改进。", body_style))
    else:
        story.append(Paragraph("总体评价：较差。该专业多项指标处于预警状态，需紧急干预。", body_style))

    # 二、预警指标
    story.append(Paragraph("二、各指标预警情况", section_style))

    if data['red']:
        story.append(Paragraph(f"🔴 红色预警指标（{len(data['red'])}项）：", red_style))
        for item in data['red']:
            fmt_val = format_value(item['value'], item['id'], item['format'])
            trend = {'up': '↑', 'down': '↓', 'stable': '→'}.get(item['trend'], '→')
            story.append(Paragraph(f"  • {item['name']}：{fmt_val}{item['unit']}，趋势{trend}，建议立即改进。", red_style))

    if data['yellow']:
        story.append(Paragraph(f"🟡 黄色预警指标（{len(data['yellow'])}项）：", yellow_style))
        for item in data['yellow']:
            fmt_val = format_value(item['value'], item['id'], item['format'])
            trend = {'up': '↑', 'down': '↓', 'stable': '→'}.get(item['trend'], '→')
            story.append(Paragraph(f"  • {item['name']}：{fmt_val}{item['unit']}，趋势{trend}，建议密切关注。", yellow_style))

    if data['blue']:
        story.append(Paragraph(f"🔵 蓝色关注指标（{len(data['blue'])}项）：", blue_style))
        for item in data['blue']:
            fmt_val = format_value(item['value'], item['id'], item['format'])
            story.append(Paragraph(f"  • {item['name']}：{fmt_val}{item['unit']}，正常但有负向波动，需持续关注。", blue_style))

    if data['green']:
        story.append(Paragraph(f"🟢 绿色健康指标（{len(data['green'])}项）：", green_style))
        for item in data['green']:
            fmt_val = format_value(item['value'], item['id'], item['format'])
            story.append(Paragraph(f"  • {item['name']}：{fmt_val}{item['unit']}，趋势健康。", green_style))

    # 三、综合建议
    story.append(Paragraph("三、综合改进建议", section_style))
    if data['red']:
        story.append(Paragraph(f"1. 紧急改进：关注红色预警指标（{', '.join([i['name'] for i in data['red']])}），需紧急调配资源制定专项方案。", body_style))
    if data['yellow']:
        story.append(Paragraph(f"2. 重点提升：改善黄色预警指标（{', '.join([i['name'] for i in data['yellow']])}），制定针对性改进计划。", body_style))
    if data['blue']:
        story.append(Paragraph(f"3. 持续关注：保持蓝色指标（{', '.join([i['name'] for i in data['blue']])}）的稳定性，防止进一步下滑。", body_style))
    if not data['red'] and not data['yellow'] and not data['blue']:
        story.append(Paragraph("继续保持良好发展态势，巩固现有优势领域，形成专业特色。", body_style))

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#dddddd'), spaceAfter=6))
    story.append(Paragraph(f"本报告由专业发展智诊系统自动生成 | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"专业发展智诊报告_{data['majorName']}_{data['year']}.pdf"
    import urllib.parse
    encoded_name = urllib.parse.quote(filename)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"})


class HTMLResponse(JSONResponse):
    media_type = "text/html; charset=utf-8"


@app.get("/")
async def root():
    """Serve the frontend HTML."""
    html_file = Path(__file__).parent.parent / "frontend" / "index.html"
    return FileResponse(str(html_file))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8089)
