"""Semantic similarity-based bid recall using sentence embeddings.

使用 sentence-transformers 進行語意相似度計算，
與預定義的 4 大類別描述比對，召回相關標案。
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.models import BidRecord

logger = logging.getLogger("bid-monitor.embedding")


class EmbeddingRecaller:
    """基於 embedding 語意相似度的標案召回器"""
    
    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        top_k: int = 30,
        similarity_threshold: float = 0.62,
        log: Any | None = None,
    ):
        """
        Args:
            model_name: sentence-transformers 模型名稱
            top_k: 召回前 K 個候選
            similarity_threshold: 最低相似度閾值（0-1）
            log: logger 實例
        """
        self.model_name = model_name
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.log = log or logger
        self.model = None
        self._category_embeddings = None
        
    def _ensure_model_loaded(self):
        """延遲載入模型（避免 import 時就載入）"""
        if self.model is not None:
            return
        
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            self.log.info(
                "embedding_model_loaded",
                extra={"model": self.model_name}
            )
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        except Exception as exc:
            self.log.error("embedding_model_load_failed", extra={"error": str(exc)})
            raise
    
    def _build_text(self, record: BidRecord) -> str:
        """拼接標案關鍵字段作為語意輸入"""
        parts = [record.title]
        if record.summary:
            parts.append(record.summary)
        if record.category:
            parts.append(record.category)
        return " ".join(parts).strip()
    
    def encode_bids(self, records: list[BidRecord]) -> np.ndarray:
        """將標案轉為 embedding vectors"""
        self._ensure_model_loaded()
        texts = [self._build_text(r) for r in records]
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings
    
    def encode_category_descriptions(self, category_texts: list[str]) -> np.ndarray:
        """將類別描述轉為 embedding vectors（cached）"""
        if self._category_embeddings is not None:
            return self._category_embeddings
        
        self._ensure_model_loaded()
        self._category_embeddings = self.model.encode(
            category_texts,
            convert_to_numpy=True,
            show_progress_bar=False
        )
        self.log.info(
            "category_embeddings_encoded",
            extra={"count": len(category_texts)}
        )
        return self._category_embeddings
    
    def recall_by_category(
        self,
        candidates: list[BidRecord],
        category_texts: list[str],
    ) -> list[BidRecord]:
        """
        基於與 4 大類描述的相似度，召回 top-K 候選。
        
        Args:
            candidates: 候選標案列表（已通過 keyword filter）
            category_texts: 4 大類別的標準描述文本
        
        Returns:
            召回的標案列表（按相似度排序）
        """
        if not candidates:
            return []
        
        try:
            # 編碼候選標案
            candidate_embeddings = self.encode_bids(candidates)
            
            # 編碼類別描述（cached）
            category_embeddings = self.encode_category_descriptions(category_texts)
            
            # 計算 cosine similarity
            from sklearn.metrics.pairwise import cosine_similarity
            scores = cosine_similarity(candidate_embeddings, category_embeddings)
            
            # 每個候選取與所有類別的最高相似度
            max_scores = scores.max(axis=1)

            # 標記每個候選的最佳匹配類別
            best_categories = scores.argmax(axis=1)
            
            # 按相似度排序並過濾
            ranked = []
            for i, record in enumerate(candidates):
                score = float(max_scores[i])
                if score >= self.similarity_threshold:
                    # 將相似度分數附加到 record metadata
                    if not hasattr(record, 'metadata') or record.metadata is None:
                        record.metadata = {}
                    record.metadata["embedding_similarity"] = score
                    best_category_idx = int(best_categories[i])
                    record.metadata["embedding_best_category_idx"] = best_category_idx
                    try:
                        from core.embedding_categories import get_category_by_index
                        best_category = get_category_by_index(best_category_idx)
                        if best_category:
                            record.metadata["embedding_best_category"] = best_category.name
                    except Exception:
                        pass
                    ranked.append((record, score))
            
            # 按相似度降序排序
            ranked.sort(key=lambda x: x[1], reverse=True)
            
            # 取 top-K
            result = [rec for rec, _ in ranked[:self.top_k]]
            
            self.log.info(
                "embedding_recall_done",
                extra={
                    "candidates": len(candidates),
                    "recalled": len(result),
                    "threshold": self.similarity_threshold,
                    "top_k": self.top_k,
                }
            )
            
            return result
            
        except Exception as exc:
            self.log.error("embedding_recall_failed", extra={"error": str(exc)})
            # Graceful fallback: 返回原始候選集
            return candidates


def recall_bids_with_embedding(
    candidates: list[BidRecord],
    *,
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
    top_k: int = 30,
    similarity_threshold: float = 0.62,
    log: Any | None = None,
) -> list[BidRecord]:
    """
    便利函式：使用 embedding 召回相關標案。
    
    Args:
        candidates: 候選標案列表
        model_name: sentence-transformers 模型
        top_k: 召回前 K 個
        similarity_threshold: 最低相似度
        log: logger 實例
    
    Returns:
        召回的標案列表
    """
    from core.embedding_categories import get_category_texts
    
    recaller = EmbeddingRecaller(
        model_name=model_name,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        log=log,
    )
    
    category_texts = get_category_texts()
    return recaller.recall_by_category(candidates, category_texts)
