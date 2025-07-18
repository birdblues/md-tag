from dotenv import load_dotenv
import sys
import os
import re

load_dotenv()

from langchain_openai import ChatOpenAI

def process_markdown_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # 객체 생성
        llm = ChatOpenAI(
            temperature=0.0,  # 창의성 (0.0 ~ 2.0)
            model_name="gpt-4.1-mini",  # 모델명
        )
        
        # 기존 프론트매터에서 tags 추출 및 업데이트 요청
        question = f"""다음 마크다운 파일을 처리해주세요:

1. 오탈자, 띄어쓰기, 마크다운 문법 오류를 수정하세요
2. 기존 프론트매터의 구조를 유지하되, tags 필드만 내용에 적합한 해시태그로 업데이트하세요
3. 원본에 "요약" 섹션이 없다면 맨 뒤에 "## 요약" 헤더로 내용 요약을 추가하세요
4. 원본의 전체 구조와 내용을 유지하세요

중요사항:
- 프론트매터는 반드시 다음 형식을 유지하세요:
```
---
created: 기존값
tags: 
  - 태그1
  - 태그2
  - 태그3
source: 기존값
author: 기존값
---
```
- 원본 내용의 구조와 헤더 레벨을 그대로 유지하세요
- 요약은 원본에 없을 경우에만 맨 뒤에 추가하세요

파일 내용:
{content}"""
        
        # 질의
        response = llm.invoke(question)
        processed_content = response.content
        
        # 백틱 코드 블록 제거
        processed_content = re.sub(r'^```\w*\n', '', processed_content, flags=re.MULTILINE)
        processed_content = re.sub(r'\n```$', '', processed_content)
        processed_content = processed_content.strip()
        
        # 출력 파일명 생성 (파일명_fix.md)
        base_name = os.path.splitext(file_path)[0]
        output_file = f"{base_name}_fix.md"
        
        # 수정된 내용을 파일로 저장
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(processed_content)
        
        print(f"처리 완료: {output_file}")
        print("\n--- 처리된 내용 ---")
        print(processed_content)
        
    except FileNotFoundError:
        print(f"오류: 파일 '{file_path}'을 찾을 수 없습니다.")
    except Exception as e:
        print(f"오류: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python main.py <파일경로>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    process_markdown_file(file_path)
