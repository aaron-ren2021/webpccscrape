#!/bin/bash
# 啟動 Ollama 服務並運行本地 LLM 篩選測試

set -e

echo "=================================="
echo "  Local LLM 服務啟動腳本"
echo "=================================="

# 檢查 Ollama 是否已安裝
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama 未安裝"
    echo "請執行: curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi

echo "✅ Ollama 已安裝: $(which ollama)"

# 檢查模型是否已下載
if ! ollama list | grep -q "qwen2.5:3b"; then
    echo "⏳ 下載 qwen2.5:3b 模型..."
    ollama pull qwen2.5:3b
    echo "✅ 模型下載完成"
else
    echo "✅ qwen2.5:3b 模型已存在"
fi

# 停止現有 Ollama 服務
pkill -f "ollama serve" 2>/dev/null || true
sleep 1

# 啟動 Ollama 服務
echo "⏳ 啟動 Ollama 服務..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!

# 等待服務啟動
sleep 3

# 檢查服務是否正常運行
if ps -p $OLLAMA_PID > /dev/null; then
    echo "✅ Ollama 服務已啟動 (PID: $OLLAMA_PID)"
    echo "   日誌檔案: /tmp/ollama.log"
else
    echo "❌ Ollama 服務啟動失敗"
    echo "查看日誌: tail -f /tmp/ollama.log"
    exit 1
fi

# 測試連接
echo "⏳ 測試 Ollama API..."
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "✅ Ollama API 正常運作"
else
    echo "❌ Ollama API 無法連接"
    exit 1
fi

echo ""
echo "=================================="
echo "  服務啟動成功！"
echo "=================================="
echo ""
echo "測試指令："
echo "  1. 測試 Local LLM:"
echo "     python test_local_llm.py"
echo ""
echo "  2. 測試完整 Pipeline:"
echo "     python run_local.py --no-send --preview-html ./output/preview.html"
echo ""
echo "停止服務："
echo "  pkill -f 'ollama serve'"
echo ""
echo "查看日誌："
echo "  tail -f /tmp/ollama.log"
echo ""
