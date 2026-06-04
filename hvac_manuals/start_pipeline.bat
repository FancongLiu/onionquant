@echo off
cd /d "e:\2026_AgentStudy\Python_code"
call .venv\Scripts\python.exe hvac_manuals/auto_pipeline.py >> hvac_manuals/stdout.log 2>> hvac_manuals/stderr.log
echo Pipeline exited at %date% %time% >> hvac_manuals/stdout.log
