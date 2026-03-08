import json
import re

import httpx

from rag_mvp.config import KIMI_API_KEY, KIMI_AUTH_TOKEN, KIMI_BASE_URL, KIMI_MODEL
from rag_mvp.schemas import GraphFact, SourceHit


class KimiClientError(RuntimeError):
    """Raised when the Kimi API request fails."""


class KimiClient:
    def __init__(self) -> None:
        self.base_url = KIMI_BASE_URL.rstrip("/")
        self.api_key = KIMI_API_KEY
        self.auth_token = KIMI_AUTH_TOKEN
        self.model = KIMI_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def expand_query(self, question: str) -> str:
        system_prompt = (
            "You rewrite academic search queries for literature retrieval. "
            "Translate Chinese or mixed-language questions into concise English search keywords. "
            "Return only a short keyword query, with no explanation."
        )
        return await self._send_message(system_prompt, question, max_tokens=80)

    async def extract_document_graph(self, file_name: str, document_text: str) -> dict:
        system_prompt = (
            "You extract an academic knowledge graph from paper text. "
            "Return valid JSON only with keys: summary, entities, relationships. "
            "Entity types must be chosen from Method, Model, Crop, Sensor, Dataset, Task, Metric, Region, Institution, Concept. "
            "Each entity item must have name and type. "
            "Each relationship item must have source, target, type, evidence. "
            "Relationship types should be short uppercase strings like USES_DATA, APPLIES_TO, OUTPERFORMS, EVALUATED_BY, RELATED_TO."
        )
        user_prompt = (
            f"File: {file_name}\n"
            "Extract the most important entities and explicit relationships from the following paper text. "
            "Keep at most 18 entities and 24 relationships. "
            "Only include relationships that are supported by the text.\n\n"
            f"{document_text[:12000]}"
        )
        raw = await self._send_message(system_prompt, user_prompt, max_tokens=1800)
        return self._parse_json_object(raw)

    async def answer_question(
        self,
        question: str,
        source_hits: list[SourceHit],
        graph_facts: list[GraphFact] | None = None,
    ) -> str:
        context_blocks = []
        for hit in source_hits:
            context_blocks.append(
                "\n".join(
                    [
                        f"[S{hit.rank}] 文件: {hit.file_name}",
                        f"页码: {hit.page_number}",
                        f"相关度: {hit.score}",
                        f"内容片段: {hit.preview}",
                    ]
                )
            )

        if not context_blocks:
            raise KimiClientError("No retrieved context was provided to the model")

        graph_blocks = []
        for fact in graph_facts or []:
            graph_blocks.append(
                f"[G{fact.rank}] {fact.source} ({fact.source_type}) -[{fact.relation}]-> {fact.target} ({fact.target_type}) | 文档: {fact.document} | 证据: {fact.evidence}"
            )

        system_prompt = (
            "你是一个面向农作物分类论文检索的学术助理。"
            "只能依据给定资料作答，不要编造。"
            "回答时优先给出简洁结论，再给出依据。"
            "向量检索来源使用 [S1] 这种格式引用；图谱事实使用 [G1] 这种格式引用。"
            "如果资料不足，请明确说明‘根据当前已检索到的论文片段，暂时无法确定’。"
        )
        prompt_parts = [
            "以下是检索到的向量资料片段：",
            "\n\n".join(context_blocks),
        ]
        if graph_blocks:
            prompt_parts.extend([
                "以下是检索到的图谱关系：",
                "\n".join(graph_blocks),
            ])
        prompt_parts.extend([
            f"用户问题：{question}",
            "请基于上面的资料回答，并保留来源编号。",
        ])
        user_prompt = "\n\n".join(prompt_parts)
        return await self._send_message(system_prompt, user_prompt, max_tokens=1200)

    async def _send_message(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        if not self.is_configured:
            raise KimiClientError("Kimi API credentials are not configured")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self.auth_token:
            headers["authorization"] = f"Bearer {self.auth_token}"

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers=headers,
                    json=payload,
                )
        except Exception as exc:
            raise KimiClientError(f"Kimi request failed: {exc}") from exc

        if response.status_code >= 400:
            raise KimiClientError(f"Kimi API returned {response.status_code}: {response.text[:300]}")

        body = response.json()
        text_parts = [
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        ]
        answer = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
        if not answer:
            raise KimiClientError("Kimi API returned an empty answer")
        return answer

    def _parse_json_object(self, raw: str) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if not match:
                raise KimiClientError("Kimi did not return valid JSON for graph extraction")
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise KimiClientError("Kimi returned malformed JSON for graph extraction") from exc
