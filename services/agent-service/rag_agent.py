"""
LangGraph 기반 RAG 에이전트
YouTube 콘텐츠를 기반으로 한 지능형 질의응답 시스템
"""

import os
from typing import List, Dict, Any, TypedDict, Annotated
from operator import add
from langchain_openai import ChatOpenAI
from langchain.schema import Document
from langchain.prompts import ChatPromptTemplate
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
import json
import sys


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

        # BGE-M3 임베딩 서버 URL
        self.embedding_server_url = os.getenv('EMBEDDING_SERVER_URL', 'http://embedding-server:8083')

        # Qdrant 클라이언트 초기화
        qdrant_url = os.getenv('QDRANT_URL', 'http://localhost:6333')
        self.qdrant_client = QdrantClient(url=qdrant_url)

        # 그래프 구성
        self.graph = self._build_graph()

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """BGE-M3 임베딩 서버에서 벡터 생성"""
        import requests
        try:
            response = requests.post(
                f"{self.embedding_server_url}/embed",
                json={"texts": texts},
                timeout=30
            )
            if response.status_code == 200:
                return response.json()['embeddings']
            else:
                raise Exception(f"임베딩 서버 오류: {response.status_code}")
        except Exception as e:
            print(f"임베딩 생성 실패: {e}")
            raise

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
        """다층 벡터 검색 노드"""
        query = state["query"]
        print(f"[Search] Query: {query}", file=sys.stderr)

        # 쿼리 임베딩 생성 (BGE-M3 사용)
        try:
            query_embedding = self._get_embeddings([query])[0]
            print(f"[Search] Embedding dimension: {len(query_embedding)}", file=sys.stderr)
        except Exception as e:
            print(f"[Search] Embedding error: {e}", file=sys.stderr)
            raise

        all_results = []

        # 1. 요약 검색 (전체 영상 이해)
        try:
            summary_results = self.qdrant_client.search(
                collection_name="youtube_summaries",
                query_vector=query_embedding,
                limit=3,
                score_threshold=0.5  # BGE-M3에 맞는 threshold
            )
            print(f"[Search] Summary results: {len(summary_results)}")
            for result in summary_results:
                print(f"  - Score: {result.score:.4f}, Title: {result.payload.get('title', 'N/A')}")
                result.payload['search_type'] = 'summary'
                all_results.append(result)
        except Exception as e:
            print(f"[Search] Summary search error: {e}")
            import traceback
            traceback.print_exc()
            pass  # 컬렉션이 없으면 무시

        # 2. 문단 검색 (중간 단위 컨텍스트)
        try:
            paragraph_results = self.qdrant_client.search(
                collection_name="youtube_paragraphs",
                query_vector=query_embedding,
                limit=5,
                score_threshold=0.5
            )
            for result in paragraph_results:
                result.payload['search_type'] = 'paragraph'
                all_results.append(result)
        except Exception as e:
            print(f"[Search] Paragraph search error: {e}", file=sys.stderr)
            pass

        # 3. 세밀한 청크 검색 (기존 방식)
        chunk_results = self.qdrant_client.search(
            collection_name="youtube_content",
            query_vector=query_embedding,
            limit=5,
            score_threshold=0.5
        )
        for result in chunk_results:
            result.payload['search_type'] = 'chunk'
            all_results.append(result)

        # 점수 기준으로 정렬하고 상위 10개 선택
        search_results = sorted(all_results, key=lambda x: x.score, reverse=True)[:10]

        # 검색 결과 처리
        processed_results = []
        for result in search_results:
            payload = result.payload

            # search_type에 따라 다른 필드 사용
            search_type = payload.get('search_type', 'chunk')
            if search_type == 'summary':
                content_text = payload.get('summary', payload.get('text', ''))
            elif search_type == 'paragraph':
                content_text = payload.get('paragraph', payload.get('text', ''))
            else:
                content_text = payload.get('text', '')

            # 디버깅 로그
            print(f"[Process] Type: {search_type}, Score: {result.score:.4f}, Title: {payload.get('title', 'N/A')[:50]}...", file=sys.stderr)
            print(f"[Process] Content length: {len(content_text)}", file=sys.stderr)

            processed_results.append({
                'id': result.id,
                'score': result.score,
                'content': content_text,
                'title': payload.get('title', ''),
                'url': payload.get('url', ''),
                'timestamp_url': payload.get('timestamp_url', ''),  # 타임스탬프 URL 추가
                'start_time': payload.get('start_time'),  # 시작 시간 추가
                'end_time': payload.get('end_time'),  # 종료 시간 추가
                'platform': payload.get('platform', ''),
                'publish_date': payload.get('publish_date', ''),
                'search_type': search_type,
                'metadata': payload
            })

        state["search_results"] = processed_results

        # 검색된 내용을 컨텍스트로 결합 (URL 정보 포함)
        context_parts = []
        for i, result in enumerate(processed_results):
            content = result['content']

            # 컨텐츠가 비어있으면 스킵
            if not content:
                print(f"[Context] Skipping empty content for: {result['title']}", file=sys.stderr)
                continue

            # search_type에 따라 다른 길이 제한
            if result.get('search_type') == 'summary':
                max_length = 300  # 요약은 더 길게
            else:
                max_length = 200

            if len(content) > max_length:
                content = content[:max_length] + "..."

            # 타임스탬프 URL이 있으면 우선 사용, 없으면 일반 URL
            url_to_use = result.get('timestamp_url', result.get('url', ''))

            # 시간 정보 추가
            time_info = ""
            if 'start_time' in result and result['start_time'] is not None:
                minutes = int(result['start_time']) // 60
                seconds = int(result['start_time']) % 60
                time_info = f" [{minutes}:{seconds:02d}]"

            context_parts.append(
                f"[{i+1}. {result['title']}]{time_info}\n{content}\nURL: {url_to_use}\n점수: {result['score']:.3f}"
            )

            print(f"[Context] Added #{i+1}: {result['title'][:30]}... (score: {result['score']:.3f})", file=sys.stderr)

        state["context"] = "\n\n---\n\n".join(context_parts)
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
3. 컨텍스트에 포함된 실제 URL을 사용하세요 (예시 URL을 만들지 마세요)
4. 불확실한 내용은 추측하지 마세요
5. 한국어로 자연스럽고 친근하게 답변하세요
6. 컨텍스트에서 충분한 정보를 찾을 수 없으면 그렇게 말하세요

답변 후에는 **참고 자료** 섹션을 추가하여 컨텍스트에 포함된 실제 YouTube URL들을 제공하세요.
절대 예시 URL(https://www.youtube.com/watch?v=example)을 사용하지 마세요.

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
            # 점수 기준을 낮춤 (0.8 -> 0.55) 그리고 상위 5개만 포함
            if result['score'] > 0.55 and len(sources) < 5:  # 점수 기준 낮추고 개수 제한
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

        # 참고 자료를 답변에 추가
        if sources:
            references = "\n\n### 📚 참고 자료\n"
            for i, source in enumerate(sources, 1):
                # 타임스탬프 URL이 있으면 우선 사용
                link_url = source.get('timestamp_url', source.get('url', ''))
                timestamp = source.get('timestamp', '')

                if timestamp:
                    references += f"{i}. [{source['title']}]({link_url}) - {timestamp}\n"
                else:
                    references += f"{i}. [{source['title']}]({link_url})\n"

            state["answer"] = state["answer"] + references

        return state

    def search_similar_content(
        self,
        query: str,
        filters: Dict = None,
        limit: int = 10
    ) -> List[Dict]:
        """유사 콘텐츠 검색"""
        query_embedding = self._get_embeddings([query])[0]

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
            score_threshold=0.5
        )

        # 결과 정리
        processed_results = []
        for result in results:
            payload = result.payload
            processed_results.append({
                'id': result.id,
                'score': result.score,
                'content': payload.get('text', ''),
                'title': payload.get('title', ''),
                'url': payload.get('url', ''),
                'platform': payload.get('platform', ''),
                'publish_date': payload.get('publish_date', ''),
                'metadata': payload
            })

        return processed_results

    def ask(self, query: str, filters: Dict = None) -> Dict:
        """질문에 대한 답변 생성"""
        print(f"[Ask] Query received: {query}")

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
        print(f"[Ask] Invoking graph with state...")
        result = self.graph.invoke(initial_state)
        print(f"[Ask] Graph execution complete. Found {len(result.get('search_results', []))} results")

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