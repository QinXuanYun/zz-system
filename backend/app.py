from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import json, os, math

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

def load_data():
    with open(os.path.join(DATA_DIR, 'indicators.json'), 'r', encoding='utf-8') as f:
        return json.load(f)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/overview')
def overview():
    """学院总览 - 所有专业最新学年的概览"""
    db = load_data()
    meta = db['meta']
    latest_year = meta['years'][-1]
    year_data = db['data'][latest_year]
    indicators = meta['indicators']
    
    majors_overview = []
    total_red = 0
    total_yellow = 0
    total_blue = 0
    total_green = 0
    
    for m in meta['majors']:
        mid = m['id']
        md = year_data[mid]
        counts = {'red': 0, 'yellow': 0, 'blue': 0, 'green': 0}
        details = {'red': [], 'yellow': [], 'blue': [], 'green': []}
        
        prev_year = meta['years'][-2] if len(meta['years']) > 1 else None
        prev_data = db['data'].get(prev_year, {}).get(mid, {}).get('raw', {}) if prev_year else {}
        
        for ind in indicators:
            iid = ind['id']
            val = md['raw'].get(iid, 0)
            th = ind['thresholds']
            ind_format = ind.get('format', 'pct')  # Default to pct
            level = get_level(val, th, iid, ind_format)
            
            # Check blue: normal but negative trend vs previous year
            if level == 'green' and prev_data:
                prev_val = prev_data.get(iid, 0)
                if val < prev_val:
                    level = 'blue'
            
            counts[level] += 1
            details[level].append(ind['name'])
        
        total_red += counts['red']
        total_yellow += counts['yellow']
        total_blue += counts['blue']
        total_green += counts['green']
        
        majors_overview.append({
            'id': mid,
            'name': m['name'],
            'fullName': m['fullName'],
            'total': md['total'],
            'scoreRate': md['scoreRate'],
            'counts': counts,
            'details': details
        })
    
    # Sort by scoreRate descending
    majors_overview.sort(key=lambda x: x['scoreRate'], reverse=True)
    
    return jsonify({
        'year': latest_year,
        'years': meta['years'],
        'summary': {
            'totalMajors': len(meta['majors']),
            'red': total_red,
            'yellow': total_yellow,
            'blue': total_blue,
            'green': total_green,
            'avgScoreRate': round(sum(m['scoreRate'] for m in majors_overview) / len(majors_overview), 4)
        },
        'majors': majors_overview
    })

@app.route('/api/major/<major_id>')
def major_detail(major_id):
    """单个专业详情 - 所有学年所有指标"""
    db = load_data()
    meta = db['meta']
    indicators = meta['indicators']
    
    result = {'years': {}, 'indicators': indicators, 'majorName': ''}
    for m in meta['majors']:
        if m['id'] == major_id:
            result['majorName'] = m['name']
            result['fullName'] = m['fullName']
            break
    
    for year in meta['years']:
        md = db['data'][year].get(major_id, {})
        if md:
            ind_details = []
            for ind in indicators:
                iid = ind['id']
                val = md['raw'].get(iid, 0)
                score = md['score'].get(iid, 0)
                ind_format = ind.get('format', 'pct')
                level = get_level(val, ind['thresholds'], iid, ind_format)
                ind_details.append({
                    'id': iid,
                    'name': ind['name'],
                    'raw': val,
                    'score': score,
                    'weight': ind['weight'],
                    'level': level,
                    'format': ind_format,
                    'unit': ind.get('unit', '')
                })
            result['years'][year] = {
                'indicators': ind_details,
                'total': md['total'],
                'scoreRate': md['scoreRate']
            }
    
    return jsonify(result)

@app.route('/api/trends/<major_id>')
def trends(major_id):
    """趋势数据 - 某专业所有指标的多年趋势"""
    db = load_data()
    meta = db['meta']
    years = meta['years']
    
    trends_data = []
    for ind in meta['indicators']:
        iid = ind['id']
        values = []
        scores = []
        for year in years:
            md = db['data'][year].get(major_id, {})
            values.append(md.get('raw', {}).get(iid, 0))
            scores.append(md.get('score', {}).get(iid, 0))
        
        # Simple linear trend
        n = len(values)
        if n >= 2:
            x_mean = (n - 1) / 2
            y_mean = sum(values) / n
            num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den != 0 else 0
            predicted_next = values[-1] + slope
        else:
            slope = 0
            predicted_next = values[-1] if values else 0
        
        ind_format = ind.get('format', 'pct')
        trends_data.append({
            'id': iid,
            'name': ind['name'],
            'values': values,
            'scores': scores,
            'slope': round(slope, 4),
            'predicted': round(predicted_next, 4),
            'level': get_level(values[-1], ind['thresholds'], iid, ind_format) if values else 'green',
            'format': ind_format
        })
    
    return jsonify({'years': years, 'trends': trends_data})

@app.route('/api/compare')
def compare():
    """专业对比 - 雷达图数据"""
    db = load_data()
    meta = db['meta']
    major_ids = request.args.getlist('majors')
    year = request.args.get('year', meta['years'][-1])
    
    if not major_ids:
        major_ids = [m['id'] for m in meta['majors']]
    
    year_data = db['data'].get(year, {})
    
    compare_data = []
    for mid in major_ids:
        md = year_data.get(mid, {})
        if md:
            name = next((m['name'] for m in meta['majors'] if m['id'] == mid), mid)
            scores = [md['score'].get(ind['id'], 0) for ind in meta['indicators']]
            # Normalize to percentage of max possible score (weight)
            max_scores = [ind['weight'] for ind in meta['indicators']]
            pct = [round(s / m * 100, 1) if m > 0 else 0 for s, m in zip(scores, max_scores)]
            compare_data.append({
                'id': mid,
                'name': name,
                'scores': scores,
                'percentages': pct,
                'total': md['total'],
                'scoreRate': md['scoreRate']
            })
    
    return jsonify({
        'year': year,
        'indicators': [{'name': ind['name'], 'weight': ind['weight']} for ind in meta['indicators']],
        'majors': compare_data
    })

@app.route('/api/ranking')
def ranking():
    """排行榜 - 按指标或总分排名"""
    db = load_data()
    meta = db['meta']
    year = request.args.get('year', meta['years'][-1])
    indicator_id = request.args.get('indicator', None)
    
    year_data = db['data'].get(year, {})
    rankings = []
    
    for m in meta['majors']:
        mid = m['id']
        md = year_data.get(mid, {})
        if md:
            if indicator_id:
                val = md['raw'].get(indicator_id, 0)
                score = md['score'].get(indicator_id, 0)
            else:
                val = md['scoreRate']
                score = md['total']
            rankings.append({
                'id': mid,
                'name': m['name'],
                'value': val,
                'score': score
            })
    
    rankings.sort(key=lambda x: x['value'], reverse=True)
    for i, r in enumerate(rankings):
        r['rank'] = i + 1
    
    return jsonify({'year': year, 'indicator': indicator_id, 'rankings': rankings})

@app.route('/api/warnings')
def warnings():
    """预警汇总"""
    db = load_data()
    meta = db['meta']
    year = request.args.get('year', meta['years'][-1])
    year_data = db['data'].get(year, {})
    
    warnings_list = []
    for m in meta['majors']:
        mid = m['id']
        md = year_data.get(mid, {})
        if not md:
            continue
        
        prev_year = meta['years'][-2] if len(meta['years']) > 1 else None
        prev_data = db['data'].get(prev_year, {}).get(mid, {}).get('raw', {}) if prev_year else {}
        
        for ind in meta['indicators']:
            iid = ind['id']
            val = md['raw'].get(iid, 0)
            ind_format = ind.get('format', 'pct')
            level = get_level(val, ind['thresholds'], iid, ind_format)
            
            if level == 'green' and prev_data:
                prev_val = prev_data.get(iid, 0)
                if val < prev_val:
                    level = 'blue'
            
            if level in ('red', 'yellow'):
                change = None
                if prev_data and iid in prev_data:
                    change = round(val - prev_data[iid], 4)
                warnings_list.append({
                    'majorId': mid,
                    'majorName': m['name'],
                    'indicatorId': iid,
                    'indicatorName': ind['name'],
                    'value': val,
                    'level': level,
                    'change': change,
                    'format': ind_format
                })
    
    warnings_list.sort(key=lambda x: (0 if x['level'] == 'red' else 1, x['majorName']))
    return jsonify({'year': year, 'warnings': warnings_list})

@app.route('/api/report/<major_id>')
def report(major_id):
    """生成专业诊断报告"""
    db = load_data()
    meta = db['meta']
    latest_year = meta['years'][-1]
    md = db['data'][latest_year].get(major_id, {})
    
    major_name = next((m['name'] for m in meta['majors'] if m['id'] == major_id), major_id)
    
    sections = []
    red_items = []
    yellow_items = []
    green_items = []
    blue_items = []
    
    for ind in meta['indicators']:
        iid = ind['id']
        val = md['raw'].get(iid, 0)
        ind_format = ind.get('format', 'pct')
        level = get_level(val, ind['thresholds'], iid, ind_format)
        
        # Get trend
        values = [db['data'][y].get(major_id, {}).get('raw', {}).get(iid, 0) for y in meta['years']]
        trend = 'stable'
        if len(values) >= 2:
            if values[-1] > values[-2]:
                trend = 'up'
            elif values[-1] < values[-2]:
                trend = 'down'
        
        item = {'id': iid, 'name': ind['name'], 'value': val, 'level': level, 'trend': trend, 'history': values}
        if level == 'red':
            red_items.append(item)
        elif level == 'yellow':
            yellow_items.append(item)
        elif level == 'blue':
            blue_items.append(item)
        else:
            green_items.append(item)
    
    # Build report text
    report_text = f"【{major_name}】专业发展诊断报告 ({latest_year})\n\n"
    report_text += f"综合得分：{md['total']:.1f} / 47分，得分率：{md['scoreRate']*100:.1f}%\n\n"
    
    if red_items:
        report_text += "🔴 红色预警指标：\n"
        for item in red_items:
            report_text += f"  · {item['name']}：{format_value(item['value'], item['id'])}，趋势{'↑上升' if item['trend']=='up' else '↓下降' if item['trend']=='down' else '→持平'}\n"
        report_text += "\n"
    
    if yellow_items:
        report_text += "🟡 黄色预警指标：\n"
        for item in yellow_items:
            report_text += f"  · {item['name']}：{format_value(item['value'], item['id'])}，趋势{'↑上升' if item['trend']=='up' else '↓下降' if item['trend']=='down' else '→持平'}\n"
        report_text += "\n"
    
    if blue_items:
        report_text += "🔵 关注指标（正常但有负向波动）：\n"
        for item in blue_items:
            report_text += f"  · {item['name']}：{format_value(item['value'], item['id'])}\n"
        report_text += "\n"
    
    if green_items:
        report_text += "🟢 健康指标：\n"
        for item in green_items:
            report_text += f"  · {item['name']}：{format_value(item['value'], item['id'])}\n"
    
    return jsonify({
        'majorId': major_id,
        'majorName': major_name,
        'year': latest_year,
        'total': md['total'],
        'scoreRate': md['scoreRate'],
        'red': red_items,
        'yellow': yellow_items,
        'blue': blue_items,
        'green': green_items,
        'reportText': report_text
    })

def format_value(val, iid, ind_format=None):
    """Format value based on indicator format.
    
    Args:
        val: The raw value
        iid: Indicator ID (for backward compatibility)
        ind_format: Optional format ('pct', 'ratio', 'days')
    """
    # For ratio format (生师比): show as "16.5:1"
    if ind_format == 'ratio':
        return f"{val:.1f}:1"
    
    # For pct format: show as percentage
    if ind_format == 'pct':
        # val is stored as decimal fraction (0.88 for 88%)
        # Convert to percentage for display
        return f"{val * 100:.1f}%"
    
    # For days format
    if ind_format == 'days':
        return f"{val:.1f}天"
    
    # Fallback for backward compatibility
    if iid == 'X11':
        return f"{val:.1f}天"
    elif val <= 2:
        return f"{val*100:.1f}%"
    else:
        return f"{val:.2f}"

def get_level(val, thresholds, iid=None, ind_format=None):
    """Determine warning level based on thresholds.
    
    For ratio format (like 生师比): lower is better
    - green: val <= green_threshold (e.g., 18)
    - yellow: green < val <= yellow_threshold (e.g., 22)
    - red: val > yellow_threshold
    
    For pct format: higher is better
    - Uses [low, high) tuple thresholds
    """
    # Check if this is a ratio format indicator
    # Ratio thresholds have numeric values like {'green': 18, 'yellow': 22, 'red': 999}
    # Pct thresholds have tuple values like {'red': [0, 0.85], 'yellow': [0.85, 0.90], ...}
    
    if ind_format == 'ratio' or (thresholds and isinstance(thresholds.get('green'), (int, float)) and not isinstance(thresholds.get('green'), tuple)):
        # Ratio format: lower is better
        green_thresh = thresholds.get('green', 18)
        yellow_thresh = thresholds.get('yellow', 22)
        
        if val <= green_thresh:
            return 'green'
        elif val <= yellow_thresh:
            return 'yellow'
        else:
            return 'red'
    
    # Pct format: higher is better (original logic)
    for level in ['red', 'yellow', 'blue', 'green']:
        if level in thresholds:
            low, high = thresholds[level]
            if low <= val < high:
                return level
    return 'green'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8089, debug=False)
