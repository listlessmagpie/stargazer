@echo off
rem The learning loop's daily step: forecast every market before the fact, score what came due,
rem refresh the occasions when stale, move the paper book, write record.json for the live show,
rem and publish the record. Touches no money.
cd /d D:\git\stargazer
echo [%date% %time%] daily starting >> forecast_daily.log
"D:\git\paradox-box\.venv\Scripts\python.exe" almanac.py --daily >> forecast_daily.log 2>&1
git add FORECASTS.md forecasts.jsonl forecast.json record.json paper_book.json ALMANAC_OCCASIONS.md almanac_occasions.json >> forecast_daily.log 2>&1
git commit -q -m "Record, written before the fact" -- FORECASTS.md forecasts.jsonl forecast.json record.json paper_book.json ALMANAC_OCCASIONS.md almanac_occasions.json >> forecast_daily.log 2>&1
git push -q >> forecast_daily.log 2>&1
echo [%date% %time%] daily done >> forecast_daily.log
