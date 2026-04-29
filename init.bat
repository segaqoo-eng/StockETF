@echo off
echo === StockETF 初始化 ===
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
echo.
echo === 完成！之後執行方式 ===
echo 更新持股資料：.venv\Scripts\python.exe main.py
echo 回測：        .venv\Scripts\python.exe backtest.py
echo 看網站：      .venv\Scripts\python.exe -m http.server 8080
echo.
pause
