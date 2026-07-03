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
    
    # Исправляем дату
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True, errors='coerce')
    
    html = f"""
    <html>
    <head>
        <title>Fastpari Monitoring - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; }}
            th {{ background-color: #f0f0f0; }}
        </style>
    </head>
    <body>
        <h1>Fastpari Performance Report</h1>
        <p>Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """
    
    html += "<h2>Результаты измерений</h2>"
    html += df.sort_values(by='datetime', ascending=False).to_html(index=False)
    
    # Графики
    if len(df) > 0:
        fig1 = px.bar(df, x='page', y='ttfb', color='geo', 
                     title='TTFB по страницам и гео (мс)',
                     labels={'ttfb': 'Time to First Byte (мс)'})
        
        fig2 = px.bar(df, x='page', y='load', color='geo', 
                     title='Full Load Time по страницам и гео (мс)')
        
        html += fig1.to_html(full_html=False, include_plotlyjs=False)
        html += fig2.to_html(full_html=False, include_plotlyjs=False)
    
    html += "</body></html>"
    
    with open("reports/report.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✅ Отчёт создан: reports/report.html")