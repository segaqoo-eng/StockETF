# 持股每日差異比較（待實作，v2 F5）

## 需求

每檔 ETF 顯示今日 vs 昨日差異：

- **A. 新增/移除的股票**（🆕 新進 / ❌ 移除）
- **B. 權重增減**（▲ +0.5% / ▼ -0.3%）

## 資料層（已就緒）

`data/snapshots/YYYYMMDD.json` 每日快照已存在，**不需改結構**。

## v2 實作規格

### Backend：`normalizer.py` 加 diff function

```python
def compute_diff(today: dict, yesterday: dict) -> dict:
    """
    回傳每支 ETF 的持股差異
    {
      "00982A": {
        "added":   [{"ticker": "2330", "name": "台積電", "weight": 8.43}],
        "removed": [{"ticker": "1234", "name": "某某",   "weight": 1.2}],
        "changed": [
          {
            "ticker": "5536",
            "name": "聖暉",
            "weight_today": 8.43,
            "weight_yesterday": 7.9,
            "delta": +0.53
          }
        ]
      }
    }
    """
```

輸出寫入 `data/latest_diff.json`（跟 `latest.json` 同層）。

### Frontend：`index.html` 持股列加 diff badge

- **🆕 綠色標籤**：今日新進
- **❌ 紅色標籤**：昨日移除（顯示在昨日欄）
- **▲ +0.53% 綠字** / **▼ -0.53% 紅字**：權重變動

## 注意事項

- **diff 計算只針對 `market == "TW"` 的股票** — 與交叉分析主表保持一致。美股/日股的權重變動就算抓到也不顯示在 diff badge 上（避免主表沒有的標的卻在 diff 裡冒出來）
- **群益目前只有 top-10**，diff 準確度受限 — badge 旁加 `*` 備註。詳見 `docs/known-issues/capital-scraper.md`
- **第一天無昨日快照**時，diff 全部顯示 `N/A`
- `snapshots/` 保留 30 天，超過自動清理（v2 時一併實作）

## 相關檔案

- `data/snapshots/YYYYMMDD.json`（既有）
- `normalizer.py`（要加 `compute_diff`）
- `index.html`（要加 badge 渲染與 latest_diff.json 載入）
