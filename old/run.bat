@echo off
cd /d D:\git\stargazer
echo [%date% %time%] stargazer starting >> stargazer.log
python -u agent.py --loop >> stargazer.log 2>&1
echo [%date% %time%] stargazer exited >> stargazer.log
