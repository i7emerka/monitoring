import pandas as pd
import plotly.express as px
from datetime import datetime
import os

def generate_html_report():
    csv_path = "reports/metrics.csv"
    if not os.path.exists(csv_path):
        print("CSV файл не найден")
        return
    
    df = pd.read_csv(csv_path)
    
    # Исправленное преобразование времени
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True, errors='coerce')
    
    # Основной отчёт
    html = f"""
    <html>
    <head>
        <title>Fastpari Monitoring Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>Fastpari Performance Monitoring</h1>
        <p>Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """
    
    # Таблица
    html += "<h2>Все результаты</h2>"
    html += df.sort_values('datetime', ascending=False).to_html(index=False)
    
    # Графики
    if not df.empty:
        fig_ttfb = px.bar(df, x='page', y='ttfb', color='geo', 
                         title='TTFB (мс) по страницам и гео',
                         labels={'ttfb': 'TTFB (мс)'})
        
        fig_load = px.bar(df, x='page', y='load', color='geo', 
                         title='Full Load Time (мс) по страницам и гео',
                         labels={'load': 'Load Time (мс)'})
        
        html += fig_ttfb.to_html(full_html=False, include_plotlyjs=False)
        html += fig_load.to_html(full_html=False, include_plotlyjs=False)
    
    html += "</body></html>"
    
    report_path = "reports/report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✅ HTML-отчёт успешно создан: {report_path}")