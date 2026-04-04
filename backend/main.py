"""
专业发展智诊系统 - FastAPI Backend
"""
import json
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="专业发展智诊系统", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data path
DATA_FILE = Path(__file__).parent.parent / "data" / "indicators.json"


def load_data():
    """Load indicators data from JSON file."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_warning_level(indicator_name: str, value: float) -> str:
    """Determine warning level based on indicator thresholds."""
    data = load_data()
    thresholds = data.get("thresholds", {})
    
    if indicator_name not in thresholds:
        return "green"
    
    threshold = thresholds[indicator_name]
    is_inverse = threshold.get("inverse", False)
    green = threshold["green"]
    yellow = threshold["yellow"]
    
    if is_inverse:
        # Lower is better (e.g., 生师比)
        if value <= green:
            return "green"
        elif value <= yellow:
            return "yellow"
        else:
            return "red"
    else:
        # Higher is better
        if value >= green:
            return "green"
        elif value >= yellow:
            return "yellow"
        else:
            return "red"


def generate_report(major_data: dict) -> dict:
    """Generate analysis report for a major."""
    indicators = major_data["indicators"]
    
    # Categorize indicators by warning level
    green_indicators = []
    blue_indicators = []
    yellow_indicators = []
    red_indicators = []
    
    for ind in indicators:
        # Calculate percentage for threshold check
        if ind["weight"] > 0:
            percentage = (ind["score"] / ind["weight"]) * 100
            level = get_warning_level(ind["name"], percentage)
        else:
            level = "green"
        
        if level == "green":
            green_indicators.append(ind)
        elif level == "yellow":
            yellow_indicators.append(ind)
        elif level == "red":
            red_indicators.append(ind)
    
    # Find strengths and weaknesses
    # Sort by score/weight ratio
    sorted_indicators = sorted(indicators, 
                               key=lambda x: x["score"]/x["weight"] if x["weight"] > 0 else 0)
    
    strengths = sorted_indicators[-3:]  # Top 3
    weaknesses = sorted_indicators[:3]  # Bottom 3
    
    # Generate text
    report_text = f"""【{major_data['name']}】专业发展分析报告

■ 总体得分: {major_data['totalScore']:.2f} 分 (得分率: {major_data['scoreRate']*100:.1f}%)

■ 预警概况:
- 绿色指标 (正常): {len(green_indicators)} 个
- 黄色预警: {len(yellow_indicators)} 个
- 红色预警: {len(red_indicators)} 个

■ 优势领域 (表现较好的指标):
{chr(10).join([f"  ✓ {s['name']}: {s['score']}/{s['weight']}分" for s in strengths])}

■ 需改进领域 (得分偏低的指标):
{chr(10).join([f"  ✗ {w['name']}: {w['score']}/{w['weight']}分" for w in weaknesses])}

■ 建议:
{"1. 继续保持现有优势领域的发展势头。" if len(green_indicators) >= 5 else "1. 加强优势领域，同时重点改进黄色预警指标。"}
{f"2. 重点关注: {', '.join([w['name'] for w in weaknesses[:2]])} 等薄弱环节。" if weaknesses else ""}
{"3. 建议加强校企合作，提升企业订单学生占比。" if any(ind['id'] == 'X6' and ind['score'] == 0 for ind in indicators) else ""}
"""
    
    return {
        "major": major_data["name"],
        "totalScore": major_data["totalScore"],
        "scoreRate": major_data["scoreRate"],
        "warnings": {
            "green": len(green_indicators),
            "yellow": len(yellow_indicators),
            "red": len(red_indicators)
        },
        "greenIndicators": [{"name": i["name"], "score": i["score"], "weight": i["weight"]} for i in green_indicators],
        "yellowIndicators": [{"name": i["name"], "score": i["score"], "weight": i["weight"], "percentage": round(i["score"]/i["weight"]*100, 1) if i["weight"] > 0 else 0} for i in yellow_indicators],
        "redIndicators": [{"name": i["name"], "score": i["score"], "weight": i["weight"], "percentage": round(i["score"]/i["weight"]*100, 1) if i["weight"] > 0 else 0} for i in red_indicators],
        "strengths": [{"name": s["name"], "score": s["score"], "weight": s["weight"]} for s in strengths],
        "weaknesses": [{"name": w["name"], "score": w["score"], "weight": w["weight"]} for w in weaknesses],
        "reportText": report_text
    }


@app.get("/")
async def root():
    """Serve the frontend HTML."""
    html_file = Path(__file__).parent.parent / "frontend" / "index.html"
    return FileResponse(str(html_file))


@app.get("/api/majors")
async def get_majors():
    """Get list of all majors with summary data."""
    data = load_data()
    majors = []
    for m in data["majors"]:
        majors.append({
            "id": m["id"],
            "name": m["name"],
            "totalScore": m["totalScore"],
            "scoreRate": m["scoreRate"]
        })
    return {"majors": majors, "summary": data.get("summary", {})}


@app.get("/api/indicators/{major_id}")
async def get_indicators(major_id: str):
    """Get detailed indicators for a specific major."""
    data = load_data()
    for m in data["majors"]:
        if m["id"] == major_id:
            # Add warning levels to indicators
            indicators_with_level = []
            for ind in m["indicators"]:
                if ind["weight"] > 0:
                    percentage = (ind["score"] / ind["weight"]) * 100
                    level = get_warning_level(ind["name"], percentage)
                else:
                    level = "green"
                    percentage = 0
                
                indicators_with_level.append({
                    **ind,
                    "level": level,
                    "percentage": round(percentage, 1)
                })
            
            return {
                "major": m["name"],
                "indicators": indicators_with_level
            }
    
    raise HTTPException(status_code=404, detail="专业不存在")


@app.get("/api/warnings")
async def get_warnings():
    """Get warning status for all majors."""
    data = load_data()
    warnings = []
    
    for m in data["majors"]:
        green_count = 0
        yellow_count = 0
        red_count = 0
        green_list = []
        yellow_list = []
        red_list = []
        
        for ind in m["indicators"]:
            if ind["weight"] > 0:
                percentage = (ind["score"] / ind["weight"]) * 100
                level = get_warning_level(ind["name"], percentage)
            else:
                level = "green"
            
            if level == "green":
                green_count += 1
                green_list.append(ind["name"])
            elif level == "yellow":
                yellow_count += 1
                yellow_list.append(ind["name"])
            elif level == "red":
                red_count += 1
                red_list.append(ind["name"])
        
        warnings.append({
            "majorId": m["id"],
            "majorName": m["name"],
            "totalScore": m["totalScore"],
            "scoreRate": m["scoreRate"],
            "greenCount": green_count,
            "yellowCount": yellow_count,
            "redCount": red_count,
            "greenIndicators": green_list,
            "yellowIndicators": yellow_list,
            "redIndicators": red_list
        })
    
    return {"warnings": warnings}


@app.get("/api/radar")
async def get_radar_data():
    """Get data for radar chart comparison."""
    data = load_data()
    
    # Get all indicator names (first 6 key indicators for radar)
    indicator_names = ["X1", "X2", "X3", "X4", "X5", "X7"]
    indicator_labels = ["招生完成率", "在校生满意度", "毕业生满意度", "职业资格", "就业落实率", "双师型教师"]
    
    radar_data = []
    for m in data["majors"]:
        # Calculate percentage scores for each indicator
        scores = []
        for i, ind_id in enumerate(indicator_names):
            for ind in m["indicators"]:
                if ind["id"] == ind_id and ind["weight"] > 0:
                    score = (ind["score"] / ind["weight"]) * 100
                    scores.append(round(score, 1))
                    break
            else:
                scores.append(0)
        
        radar_data.append({
            "majorId": m["id"],
            "majorName": m["name"],
            "scores": scores
        })
    
    return {
        "indicators": indicator_labels,
        "majors": radar_data
    }


@app.get("/api/report/{major_id}")
async def get_report(major_id: str):
    """Generate analysis report for a specific major."""
    data = load_data()
    
    for m in data["majors"]:
        if m["id"] == major_id:
            return generate_report(m)
    
    raise HTTPException(status_code=404, detail="专业不存在")


@app.get("/api/summary")
async def get_summary():
    """Get overall summary statistics."""
    data = load_data()
    
    totals = [m["totalScore"] for m in data["majors"]]
    rates = [m["scoreRate"] for m in data["majors"]]
    
    return {
        "avgScore": round(sum(totals) / len(totals), 2),
        "maxScore": max(totals),
        "minScore": min(totals),
        "avgRate": round(sum(rates) / len(rates) * 100, 1),
        "totalMajors": len(data["majors"])
    }


@app.get("/api/all-reports")
async def get_all_reports():
    """Generate reports for all majors."""
    data = load_data()
    reports = []
    
    for m in data["majors"]:
        reports.append(generate_report(m))
    
    return {"reports": reports}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
