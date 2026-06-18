def get_styles():
    return """
    <style>
        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            overflow-x: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f3f4f6;
            color: #0f172a;
        }

        .dashboard-tab {
            display: none;
        }

        .dashboard-tab.active-tab {
            display: block;
        }

        .nav-link.active {
            background: #0f172a;
            color: white;
        }

        .dashboard {
            width: 100%;
            max-width: 1500px;
            margin: 0 auto;
            padding: 24px;
            overflow-x: hidden;
        }

        
        .ai-card {
    border: 1px solid #c7d2fe;
    background: linear-gradient(180deg, #ffffff, #f8fafc);
}

        .ai-summary {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 14px;
            font-size: 14px;
            line-height: 1.5;
        }

        .ai-summary p {
            margin: 8px 0 0;
        }

        .ai-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin-bottom: 14px;
        }

        .ai-actions {
            margin: 10px 0 0;
            padding-left: 22px;
            line-height: 1.6;
        }

        @media (max-width: 1000px) {
            .ai-grid {
                grid-template-columns: 1fr;
            }
        }


        .section-anchor {
            scroll-margin-top: 90px;
        }

        .navbar {
            position: sticky;
            top: 0;
            z-index: 50;
            background: rgba(243, 244, 246, 0.92);
            backdrop-filter: blur(12px);
            padding: 12px 0 18px;
            margin-bottom: 8px;
        }

        .nav-inner {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .nav-link {
            text-decoration: none;
            color: #334155;
            background: white;
            border: 1px solid #e5e7eb;
            padding: 9px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 650;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
            cursor: pointer;
        }

        .nav-link:hover {
            background: #0f172a;
            color: white;
        }

        .hero {
            background: linear-gradient(135deg, #0f172a, #1e293b);
            color: white;
            border-radius: 24px;
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.18);
        }

        .hero-top {
            display: flex;
            justify-content: space-between;
            gap: 20px;
            align-items: flex-start;
        }

        .hero h1 {
            margin: 0;
            font-size: 34px;
            letter-spacing: -0.03em;
        }

        .hero p {
            color: #cbd5e1;
            margin-top: 8px;
        }

        .period-pill {
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 999px;
            padding: 10px 16px;
            white-space: nowrap;
            font-size: 14px;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 16px;
            margin-top: 24px;
        }

        .kpi {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 18px;
            padding: 18px;
            min-width: 0;
        }

        .kpi-label {
            color: #cbd5e1;
            font-size: 13px;
            margin-bottom: 8px;
        }

        .kpi-value {
            font-size: 28px;
            font-weight: 750;
            letter-spacing: -0.03em;
        }

        .main-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
            gap: 20px;
            margin-bottom: 20px;
        }

        .three-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 22px;
            padding: 20px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
            overflow: hidden;
            min-width: 0;
        }

        .card h2 {
            font-size: 18px;
            margin: 0 0 14px;
            letter-spacing: -0.02em;
        }

        .mini-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }

        .mini-kpi {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 14px;
        }

        .mini-kpi span {
            color: #64748b;
            font-size: 12px;
            display: block;
        }

        .mini-kpi strong {
            font-size: 22px;
            margin-top: 6px;
            display: block;
        }

        .insight {
            border-radius: 16px;
            padding: 14px;
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            font-size: 14px;
            line-height: 1.45;
            margin-bottom: 10px;
        }

        .tag {
            display: inline-block;
            border-radius: 999px;
            padding: 4px 9px;
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .green { background: #dcfce7; color: #166534; }
        .orange { background: #ffedd5; color: #9a3412; }
        .red { background: #fee2e2; color: #991b1b; }
        .blue { background: #dbeafe; color: #1e40af; }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        .kpi-grid-five {
            grid-template-columns: repeat(5, minmax(0, 1fr));
        }

        .kpi-delta.neutral {
            color: #cbd5e1;
        }

        .sales-v2 {
            display: flex;
            flex-direction: column;
            gap: 22px;
        }

        .sales-hero {
            background: #0f172a;
            color: white;
            border-radius: 24px;
            padding: 28px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .sales-hero h1 {
            margin: 0;
            font-size: 30px;
        }

        .sales-hero p {
            color: #cbd5e1;
            margin: 8px 0 0;
        }

        .sales-kpi-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 16px;
        }

        .sales-kpi,
        .sales-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 22px;
            padding: 20px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
        }

        .sales-kpi span {
            display: block;
            color: #64748b;
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .sales-kpi strong {
            font-size: 24px;
            color: #0f172a;
        }

        .sales-main-grid {
            display: grid;
            grid-template-columns: 1.45fr 1fr;
            gap: 20px;
        }

        .sales-three-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }

        .sales-two-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }

        .sales-card.full {
            width: 100%;
        }

        .sales-card h2,
        .sales-card h3 {
            margin: 0 0 16px;
            color: #0f172a;
        }

        .sales-card-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 16px;
            margin-bottom: 16px;
        }

        .sales-card-header h2 {
            margin: 0;
        }

        .sales-card-header span {
            color: #64748b;
            font-size: 13px;
            font-weight: 700;
        }

        .sales-highlight {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 18px;
            padding: 16px;
            margin-bottom: 18px;
        }

        .sales-highlight span {
            font-size: 12px;
            font-weight: 800;
            color: #1d4ed8;
        }

        .sales-highlight strong {
            display: block;
            font-size: 22px;
            margin-top: 4px;
        }

        .sales-highlight p {
            color: #475569;
            margin: 6px 0 0;
        }

        .sales-bar-row {
            display: grid;
            grid-template-columns: minmax(180px, 1fr) 2fr 85px;
            align-items: center;
            gap: 14px;
            margin-bottom: 13px;
        }

        .sales-bar-label {
            color: #334155;
            font-size: 13px;
            font-weight: 700;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .sales-bar-track {
            height: 13px;
            background: #e5e7eb;
            border-radius: 999px;
            overflow: hidden;
        }

        .sales-bar-fill {
            height: 100%;
            background: #2563eb;
            border-radius: 999px;
        }

        .sales-bar-value {
            text-align: right;
            color: #0f172a;
            font-size: 13px;
            font-weight: 800;
        }

        .sales-note {
            color: #64748b;
            font-size: 13px;
            margin-top: 14px;
        }

        @media (max-width: 1000px) {
            .sales-kpi-grid,
            .sales-main-grid,
            .sales-three-grid,
            .sales-two-grid {
                grid-template-columns: 1fr;
            }
        }

        .custom-bar-chart {
            width: 100%;
            padding: 8px 4px;
        }

        .custom-chart-title {
            font-size: 18px;
            font-weight: 700;
            color: #1e293b;
            margin-bottom: 18px;
        }

        .custom-bar-row {
            display: grid;
            grid-template-columns: minmax(260px, 1.2fr) 2fr 90px;
            align-items: center;
            gap: 14px;
            margin-bottom: 14px;
        }

        .custom-bar-label {
            font-size: 13px;
            color: #334155;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .custom-bar-track {
            height: 16px;
            background: #e5e7eb;
            border-radius: 999px;
            overflow: hidden;
        }

        .custom-bar-fill {
            height: 100%;
            background: #2563eb;
            border-radius: 999px;
        }

        .custom-bar-value {
            font-size: 13px;
            font-weight: 700;
            color: #0f172a;
            text-align: right;
        }

        .date-range {
            margin-top: 12px;
            color: #cbd5e1;
            font-size: 13px;
        }

        .date-range span {
            margin: 0 8px;
            color: #94a3b8;
        }

        .kpi-delta {
            margin-top: 8px;
            font-size: 13px;
            font-weight: 700;
        }

        .kpi-delta.positive {
            color: #86efac;
        }

        .kpi-delta.negative {
            color: #fca5a5;
        }
        
        .data-table th {
            text-align: left;
            padding: 11px;
            background: #f8fafc;
            color: #475569;
            border-bottom: 1px solid #e5e7eb;
            white-space: nowrap;
        }

        .data-table td {
            padding: 11px;
            border-bottom: 1px solid #e5e7eb;
            white-space: nowrap;
        }

        .full {
            margin-bottom: 20px;
            overflow-x: auto;
        }

        .chart-empty, .empty {
            padding: 30px;
            color: #64748b;
            background: #f8fafc;
            border-radius: 16px;
            text-align: center;
        }

        @media (max-width: 1000px) {
            .kpi-grid,
            .main-grid,
            .three-grid {
                grid-template-columns: 1fr;
            }

            .hero-top {
                flex-direction: column;
            }
        }
    </style>
    """