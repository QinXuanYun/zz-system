"""
Database models and operations for Academic Report System
"""
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "academic_report.db"
DB_PATH.parent.mkdir(exist_ok=True)

# Create engine
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Year(Base):
    """Academic year"""
    __tablename__ = "years"
    
    id = Column(Integer, primary_key=True, index=True)
    year_name = Column(String(50), unique=True, index=True)  # e.g., "2023-2024学年"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    majors = relationship("Major", back_populates="year", cascade="all, delete-orphan")


class Major(Base):
    """Major/Professional information"""
    __tablename__ = "majors"
    
    id = Column(Integer, primary_key=True, index=True)
    year_id = Column(Integer, ForeignKey("years.id"))
    major_id = Column(String(50))  # e.g., "major_0"
    name = Column(String(100))  # Sheet name from Excel
    full_name = Column(String(200))
    
    year = relationship("Year", back_populates="majors")
    indicators = relationship("IndicatorValue", back_populates="major", cascade="all, delete-orphan")


class IndicatorValue(Base):
    """Indicator values for each major"""
    __tablename__ = "indicator_values"
    
    id = Column(Integer, primary_key=True, index=True)
    major_id = Column(Integer, ForeignKey("majors.id"))
    indicator_id = Column(String(10))  # X1, X2, ..., X15
    value = Column(Float)
    
    major = relationship("Major", back_populates="indicators")


class IndicatorMeta(Base):
    """Indicator metadata (thresholds, etc.)"""
    __tablename__ = "indicator_meta"
    
    id = Column(Integer, primary_key=True, index=True)
    indicator_id = Column(String(10), unique=True, index=True)
    name = Column(String(100))
    weight = Column(Integer)
    unit = Column(String(20))
    method = Column(Text)
    red_threshold = Column(Float)
    yellow_threshold = Column(Float)
    green_threshold = Column(Float)
    higher_is_better = Column(Integer, default=1)  # 1=True, 0=False
    format = Column(String(20))  # pct, ratio, days, num


# Initialize database
def init_db():
    Base.metadata.create_all(bind=engine)
    init_indicator_meta()


def init_indicator_meta():
    """Initialize indicator metadata"""
    db = SessionLocal()
    try:
        # Check if already initialized
        if db.query(IndicatorMeta).first():
            return
        
        indicators = [
            {
                "indicator_id": "X1", "name": "报到率", "weight": 5, "unit": "%",
                "method": "(实际录取数/招生计划数)*100%",
                "red_threshold": 0.85, "yellow_threshold": 0.90, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X2", "name": "生师比", "weight": 3, "unit": ":1",
                "method": "折合在校生数/折合教师数",
                "red_threshold": 18, "yellow_threshold": 22, "green_threshold": 999,
                "higher_is_better": 0, "format": "ratio"
            },
            {
                "indicator_id": "X3", "name": "课程优良率", "weight": 3, "unit": "%",
                "method": "学生评教'优良'课程比例",
                "red_threshold": 0.70, "yellow_threshold": 0.85, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X4", "name": "技能证书通过率", "weight": 4, "unit": "%",
                "method": "获相关职业资格证书学生比例",
                "red_threshold": 0.60, "yellow_threshold": 0.75, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X5", "name": "毕业率", "weight": 3, "unit": "%",
                "method": "当届毕业生实际毕业比例",
                "red_threshold": 0.95, "yellow_threshold": 0.97, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X6", "name": "就业去向落实率", "weight": 5, "unit": "%",
                "method": "截止当年底的毕业生就业率",
                "red_threshold": 0.92, "yellow_threshold": 0.96, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X7", "name": "专业相关度", "weight": 4, "unit": "%",
                "method": "就业岗位与专业相关毕业生比例",
                "red_threshold": 0.68, "yellow_threshold": 0.70, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X8", "name": "在校生满意度", "weight": 4, "unit": "%",
                "method": "在校生对所学专业的满意度",
                "red_threshold": 0.91, "yellow_threshold": 0.95, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X9", "name": "毕业生满意度", "weight": 4, "unit": "%",
                "method": "毕业生对所学专业的满意度",
                "red_threshold": 0.92, "yellow_threshold": 0.95, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X10", "name": "企业订单学生占比", "weight": 4, "unit": "%",
                "method": "专业接受企业订单且在该企业就业的学生比例",
                "red_threshold": 0.08, "yellow_threshold": 0.15, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X11", "name": "双师型专任教师占比", "weight": 3, "unit": "%",
                "method": "双师型专任教师占专任教师总数的百分比",
                "red_threshold": 0.60, "yellow_threshold": 0.75, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X12", "name": "高级职称专任教师占比", "weight": 3, "unit": "%",
                "method": "高级职称的专任教师占专任教师总数的比例",
                "red_threshold": 0.15, "yellow_threshold": 0.25, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X13", "name": "高技术技能人才占比", "weight": 3, "unit": "%",
                "method": "高技术技能人才占专任教师总数的比例",
                "red_threshold": 0.05, "yellow_threshold": 0.10, "green_threshold": 1.00,
                "higher_is_better": 1, "format": "pct"
            },
            {
                "indicator_id": "X14", "name": "师均论文数、著作数、课题数", "weight": 3, "unit": "项",
                "method": "论文、著作、课题数与专任教师总数的比值",
                "red_threshold": 0.5, "yellow_threshold": 1.0, "green_threshold": 2.0,
                "higher_is_better": 1, "format": "num"
            },
            {
                "indicator_id": "X15", "name": "教师人均企业实践时间", "weight": 3, "unit": "天",
                "method": "教师企业实践总天数与专任教师总数的比值",
                "red_threshold": 18, "yellow_threshold": 30, "green_threshold": 999,
                "higher_is_better": 1, "format": "days"
            },
        ]
        
        for ind in indicators:
            db.add(IndicatorMeta(**ind))
        
        db.commit()
    finally:
        db.close()


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def get_years() -> List[str]:
    """Get all years from database"""
    db = SessionLocal()
    try:
        years = db.query(Year).order_by(Year.year_name.desc()).all()
        return [y.year_name for y in years]
    finally:
        db.close()


def get_year_data(year_name: str) -> Dict[str, Any]:
    """Get all data for a specific year"""
    db = SessionLocal()
    try:
        year = db.query(Year).filter(Year.year_name == year_name).first()
        if not year:
            return None
        
        result = {
            "meta": {
                "school": "",
                "years": get_years(),
                "indicators": [],
                "majors": []
            },
            "data": {year_name: {}}
        }
        
        # Get indicator metadata
        ind_meta = db.query(IndicatorMeta).all()
        for ind in ind_meta:
            result["meta"]["indicators"].append({
                "id": ind.indicator_id,
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
            })
        
        # Get majors and their indicator values
        for major in year.majors:
            result["meta"]["majors"].append({
                "id": major.major_id,
                "name": major.name,
                "fullName": major.full_name
            })
            
            result["data"][year_name][major.major_id] = {}
            for ind_val in major.indicators:
                result["data"][year_name][major.major_id][ind_val.indicator_id] = ind_val.value
        
        return result
    finally:
        db.close()


def import_excel_data(year_name: str, majors_data: List[Dict]) -> bool:
    """Import Excel data into database"""
    db = SessionLocal()
    try:
        # Check if year exists
        year = db.query(Year).filter(Year.year_name == year_name).first()
        if year:
            # Delete existing data for this year
            db.delete(year)
            db.commit()
        
        # Create new year
        year = Year(year_name=year_name)
        db.add(year)
        db.flush()
        
        # Add majors and their indicators
        for idx, major_data in enumerate(majors_data):
            major = Major(
                year_id=year.id,
                major_id=f"major_{idx}",
                name=major_data["name"],
                full_name=major_data["name"]
            )
            db.add(major)
            db.flush()
            
            # Add indicator values
            for ind_id, value in major_data["indicators"].items():
                ind_val = IndicatorValue(
                    major_id=major.id,
                    indicator_id=ind_id,
                    value=value
                )
                db.add(ind_val)
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Import error: {e}")
        return False
    finally:
        db.close()


# Initialize database on module load
init_db()
