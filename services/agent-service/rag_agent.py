"""
LangGraph 기반 RAG 에이전트
YouTube 콘텐츠를 기반으로 한 지능형 질의응답 시스템
"""

import os
from typing import List, Dict, Any, TypedDict, Annotated
from operator import add
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import Document
from langchain.prompts import ChatPromptTemplate
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
import json


class AgentState(TypedDict):
    """에이전트 상태 정의"""
    messages: Annotated[List[BaseMessage], add_messages]
    query: str
    search_results: List[Dict]
    context: str
    answer: str
    metadata: Dict[str, Any]


class YouTubeRAGAgent:
    """YouTube RAG 에이전트"""

    def __init__(self):
        # LLM 초기화
        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=0.1,
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )

        # 임베딩 모델 초기화
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )

        # Qdrant 클라이언트 초기화
        qdrant_url = os.getenv('QDRANT_URL', 'http://localhost:6333')
        self.qdrant_client = QdrantClient(url=qdrant_url)

        # 그래프 구성
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """LangGraph 구성"""
        workflow = StateGraph(AgentState)

        # 노드 추가
        workflow.add_node("search", self._search_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("refine", self._refine_node)

        # 엣지 추가
        workflow.set_entry_point("search")
        workflow.add_edge("search", "generate")
        workflow.add_edge("generate", "refine")
        workflow.add_edge("refine", END)

        return workflow.compile()

    def _search_node(self, state: AgentState) -> AgentState:
        """벡터 검색 노드"""
        query = state["query"]

        # 쿼리 임베딩 생성
        query_embedding = self.embeddings.embed_query(query)

        # 벡터 검색 수행
        search_results = self.qdrant_client.search(
            collection_name="youtube_content",
            query_vector=query_embedding,
            limit=3,
            score_threshold=0.7
        )

        # 검색 결과 처리
        processed_results = []
        for result in search_results:
            payload = result.payload
            processed_results.append({
                'id': result.id,
                'score': result.score,
                'content': payload.get('chunk_text', ''),
                'title': payload.get('title', ''),
                'url': payload.get('url', ''),
                'platform': payload.get('platform', ''),
                'publish_date': payload.get('publish_date', ''),
                'metadata': payload
            })

        state["search_results"] = processed_results

        # 검색된 내용을 컨텍스트로 결합 (길이 제한)
        context_parts = []
        for result in processed_results:
            content = result['content']
            # 각 결과를 200자로 제한
            if len(content) > 200:
                content = content[:200] + "..."
            context_parts.append(
                f"[{result['title']}] {content}"
            )

        state["context"] = "\n\n".join(context_parts)
        return state

    def _generate_node(self, state: AgentState) -> AgentState:
        """답변 생성 노드"""
        query = state["query"]
        context = state["context"]

        # 프롬프트 템플릿
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
당신은 YouTube 콘텐츠 전문가입니다. 사용자의 질문에 대해 제공된 YouTube 콘텐츠를 기반으로 정확하고 유용한 답변을 제공하세요.

답변 시 다음 사항을 고려하세요:
1. 제공된 컨텍스트만을 기반으로 답변하세요
2. 답변에 관련 YouTube 동영상 제목과 출처를 명시하세요
3. 가능한 경우 해당 내용의 정확한 시간대로 이동할 수 있는 링크를 포함하세요
4. 불확실한 내용은 추측하지 마세요
5. 한국어로 자연스럽고 친근하게 답변하세요
6. 컨텍스트에서 충분한 정보를 찾을 수 없으면 그렇게 말하세요

답변 후에는 **참고 자료** 섹션을 추가하여 관련 링크들을 제공하세요.

컨텍스트:
{context}
            """),
            ("human", "{query}")
        ])

        # 답변 생성
        chain = prompt | self.llm
        response = chain.invoke({
            "query": query,
            "context": context
        })

        state["answer"] = response.content
        return state

    def _refine_node(self, state: AgentState) -> AgentState:
        """답변 개선 노드"""
        query = state["query"]
        answer = state["answer"]
        search_results = state["search_results"]

        # 메타데이터 생성 (타임스탬프 링크 포함)
        sources = []
        platforms = set()
        for result in search_results:
            if result['score'] > 0.8:  # 높은 점수의 결과만 출처로 포함
                source_info = {
                    'title': result['title'],
                    'url': result['url'],
                    'platform': result['platform'],
                    'score': result['score']
                }

                # 타임스탬프 URL 추가 (있는 경우)
                if 'timestamp_url' in result and result['timestamp_url']:
                    source_info['timestamp_url'] = result['timestamp_url']
                    # 시간 정보 추가
                    if 'start_time' in result and result['start_time'] is not None:
                        minutes = int(result['start_time']) // 60
                        seconds = int(result['start_time']) % 60
                        source_info['timestamp'] = f"{minutes}:{seconds:02d}"

                sources.append(source_info)
                platforms.add(result['platform'])

        state["metadata"] = {
            "sources": sources,
            "platforms": list(platforms),
            "search_count": len(search_results),
            "high_score_count": len([r for r in search_results if r['score'] > 0.8])
        }

        return state

    def search_similar_content(
        self,
        query: str,
        filters: Dict = None,
        limit: int = 10
    ) -> List[Dict]:
        """유사 콘텐츠 검색"""
        query_embedding = self.embeddings.embed_query(query)

        # 필터 구성
        search_filter = None
        if filters:
            conditions = []
            if filters.get('platform'):
                conditions.append(
                    FieldCondition(
                        key="platform",
                        match=MatchValue(value=filters['platform'])
                    )
                )
            if filters.get('language'):
                conditions.append(
                    FieldCondition(
                        key="language",
                        match=MatchValue(value=filters['language'])
                    )
                )

            if conditions:
                search_filter = Filter(must=conditions)

        # 검색 수행
        results = self.qdrant_client.search(
            collection_name="youtube_content",
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=limit,
            score_threshold=0.6
        )

        # 결과 정리
        processed_results = []
        for result in results:
            payload = result.payload
            processed_results.append({
                'id': result.id,
                'score': result.score,
                'content': payload.get('chunk_text', ''),
                'title': payload.get('title', ''),
                'url': payload.get('url', ''),
                'platform': payload.get('platform', ''),
                'publish_date': payload.get('publish_date', ''),
                'metadata': payload
            })

        return processed_results

    def ask(self, query: str, filters: Dict = None) -> Dict:
        """질문에 대한 답변 생성"""
        # 초기 상태 설정
        initial_state = {
            "messages": [],
            "query": query,
            "search_results": [],
            "context": "",
            "answer": "",
            "metadata": {}
        }

        # 필터가 있으면 검색에 적용 (향후 확장을 위해 추가)
        if filters:
            initial_state["filters"] = filters

        # 그래프 실행
        result = self.graph.invoke(initial_state)

        return {
            "query": query,
            "answer": result["answer"],
            "sources": result["metadata"].get("sources", []),
            "platforms": result["metadata"].get("platforms", []),
            "search_stats": {
                "total_results": result["metadata"].get("search_count", 0),
                "high_score_results": result["metadata"].get("high_score_count", 0)
            }
        }

    def get_trending_topics(self, platform: str = None, limit: int = 10) -> List[Dict]:
        """인기 토픽 조회 (최근 콘텐츠 기반)"""
        # 간단한 구현: 최근 벡터들의 메타데이터를 기반으로 인기 토픽 추출
        # 실제로는 더 복잡한 분석이 필요할 수 있음

        search_filter = None
        if platform:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="platform",
                        match=MatchValue(value=platform)
                    )
                ]
            )

        # 랜덤 샘플링으로 최근 콘텐츠 조회
        results = self.qdrant_client.search(
            collection_name="youtube_content",
            query_vector=[0.0] * 1536,  # 더미 벡터
            query_filter=search_filter,
            limit=limit * 2
        )

        # 제목별 그룹화 및 정리
        topics = {}
        for result in results:
            payload = result.payload
            title = payload.get('title', '')
            if title and title not in topics:
                topics[title] = {
                    'title': title,
                    'url': payload.get('url', ''),
                    'platform': payload.get('platform', ''),
                    'publish_date': payload.get('publish_date', ''),
                    'preview': payload.get('chunk_text', '')[:200] + '...'
                }

        return list(topics.values())[:limit]