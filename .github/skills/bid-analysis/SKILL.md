---
name: bid-analysis
description: "Analyze government procurement bid data, evaluate relevance, estimate competition, and generate investment recommendations. Use when: analyzing bids, evaluating procurement opportunities, reviewing bid history, generating bid reports, assessing bid priority."
argument-hint: "Describe the bid or analysis you need"
---

# 標案分析專家 (Bid Analysis Skill)

## 目的
分析政府標案資料，評估相關性與競爭態勢，產生投標建議報告。

## 使用時機
- 分析新抓取的標案資料
- 評估某機關的採購歷史
- 比較多筆標案的投標價值
- 產生投標可行性報告

## 流程

### Step 1: 取得標案資料
查看 `./output/preview.html` 或讀取最近一次執行的結果：
```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

### Step 2: 分析標案內容
對每筆標案進行以下分析：

1. **機關背景調查**
   - 查看該機關過往採購記錄
   - 確認是否為長期合作潛力機關
   
2. **標案內容解讀**
   - 從標題和摘要提取關鍵需求
   - 識別技術要求（硬體/軟體/服務）
   
3. **預算合理性評估**
   - 比較同類型案件金額
   - 判斷是否有利潤空間

4. **競爭態勢評估**
   - 根據案件規模推測競爭者數量
   - 識別是否有特殊資格限制

### Step 3: 產生分析報告

輸出格式：

```markdown
## 標案分析報告

### 基本資訊
| 項目 | 內容 |
|------|------|
| 機關 | {organization} |
| 標案 | {title} |
| 金額 | {amount} |
| 日期 | {date} |

### AI 評估
- 教育相關分數：{edu_score}/10
- 資訊相關分數：{it_score}/10
- 優先度：{priority}

### 投標建議
- 建議行動：{recommend}
- 理由：{reason}
- 注意事項：{notes}
```

## 資料來源
- 標案資料：[core/models.py](../../core/models.py) - BidRecord 資料結構
- 過濾邏輯：[core/filters.py](../../core/filters.py) - 關鍵字與分類規則
- AI 分類：[core/ai_classifier.py](../../core/ai_classifier.py) - AI 評分邏輯

## 注意事項
- 分析結果僅供參考，實際投標決策需由業務人員確認
- 金額資料可能未公開或不準確
- 截止日期需要到原始連結確認
