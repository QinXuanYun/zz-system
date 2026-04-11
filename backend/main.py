"""
专业发展智诊系统 - FastAPI Backend (v3)
With Database support, JWT authentication
"""
import json
import os
import math
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form
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

# Import database
from database import (
    get_db, get_years, get_year_data, import_excel_data,
    IndicatorMeta, SessionLocal, init_db
)

# Register Chinese font for PDF - Support Windows, Linux, macOS
def register_chinese_font():
    """Try to register a Chinese font for PDF generation."""
    font_paths = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_name = os.path.basename(font_path).split('.')[0]
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                return font_name
            except Exception:
                continue
    return 'Helvetica'

PDF_FONT = register_chinese_font()

# JWT Config
SECRET_KEY = "zyzd-secret-key-2024专业发展智诊系统"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# FastAPI App
app = FastAPI(title="专业发展智诊系统", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Excel storage path
EXCEL_DIR = Path(__file__).parent.parent / "excel"
EXCEL_DIR.mkdir(exist_ok=True)

# ============================================================
# Helpers
# ============================================================
def parse_year_from_filename(filename: str) -> Optional[str]:
    """Parse year from filename like '指标、阈值及数据-2020年.xlsx'"""
    # Remove file extension
    name = filename.rsplit('.', 1)[0] if '.' in filename else filename
    
    # Match patterns like: 2020-2021学年, 2020-2021, 2020年, 2020
    patterns = [
        r'(\d{4})\s*[-~]\s*(\d{4})\s*学年?',  # 2020-2021学年 or 2020-2021
        r'(\d{4})\s*学年?',                    # 2020学年 or 2020年 or 2020
    ]
    
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            year1 = match.group(1)
            year2 = match.group(2) if len(match.groups()) > 1 and match.group(2) else str(int(year1) + 1)
            return f"{year1}-{year2}学年"
    
    return None

def get_indicator_meta_db() -> Dict[str, Dict]:
    """Get indicator metadata from database"""
    db = SessionLocal()
    try:
        meta = {}
        for ind in db.query(IndicatorMeta).all():
            meta[ind.indicator_id] = {
                "name": ind.name,
                "weight": ind.weight,
                "unit": ind.unit,
                "method": ind.method,
                "thresholds": {
                    "red": ind.red_threshold,
                    "yellow": ind.yellow_threshold,
                    "green": ind.green_threshold
                },
                "higher_is_better": bool(ind.higher_is_better),
                "format": ind.format
            }
        return meta
    finally:
        db.close()

def get_level_value(val: float, ind_id: str, ind_meta: Dict) -> str:
    """Get warning level for an indicator value."""
    thresholds = ind_meta.get("thresholds", {})
    
    if ind_id == "X2":  # 生师比 - lower is better
        green_thresh = thresholds.get("green", 18)
        yellow_thresh = thresholds.get("yellow", 22)
        if val <= green_thresh:
            return "green"
        elif val <= yellow_thresh:
            return "yellow"
        else:
            return "red"
    
    # For indicators where higher is better
    red_thresh = thresholds.get("red", 0)
    yellow_thresh = thresholds.get("yellow", 0)
    green_thresh = thresholds.get("green", 100)
    
    if val >= green_thresh:
        return "green"
    elif val >= yellow_thresh:
        return "yellow"
    else:
        return "red"

def format_value(val: float, ind_id: str, fmt: str) -> str:
    """Format a value for display."""
    if fmt == "pct":
        return f"{val*100:.1f}%"
    elif fmt == "ratio":
        return f"{val:.1f}"
    elif fmt == "days":
        return f"{val:.0f}天"
    elif fmt == "num":
        return f"{val:.2f}"
    else:
        return f"{val:.2f}"

# ============================================================
# JWT Helpers
# ============================================================
def create_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
    if req.username == "admin" and req.password == "admin123":
        token = create_token({"sub": req.username, "role": "admin"})
        return TokenResponse(access_token=token, username=req.username)
    raise HTTPException(status_code=401, detail="用户名或密码错误")

@app.post("/api/auth/logout")
async def logout():
    return {"message": "已退出登录"}

@app.get("/api/auth/me")
async def me(token: str = None):
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="token已过期")
    return {"username": payload.get("sub"), "role": payload.get("role")}

# ============================================================
# Import Endpoint
# ============================================================
@app.post("/api/import")
async def import_excel(
    file: UploadFile = File(...),
    year: str = Form(None)
):
    """Upload and import Excel file"""
    import traceback
    
    try:
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="只支持 Excel 文件")
        
        # Parse year from filename if not provided
        if not year:
            year = parse_year_from_filename(file.filename)
        
        if not year:
            raise HTTPException(status_code=400, detail="无法从文件名解析年份，请手动指定")
        
        # Ensure excel directory exists
        EXCEL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = EXCEL_DIR / f"{year}_{file.filename}"
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        # Parse Excel
        wb = load_workbook(file_path, data_only=True)
        sheet_names = list(wb.sheetnames)
        
        if len(sheet_names) < 2:
            raise HTTPException(status_code=400, detail="Excel文件至少需要2个工作表（第一个是阈值表，后面是专业数据）")
        
        # Skip first sheet (thresholds), process remaining as major data
        majors_data = []
        
        for idx in range(1, min(16, len(sheet_names))):
            ws = wb[sheet_names[idx]]
            rows = list(ws.iter_rows(values_only=True))
            
            major_name = sheet_names[idx]
            indicators = {}
            
            # Read rows 1-15 for indicators
            for row_idx in range(1, min(16, len(rows))):
                row = rows[row_idx]
                if row and len(row) >= 5 and row[0] is not None:
                    try:
                        ind_num = int(row[0])
                        if ind_num > 15:
                            continue
                        ind_id = f"X{ind_num}"
                        raw_val = row[3] if row[3] is not None else 0
                        # Handle empty or non-numeric values
                        if raw_val is None or raw_val == '':
                            raw_val = 0
                        indicators[ind_id] = float(raw_val)
                    except Exception:
                        pass
            
            majors_data.append({
                "name": major_name,
                "indicators": indicators
            })
        
        if not majors_data:
            raise HTTPException(status_code=400, detail="未找到有效的专业数据")
        
        # Import to database
        success = import_excel_data(year, majors_data)
        
        if success:
            return {"success": True, "message": f"成功导入 {year} 数据，共 {len(majors_data)} 个专业"}
        else:
            raise HTTPException(status_code=500, detail="数据导入失败，请检查数据库连接")
            
    except HTTPException:
        raise
    except Exception as e:
        error_detail = f"导入错误: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")

@app.get("/api/years")
async def get_available_years():
    """Get all available years"""
    years = get_years()
    return {"years": years, "default": years[-1] if years else None}

# ============================================================
# Dashboard Endpoints
# ============================================================
@app.get("/api/dashboard")
async def get_dashboard(year: str = None):
    """Get dashboard overview"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据，请先导入")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    # Calculate summary
    total_red = total_yellow = total_blue = total_green = 0
    majors_list = []
    
    for m in meta["majors"]:
        mid = m["id"]
        mdata = year_data.get(mid, {})
        
        counts = {"red": 0, "yellow": 0, "blue": 0, "green": 0}
        details = {"red": [], "yellow": [], "blue": [], "green": []}
        
        for ind in meta["indicators"]:
            ind_id = ind["id"]
            val = mdata.get(ind_id, 0)
            level = get_level_value(val, ind_id, ind)
            counts[level] += 1
            details[level].append(ind["name"])
        
        total_red += counts["red"]
        total_yellow += counts["yellow"]
        total_blue += counts["blue"]
        total_green += counts["green"]
        
        health_score = (counts["green"] * 1.0 + counts["blue"] * 0.8 + 
                       counts["yellow"] * 0.5 + counts["red"] * 0) / max(len(meta["indicators"]), 1)
        
        majors_list.append({
            "id": mid,
            "name": m["name"],
            "fullName": m["fullName"],
            "counts": counts,
            "details": details,
            "healthScore": round(health_score * 100, 1)
        })
    
    majors_list.sort(key=lambda x: x["healthScore"], reverse=True)
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
    """Get detailed data for a specific major"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    mdata = year_data.get(major_id, {})
    
    major_meta = next((m for m in meta["majors"] if m["id"] == major_id), None)
    if not major_meta:
        raise HTTPException(status_code=404, detail="专业不存在")
    
    indicators = []
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    for ind in meta["indicators"]:
        ind_id = ind["id"]
        val = mdata.get(ind_id, 0)
        level = get_level_value(val, ind_id, ind_dict)
        
        indicators.append({
            "id": ind_id,
            "name": ind["name"],
            "value": val,
            "level": level,
            "trend": "stable",
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

@app.get("/api/compare")
async def get_compare(majors: str = None, year: str = None):
    """Get radar chart comparison data"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    if majors:
        major_ids = majors.split(",")
    else:
        major_ids = [m["id"] for m in meta["majors"]]
    
    core_ids = [f"X{i}" for i in range(1, 16)]
    
    compare_data = []
    for mid in major_ids:
        mdata = year_data.get(mid, {})
        major_meta = next((m for m in meta["majors"] if m["id"] == mid), None)
        name = major_meta["name"] if major_meta else mid
        
        scores = []
        for ind_id in core_ids:
            val = mdata.get(ind_id, 0)
            ind = ind_dict.get(ind_id, {})
            fmt = ind.get("format", "num")
            
            if fmt == "pct":
                score = val * 100
            elif fmt == "ratio":
                score = max(0, min(100, (22 - val) / (22 - 18) * 100))
            elif fmt == "days":
                score = min(val / 30 * 100, 100)
            else:
                score = val * 100
            
            scores.append(round(score, 1))
        
        compare_data.append({"id": mid, "name": name, "scores": scores})
    
    labels = [ind_dict[i]["name"] for i in core_ids if i in ind_dict]
    
    return {
        "year": target_year,
        "indicators": [{"id": i, "name": n} for i, n in zip(core_ids, labels)],
        "majors": compare_data
    }

@app.get("/api/ranking")
async def get_ranking(year: str = None, indicator: str = None):
    """Get ranking data"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    
    def normalize_value(val, ind_format):
        if ind_format == "pct":
            return val * 100
        elif ind_format == "ratio":
            return val
        elif ind_format == "days":
            return val
        else:
            return val * 100
    
    rankings = []
    for m in meta["majors"]:
        mid = m["id"]
        mdata = year_data.get(mid, {})
        
        if indicator:
            val = mdata.get(indicator, 0)
            ind_meta = next((i for i in meta["indicators"] if i["id"] == indicator), None)
            if ind_meta:
                ind_format = ind_meta.get("format", "pct")
                val = normalize_value(val, ind_format)
        else:
            counts = {"red": 0, "yellow": 0, "blue": 0, "green": 0}
            ind_dict = {i["id"]: i for i in meta["indicators"]}
            for ind_id, ind in ind_dict.items():
                val = mdata.get(ind_id, 0)
                level = get_level_value(val, ind_id, ind)
                counts[level] += 1
            total_indicators = len(meta["indicators"])
            val = (counts["green"] * 100 + counts["blue"] * 80 + 
                   counts["yellow"] * 50 + counts["red"] * 0) / max(total_indicators, 1)
        
        rankings.append({"id": mid, "name": m["name"], "value": round(val, 2)})
    
    higher_is_better = True
    if indicator:
        ind_meta = next((i for i in meta["indicators"] if i["id"] == indicator), None)
        higher_is_better = ind_meta.get("higher_is_better", True) if ind_meta else True
    
    rankings.sort(key=lambda x: x["value"], reverse=higher_is_better)
    for i, r in enumerate(rankings):
        r["rank"] = i + 1
    
    return {"year": target_year, "indicator": indicator, "rankings": rankings}

@app.get("/api/indicator/bar")
async def get_indicator_bar(indicator_id: str = None, year: str = None):
    """Get bar chart data for a specific indicator"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    
    def normalize_value(val, ind_format):
        if ind_format == "pct":
            return val * 100
        elif ind_format == "ratio":
            return val
        elif ind_format == "days":
            return val
        else:
            return val * 100
    
    if indicator_id:
        ind_meta = next((i for i in meta["indicators"] if i["id"] == indicator_id), None)
        if not ind_meta:
            raise HTTPException(status_code=404, detail="指标不存在")
        
        ind_format = ind_meta.get("format", "pct")
        data = []
        for m in meta["majors"]:
            mid = m["id"]
            mdata = year_data.get(mid, {})
            val = mdata.get(indicator_id, 0)
            normalized_val = normalize_value(val, ind_format)
            data.append({
                "majorId": mid,
                "majorName": m["name"],
                "value": normalized_val,
                "rawValue": val,
                "level": get_level_value(val, indicator_id, {indicator_id: ind_meta}),
                "format": ind_format
            })
        
        reverse_sort = ind_meta.get("higher_is_better", True)
        data.sort(key=lambda x: x["value"], reverse=reverse_sort)
        return {
            "year": target_year,
            "indicator": {"id": indicator_id, "name": ind_meta["name"], "format": ind_format},
            "data": data
        }
    else:
        all_data = {}
        for ind in meta["indicators"]:
            ind_id = ind["id"]
            ind_format = ind.get("format", "pct")
            items = []
            for m in meta["majors"]:
                mid = m["id"]
                mdata = year_data.get(mid, {})
                val = mdata.get(ind_id, 0)
                normalized_val = normalize_value(val, ind_format)
                items.append({
                    "majorId": mid,
                    "majorName": m["name"],
                    "value": normalized_val,
                    "rawValue": val,
                    "level": get_level_value(val, ind_id, {ind_id: ind}),
                    "format": ind_format
                })
            items.sort(key=lambda x: x["value"], reverse=True)
            all_data[ind_id] = {"name": ind["name"], "format": ind_format, "items": items}
        return {"year": target_year, "data": all_data}

# ============================================================
# Trends Endpoint
# ============================================================
@app.get("/api/major/{major_id}/trends")
async def get_major_trends(major_id: str):
    """Get trend data for a major across all years"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    # Get all year data
    all_years_data = {}
    for year in years:
        db_data = get_year_data(year)
        if db_data and year in db_data["data"]:
            all_years_data[year] = db_data["data"][year]
    
    if not all_years_data:
        raise HTTPException(status_code=404, detail="无趋势数据")
    
    # Get metadata from most recent year
    latest_year = years[-1]
    db_data = get_year_data(latest_year)
    meta = db_data["meta"]
    
    major_meta = next((m for m in meta["majors"] if m["id"] == major_id), None)
    if not major_meta:
        raise HTTPException(status_code=404, detail="专业不存在")
    
    trends = []
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    for ind in meta["indicators"]:
        ind_id = ind["id"]
        values = []
        
        for year in years:
            year_data = all_years_data.get(year, {})
            mdata = year_data.get(major_id, {})
            values.append(mdata.get(ind_id, 0))
        
        # Calculate trend slope
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

# ============================================================
# Warnings Endpoint
# ============================================================
@app.get("/api/warnings")
async def get_warnings(year: str = None):
    """Get all warning items"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    warnings_list = []
    
    for m in meta["majors"]:
        mid = m["id"]
        mdata = year_data.get(mid, {})
        
        for ind in meta["indicators"]:
            ind_id = ind["id"]
            val = mdata.get(ind_id, 0)
            level = get_level_value(val, ind_id, ind_dict)
            
            if level in ("red", "yellow", "blue"):
                warnings_list.append({
                    "majorId": mid,
                    "majorName": m["name"],
                    "indicatorId": ind_id,
                    "indicatorName": ind["name"],
                    "value": val,
                    "level": level,
                    "change": None,
                    "format": ind.get("format", "num"),
                    "unit": ind.get("unit", "")
                })
    
    # Sort: red first, then yellow, then blue
    warnings_list.sort(key=lambda x: (0 if x["level"] == "red" else 1 if x["level"] == "yellow" else 2, x["majorName"]))
    
    return {"year": target_year, "warnings": warnings_list}

# ============================================================
# Report Endpoints
# ============================================================
@app.get("/api/report/{major_id}")
async def generate_report(major_id: str, year: str = None):
    """Generate comprehensive diagnostic report for a major"""
    years = get_years()
    if not years:
        raise HTTPException(status_code=404, detail="暂无数据")
    
    target_year = year or years[-1]
    db_data = get_year_data(target_year)
    
    if not db_data:
        raise HTTPException(status_code=404, detail="年份不存在")
    
    meta = db_data["meta"]
    year_data = db_data["data"].get(target_year, {})
    mdata = year_data.get(major_id, {})
    
    major_meta = next((m for m in meta["majors"] if m["id"] == major_id), None)
    if not major_meta:
        raise HTTPException(status_code=404, detail="专业不存在")
    
    ind_dict = {ind["id"]: ind for ind in meta["indicators"]}
    
    # Categorize indicators
    red_items = []
    yellow_items = []
    blue_items = []
    green_items = []
    
    for ind in meta["indicators"]:
        ind_id = ind["id"]
        val = mdata.get(ind_id, 0)
        level = get_level_value(val, ind_id, ind_dict)
        
        item = {
            "id": ind_id,
            "name": ind["name"],
            "value": val,
            "level": level,
            "trend": "stable",
            "change": None,
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
    health_score = (len(green_items) * 100 + len(blue_items) * 80 + 
                   len(yellow_items) * 50 + len(red_items) * 0) / max(total, 1)
    
    # Generate report text
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
    
    if red_items:
        report_lines.append("")
        report_lines.append("（一）红色预警指标：")
        for item in red_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，建议立即改进。")
    
    if yellow_items:
        report_lines.append("")
        report_lines.append("（二）黄色预警指标：")
        for item in yellow_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，建议密切关注。")
    
    if blue_items:
        report_lines.append("")
        report_lines.append("（三）蓝色关注指标：")
        for item in blue_items:
            val_str = format_value(item["value"], item["id"], item["format"])
            report_lines.append(f"  {item['name']}：{val_str}{item['unit']}，需持续关注。")
    
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
            report_lines.append(f"   · {item['name']}指标严重偏低，需紧急调配资源。")
    
    if yellow_items:
        report_lines.append("")
        report_lines.append("2. 重点提升事项：")
        for item in yellow_items[:2]:
            report_lines.append(f"   · 加强{item['name']}领域的建设。")
    
    if blue_items:
        report_lines.append("")
        report_lines.append("3. 持续关注事项：")
        for item in blue_items[:2]:
            report_lines.append(f"   · 保持{item['name']}指标的稳定性。")
    
    if not red_items and not yellow_items and not blue_items:
        report_lines.append("")
        report_lines.append("继续保持当前良好的发展态势。")
    
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

# ============================================================
# Static Files
# ============================================================
@app.get("/")
async def root():
    html_file = Path(__file__).parent.parent / "frontend" / "index.html"
    return FileResponse(str(html_file))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8089)
