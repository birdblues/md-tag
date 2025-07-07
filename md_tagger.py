#!/usr/bin/env python3
"""
마크다운 파일 태그 자동 생성기

Ollama의 qwen3:30b-32k-0.0 모델을 사용하여 마크다운 파일을 분석하고
프론트매터에 태그를 자동으로 추가하는 스크립트입니다.
"""

import os
import re
import yaml
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import ollama
import tiktoken

class MarkdownTagger:
    def __init__(self, model_name: str = "qwen3:30b-32k-0.0", max_tokens: int = 4096, chunk_size: int = 2048):
        """
        마크다운 태거 초기화
        
        Args:
            model_name: Ollama 모델 이름
            max_tokens: 모델 최대 토큰 수
            chunk_size: 텍스트 청킹 크기
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.chunk_size = chunk_size
        self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 기본 인코딩
        
    def count_tokens(self, text: str) -> int:
        """텍스트의 토큰 수를 계산합니다."""
        return len(self.encoding.encode(text))
    
    def split_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """텍스트를 청크 크기에 맞게 효율적으로 분할합니다."""
        if text is None:
            return []
        
        chunks = []
        current_chunk = ""
        
        # 헤더 패턴으로 텍스트를 섹션으로 분할 (# ## ### #### ##### ######)
        header_pattern = r'^(#{1,6})\s+(.+)$'
        lines = text.split('\n')
        
        for line in lines:
            test_chunk = current_chunk + line + "\n"
            
            # 청크 크기 확인
            if self.count_tokens(test_chunk) <= chunk_size:
                current_chunk = test_chunk
            else:
                # 현재 청크가 비어있지 않으면 저장
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # 헤더인지 확인
                header_match = re.match(header_pattern, line)
                if header_match:
                    # 헤더로 새 청크 시작
                    current_chunk = line + "\n"
                else:
                    # 일반 라인으로 새 청크 시작
                    current_chunk = line + "\n"
                
                # 단일 라인이 청크 크기를 초과하는 경우 강제로 분할
                if self.count_tokens(current_chunk) > chunk_size:
                    # 문장 단위로 분할 시도
                    sentences = line.split('. ')
                    current_chunk = ""
                    for sentence in sentences:
                        test_sentence = current_chunk + sentence + ". "
                        if self.count_tokens(test_sentence) <= chunk_size:
                            current_chunk = test_sentence
                        else:
                            if current_chunk.strip():
                                chunks.append(current_chunk.strip())
                            current_chunk = sentence + ". "
        
        # 마지막 청크 처리
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    
    def parse_markdown_file(self, file_path: str) -> Tuple[Optional[Dict], str]:
        """
        마크다운 파일을 파싱하여 프론트매터와 내용을 분리합니다.
        
        Returns:
            Tuple[Dict, str]: (프론트매터, 마크다운 내용)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # 프론트매터 분리
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter_str = parts[1]
                    markdown_content = parts[2].strip()
                    
                    try:
                        frontmatter = yaml.safe_load(frontmatter_str)
                        if frontmatter is None:
                            frontmatter = {}
                    except yaml.YAMLError:
                        frontmatter = {}
                else:
                    frontmatter = {}
                    markdown_content = content
            else:
                frontmatter = {}
                markdown_content = content
            
            return frontmatter, markdown_content
            
        except Exception as e:
            print(f"파일 읽기 오류: {e}")
            return None, ""
    
    def generate_tags_for_chunk(self, chunk: str) -> List[str]:
        """
        청크에 대해 Ollama API를 호출하여 태그를 생성합니다.
        """
        prompt = f"""다음 텍스트를 분석하여 먼저 요약본을 만들고, 그 요약본을 바탕으로 해시태그를 생성해주세요.

1단계: 텍스트 요약
이 텍스트의 핵심 내용을 3-5문장으로 요약해주세요.

2단계: 해시태그 생성  
요약본을 바탕으로 적절한 해시태그를 생성해주세요. 해시태그는 반드시 한글로 작성해주세요.
각 해시태그는 한 줄에 하나씩 작성해주세요.
태그에는 '#', '_' 기호나 띄어쓰기를 넣지 마세요. 모든 단어를 붙여서 작성해주세요.

텍스트:
{chunk}

응답 형식:
**요약:**
[여기에 요약 내용 작성]

**해시태그:**
머신러닝
데이터분석
인공지능
딥러닝
파이썬프로그래밍"""
        
        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.0,
                    "max_tokens": self.max_tokens,
                    "top_p": 0.9
                }
            )
            
            # 응답에서 태그 추출
            tags = []
            response_text = response['response']
            
            # XML 태그와 내용 모두 제거 (예: <think>내용</think>, <answer>내용</answer> 등)
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            response_text = re.sub(r'<answer>.*?</answer>', '', response_text, flags=re.DOTALL)
            response_text = re.sub(r'<reasoning>.*?</reasoning>', '', response_text, flags=re.DOTALL)
            # 남은 단순 태그도 제거
            response_text = re.sub(r'<[^>]+>', '', response_text)
            
            # **해시태그:** 섹션 찾기
            hashtag_section = ""
            if "**해시태그:**" in response_text:
                hashtag_section = response_text.split("**해시태그:**")[1]
            elif "해시태그:" in response_text:
                hashtag_section = response_text.split("해시태그:")[1]
            else:
                # 해시태그 섹션을 찾지 못한 경우 전체 텍스트에서 추출
                hashtag_section = response_text
            
            # 줄바꿈으로 분리하여 태그 추출
            lines = hashtag_section.strip().split('\n')
            for line in lines:
                line = line.strip()
                # # 기호가 있으면 제거
                if line.startswith('#'):
                    line = line[1:].strip()
                # _ 기호와 공백 제거
                line = line.replace('_', '').replace(' ', '')
                # 빈 줄이 아니고 한글이 포함된 경우만 태그로 인정
                if line and len(line) > 1 and any('\uac00' <= char <= '\ud7a3' for char in line):
                    tags.append(line)
            
            return tags
            
        except Exception as e:
            print(f"태그 생성 오류: {e}")
            return []
    
    def merge_and_deduplicate_tags(self, all_tags: List[List[str]]) -> List[str]:
        """
        모든 청크에서 생성된 태그를 병합하고 중복을 제거하여 태그를 선택합니다.
        """
        if not all_tags:
            return []
        
        # 모든 태그를 평면화하고 빈도수 계산
        tag_counts = {}
        for chunk_tags in all_tags:
            if chunk_tags:  # None 체크 추가
                for tag in chunk_tags:
                    if tag:  # 빈 문자열 체크 추가
                        tag_lower = tag.lower()
                        if tag_lower in tag_counts:
                            tag_counts[tag_lower] += 1
                        else:
                            tag_counts[tag_lower] = 1
        
        # 빈도수 기준으로 정렬하고 상위 10개 선택
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        print(f"{sorted_tags}")
        
        # 원본 형태로 복원 (첫 번째 등장한 형태 사용)
        final_tags = []
        for tag_lower, count in sorted_tags:
            # 원본 태그 찾기
            for chunk_tags in all_tags:
                if chunk_tags:  # None 체크 추가
                    for original_tag in chunk_tags:
                        if original_tag and original_tag.lower() == tag_lower:
                            final_tags.append(original_tag)
                            break
                    if len(final_tags) > len(sorted_tags[:len(final_tags)]) - 1:
                        break
           
        return final_tags
    
    def update_frontmatter_with_tags(self, frontmatter: Dict, tags: List[str]) -> Dict:
        """
        프론트매터에 태그를 추가합니다.
        """
        if not frontmatter:
            frontmatter = {}
        
        # 기존 태그와 새 태그 병합
        existing_tags = frontmatter.get('tags', [])
        if isinstance(existing_tags, str):
            existing_tags = [existing_tags]
        
        # 중복 제거하며 병합
        all_tags = list(existing_tags) + tags
        unique_tags = []
        seen = set()
        
        for tag in all_tags:
            print(f"태그 처리 중: {tag}")
            tag_lower = tag.lower()
            if tag_lower not in seen:
                unique_tags.append(tag)
                seen.add(tag_lower)
        
        frontmatter['tags'] = unique_tags
        
        return frontmatter
    
    def find_markdown_files(self, directory_path: str) -> List[str]:
        """
        디렉토리에서 모든 마크다운 파일을 재귀적으로 찾습니다.
        
        Args:
            directory_path: 검색할 디렉토리 경로
            
        Returns:
            List[str]: 찾은 마크다운 파일 경로 목록
        """
        markdown_files = []
        try:
            path = Path(directory_path)
            if path.is_dir():
                # .md 및 .markdown 파일을 재귀적으로 찾기
                for pattern in ['**/*.md', '**/*.markdown']:
                    markdown_files.extend(path.glob(pattern))
                # Path 객체를 문자열로 변환
                markdown_files = [str(f) for f in markdown_files]
            else:
                print(f"경고: {directory_path}는 디렉토리가 아닙니다.")
        except Exception as e:
            print(f"마크다운 파일 검색 오류: {e}")
        
        return sorted(markdown_files)
    
    def save_markdown_file(self, file_path: str, frontmatter: Dict, content: str):
        """
        프론트매터와 내용을 마크다운 파일로 저장합니다.
        """
        try:
            # 프론트매터를 YAML 형식으로 변환
            frontmatter_str = yaml.dump(frontmatter, default_flow_style=False, 
                                      allow_unicode=True, sort_keys=False)
            
            # 파일 내용 구성
            full_content = f"---\n{frontmatter_str}---\n\n{content}"
            
            # 파일 저장
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(full_content)
            
            print(f"파일 저장 완료: {file_path}")
            
        except Exception as e:
            print(f"파일 저장 오류: {e}")
    
    def process_markdown_file(self, file_path: str) -> bool:
        """
        마크다운 파일을 처리하여 태그를 추가합니다.
        """
        print(f"\n파일 처리 시작: {file_path}")
        
        try:
            # 파일 파싱
            parse_result = self.parse_markdown_file(file_path)
            if parse_result is None or len(parse_result) != 2:
                print("파일 파싱 실패")
                return False
            
            frontmatter, content = parse_result
            if frontmatter is None:
                print("프론트매터 파싱 실패")
                return False
            
            if content is None:
                print("콘텐츠가 비어있습니다")
                content = ""
            
            # 텍스트 청킹
            chunks = self.split_into_chunks(content, self.chunk_size)
            if chunks is None:
                print("청킹 실패")
                return False
            print(f"텍스트를 {len(chunks)}개 청크로 분할(청크 크기: {self.chunk_size} 토큰)")
            
            # 각 청크에 대해 태그 생성
            all_tags = []
            for i, chunk in enumerate(chunks):
                print(f"청크 {i+1}/{len(chunks)} 처리 중...({self.count_tokens(chunk)} 토큰)")
                chunk_tags = self.generate_tags_for_chunk(chunk)
                if chunk_tags:  # None 체크 추가
                    all_tags.append(chunk_tags)
                    print(f"생성된 태그: {chunk_tags}")
                else:
                    print("태그 생성 실패 또는 빈 결과")
            
            # 태그 병합 및 중복 제거
            if all_tags:  # 빈 리스트 체크 추가
                final_tags = self.merge_and_deduplicate_tags(all_tags)
                print(f"최종 태그 ({len(final_tags)}개): {final_tags}")
            else:
                print("생성된 태그가 없습니다.")
                final_tags = []
            
            # 프론트매터 업데이트
            updated_frontmatter = self.update_frontmatter_with_tags(frontmatter, final_tags)
            
            # 파일 저장
            self.save_markdown_file(file_path, updated_frontmatter, content)
            
            return True
            
        except Exception as e:
            print(f"파일 처리 오류: {e}")
            return False
    
    def process_directory(self, directory_path: str) -> Dict[str, bool]:
        """
        디렉토리의 모든 마크다운 파일을 처리합니다.
        
        Args:
            directory_path: 처리할 디렉토리 경로
            
        Returns:
            Dict[str, bool]: 파일별 처리 결과 (파일경로: 성공여부)
        """
        print(f"\n디렉토리 처리 시작: {directory_path}")
        
        # 마크다운 파일 찾기
        markdown_files = self.find_markdown_files(directory_path)
        if not markdown_files:
            print("처리할 마크다운 파일이 없습니다.")
            return {}
        
        print(f"총 {len(markdown_files)}개의 마크다운 파일을 찾았습니다.")
        
        results = {}
        success_count = 0
        
        for i, file_path in enumerate(markdown_files, 1):
            print(f"\n[{i}/{len(markdown_files)}] 처리 중...")
            try:
                success = self.process_markdown_file(file_path)
                results[file_path] = success
                if success:
                    success_count += 1
                    print(f"✅ 성공: {file_path}")
                else:
                    print(f"❌ 실패: {file_path}")
            except Exception as e:
                print(f"❌ 오류: {file_path} - {e}")
                results[file_path] = False
        
        print(f"\n=== 처리 완료 ===")
        print(f"총 파일: {len(markdown_files)}개")
        print(f"성공: {success_count}개")
        print(f"실패: {len(markdown_files) - success_count}개")
        
        return results


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(
        description='마크다운 파일에 자동으로 태그를 추가합니다.'
    )
    parser.add_argument(
        'path',
        help='처리할 마크다운 파일 또는 디렉토리 경로'
    )
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='디렉토리의 모든 마크다운 파일을 재귀적으로 처리'
    )
    parser.add_argument(
        '--model',
        default='qwen3:30b-32k-0.0',
        help='사용할 Ollama 모델 (기본값: qwen3:30b-32k-0.0)'
    )
    parser.add_argument(
        '--max-tokens',
        type=int,
        default=32768,
        help='모델 최대 토큰 수 (기본값: 32768)'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=30000,
        help='청크 크기 (기본값: 30000)'
    )
    
    args = parser.parse_args()
    
    # 경로 존재 확인
    if not os.path.exists(args.path):
        print(f"오류: 경로를 찾을 수 없습니다: {args.path}")
        return
    
    # 태거 초기화
    tagger = MarkdownTagger(
        model_name=args.model,
        max_tokens=args.max_tokens,
        chunk_size=args.chunk_size
    )
    
    try:
        if args.all or os.path.isdir(args.path):
            # 디렉토리 처리
            if not os.path.isdir(args.path):
                print(f"오류: -a 옵션을 사용하려면 디렉토리 경로를 지정해야 합니다: {args.path}")
                return
            
            results = tagger.process_directory(args.path)
            if results:
                success_count = sum(1 for success in results.values() if success)
                if success_count == len(results):
                    print("\n✅ 모든 파일 처리 완료!")
                elif success_count > 0:
                    print(f"\n⚠️  부분적 완료: {success_count}/{len(results)}개 파일 성공")
                else:
                    print("\n❌ 모든 파일 처리 실패")
            else:
                print("\n❌ 처리할 파일이 없습니다")
        else:
            # 단일 파일 처리
            if not os.path.isfile(args.path):
                print(f"오류: 파일이 아닙니다: {args.path}")
                return
            
            success = tagger.process_markdown_file(args.path)
            if success:
                print("\n✅ 태그 추가 완료!")
            else:
                print("\n❌ 태그 추가 실패")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")


if __name__ == "__main__":
    main()