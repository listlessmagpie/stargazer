@echo off
rem Writes the day's forecast before the fact and publishes it. Touches no money.
cd /d D:\git\stargazer
echo [%date% %time%] forecast starting >> forecast_daily.log
"D:\git\paradox-box\.venv\Scripts\python.exe" almanac.py --forecast >> forecast_daily.log 2>&1
git add FORECASTS.md forecasts.jsonl >> forecast_daily.log 2>&1
git commit -q -m "Forecast, written before the fact" -- FORECASTS.md forecasts.jsonl >> forecast_daily.log 2>&1
git push -q >> forecast_daily.log 2>&1
echo [%date% %time%] forecast done >> forecast_daily.log
