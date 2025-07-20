import subprocess
import os
from pathlib import Path
from typing import Dict, List, Any
import requests
import re

# Ollama는 환경변수나 .env 파일이 필요하지 않습니다


class MarkdownLinter:
    """markdownlint-cli2를 사용한 마크다운 린터"""
    
    def __init__(self):
        self.lint_results = []
    
    def lint_file(self, file_path: str) -> List[Dict[str, Any]]:
        """마크다운 파일을 lint하고 결과를 파싱하여 반환"""
        try:
            # markdownlint-cli2 실행
            result = subprocess.run(
                ['markdownlint-cli2', file_path],
                capture_output=True,
                text=True,
                check=False
            )
            
            # print(f"Lint 결과: {result.stderr}")
            
            lint_issues = []
            if result.stderr:  # markdownlint-cli2는 에러를 stderr로 출력
                lines = result.stderr.strip().split('\n')
                for line in lines:
                    if line.strip() and ':' in line:
                        # markdownlint-cli2 출력 파싱
                        # 형식: tests/07월 11일 월가소식.md:8 MD022/blanks-around-headings Headings should be...
                        # 또는: tests/07월 11일 월가소식.md:8:1 MD007/ul-indent Unordered list indentation...
                        
                        try:
                            # 정규식을 사용하여 파싱 (파일명에 공백이 있어도 처리)
                            # 패턴: 파일경로:라인번호[:컬럼] MD규칙/설명 나머지설명
                            pattern = r'^(.+?):(\d+)(?::(\d+))? (MD\d+(?:/[\w-]+)?) (.+)$'
                            match = re.match(pattern, line)
                            
                            if match:
                                file_name = match.group(1)
                                line_num = int(match.group(2))
                                column = int(match.group(3)) if match.group(3) else 0
                                rule = match.group(4)
                                description = match.group(5)
                                
                                # 파일 경로가 실제 파일과 일치하는지 확인
                                if file_name == file_path or file_name.endswith(os.path.basename(file_path)):
                                    lint_issues.append({
                                        'file': file_name,
                                        'line': line_num,
                                        'column': column,
                                        'rule': rule,
                                        'description': description
                                    })
                            
                        except (ValueError, IndexError) as e:
                            # 파싱 실패한 라인은 건너뛰기
                            continue
            
            return lint_issues
            
        except subprocess.CalledProcessError as e:
            print(f"Lint 실행 중 오류 발생: {e}")
            return []
        except Exception as e:
            print(f"예상치 못한 오류: {e}")
            return []


class MarkdownFixer:
    """Ollama를 사용한 마크다운 수정기"""
    
    def __init__(self, model_name: str = "qwen3:30b-32k-0.0", ollama_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.ollama_url = ollama_url
        
        self.system_prompt = """당신은 마크다운 문서를 개선하는 전문가입니다.
주어진 마크다운 내용과 markdownlint-cli2의 lint 결과를 바탕으로 다음 작업을 수행해주세요:

1. lint에서 발견된 문제점들을 수정
   - MD007: 목록 들여쓰기를 0칸 (최상위), 2칸 단위 (중첩)로 수정
   - MD032: 목록 앞뒤에 빈 줄 추가
   - MD022: 헤딩 아래에 빈 줄 추가
   - MD036: 강조 문법(◼︎, **text**) 대신 적절한 헤딩 레벨 사용
   - MD009: 줄 끝 공백 제거
   - MD029: 순서 목록 번호 형식 통일
   - MD037: 강조 마커 내부 공백 제거

2. 마크다운 문법과 스타일 개선
3. 가독성 향상
4. 일관된 포맷팅 적용
5. 띄어쓰기, 오탈자 수정

6. 테이블 구조 수정
   - 헤더 행과 내용 행의 컬럼 수가 일치하도록 수정
   - 비교 테이블에서 첫 번째 헤더 컬럼이 생략된 경우, 빈 컬럼(|)을 추가
   - 구분자 행(---|---|---)의 컬럼 수를 실제 데이터 컬럼 수와 맞춤
   - 예시: "| Vanilla RAG| Agentic RAG" → "| | Vanilla RAG| Agentic RAG"
   - 예시: "---|---|---" (3개 컬럼)으로 구분자 수정

수정된 마크다운만 반환하고, 다른 설명은 추가하지 마세요.
원본의 의미와 내용은 변경하지 말고, 형식과 문법만 개선해주세요.
frontmatter는 그대로 유지하세요."""

    def fix_markdown(self, content: str, lint_results: List[Dict[str, Any]]) -> str:
        """마크다운 내용과 lint 결과를 바탕으로 수정된 마크다운 반환"""
        
        # lint 결과를 사용자 친화적인 형태로 변환
        lint_summary = self._format_lint_results(lint_results)
        
        user_message = f"""다음 마크다운 내용을 수정해주세요:

=== 마크다운 내용 ===
{content}

=== Lint 결과 ===
{lint_summary}

위의 lint 결과를 참고하여 마크다운을 수정해주세요."""

        try:
            # Ollama API 호출
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": f"System: {self.system_prompt}\n\nHuman: {user_message}\n\nAssistant: ",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "top_k": 40
                    }
                },
                timeout=300  # 5분 타임아웃
            )
            
            if response.status_code == 200:
                result = response.json()
                fixed_content = result.get('response', '').strip()
                
                # <think>...</think> 패턴 제거
                fixed_content = re.sub(r'<think>.*?</think>', '', fixed_content, flags=re.DOTALL)
                
                # 응답에서 마크다운 코드 블록 제거 (있는 경우)
                if fixed_content.startswith('```') and fixed_content.endswith('```'):
                    lines = fixed_content.split('\n')
                    if len(lines) > 2:
                        fixed_content = '\n'.join(lines[1:-1])
                
                # 추가 정리: 연속된 빈 줄 제거
                fixed_content = re.sub(r'\n\s*\n\s*\n', '\n\n', fixed_content)
                fixed_content = fixed_content.strip()
                
                return fixed_content if fixed_content else content
            else:
                print(f"Ollama API 오류: {response.status_code} - {response.text}")
                return content
                
        except requests.exceptions.ConnectionError:
            print("❌ Ollama 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인하세요.")
            print("   Ollama 설치: https://ollama.ai")
            print(f"   모델 다운로드: ollama pull {self.model_name}")
            return content
        except requests.exceptions.Timeout:
            print("⏰ Ollama 응답 시간이 초과되었습니다. 다시 시도해주세요.")
            return content
        except Exception as e:
            print(f"Ollama 호출 중 오류 발생: {e}")
            return content  # 오류 시 원본 반환
    
    def _format_lint_results(self, lint_results: List[Dict[str, Any]]) -> str:
        """lint 결과를 Ollama가 이해하기 쉬운 형태로 포맷팅"""
        if not lint_results:
            return "발견된 lint 문제가 없습니다."
        
        # 규칙별로 그룹화하여 더 체계적으로 표시
        rule_groups = {}
        for issue in lint_results:
            rule = issue['rule'].split('/')[0] if '/' in issue['rule'] else issue['rule']
            if rule not in rule_groups:
                rule_groups[rule] = []
            rule_groups[rule].append(issue)
        
        formatted_results = []
        for rule, issues in rule_groups.items():
            formatted_results.append(f"\n{rule} ({len(issues)}개):")
            for issue in issues[:3]:  # 각 규칙당 최대 3개 예시만 표시
                formatted_results.append(
                    f"  - 라인 {issue['line']}: {issue['description']}"
                )
            if len(issues) > 3:
                formatted_results.append(f"  - ... 그 외 {len(issues) - 3}개 더")
        
        return "\n".join(formatted_results)


class MarkdownProcessor:
    """마크다운 처리 메인 클래스"""
    
    def __init__(self, model_name: str = "qwen3:30b-32k-0.0"):
        self.linter = MarkdownLinter()
        self.fixer = MarkdownFixer(model_name=model_name)
    
    def process_file(self, input_path: str, output_path: str = None) -> bool:
        """마크다운 파일을 처리하여 수정된 버전 생성"""
        try:
            # 입력 파일 읽기
            with open(input_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            print(f"📝 파일 분석 중: {input_path}")
            
            # Lint 실행
            lint_results = self.linter.lint_file(input_path)
            print(f"🔍 {len(lint_results)}개의 lint 문제 발견")
            
            if lint_results:
                # 규칙별 문제 수 요약 출력
                rule_counts = {}
                for issue in lint_results:
                    rule = issue['rule'].split('/')[0] if '/' in issue['rule'] else issue['rule']
                    rule_counts[rule] = rule_counts.get(rule, 0) + 1
                
                print("   주요 문제들:")
                for rule, count in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"   - {rule}: {count}개")
                
                if len(rule_counts) > 5:
                    top_5_rules = [r for r, _ in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:5]]
                    remaining = sum(count for rule, count in rule_counts.items() if rule not in top_5_rules)
                    print(f"   - 기타: {remaining}개")
            
            # Ollama로 마크다운 수정
            print(f"🦙 Ollama ({self.fixer.model_name})로 마크다운 수정 중...")
            fixed_content = self.fixer.fix_markdown(original_content, lint_results)
            
            # 출력 파일 경로 결정
            if output_path is None:
                output_path = input_path
            
            # 수정된 내용 저장
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            
            print(f"✅ 수정 완료: {output_path}")
            
            # 수정 후 다시 lint 실행하여 개선 확인
            post_lint_results = self.linter.lint_file(output_path)
            improvement = len(lint_results) - len(post_lint_results)
            print(f"📊 개선 결과: {improvement}개 문제 해결 ({len(post_lint_results)}개 남음)")
            
            return True
            
        except Exception as e:
            print(f"❌ 처리 중 오류 발생: {e}")
            return False
    
    def process_directory(self, directory_path: str, recursive: bool = True):
        """디렉토리 내 모든 마크다운 파일 처리"""
        directory = Path(directory_path)
        
        if recursive:
            md_files = list(directory.rglob("*.md"))
        else:
            md_files = list(directory.glob("*.md"))
        
        print(f"📁 {len(md_files)}개의 마크다운 파일 발견")
        
        for md_file in md_files:
            print(f"\n처리 중: {md_file}")
            self.process_file(str(md_file))


def main():
    """메인 실행 함수 - 파일 경로를 입력받아 처리"""
    import sys
    
    if len(sys.argv) < 2:
        print("🦙 Ollama 기반 마크다운 자동 수정 시스템")
        print("📋 사용법: python mdfm_ollama.py <파일경로> [모델명]")
        print("📝 예시: python mdfm_ollama.py tests/example.md")
        print("📝 모델 지정: python mdfm_ollama.py tests/example.md llama3.1:8b")
        print("💾 출력: 원본 파일에 직접 저장됩니다")
        print("📊 주요 수정 사항: MD007(들여쓰기), MD032(목록 공백), MD022(헤딩 공백) 등")
        print()
        print("🔧 Ollama 설정:")
        print("   1. Ollama 설치: https://ollama.ai")
        print("   2. 모델 다운로드: ollama pull llama3.1:8b")
        print("   3. 서버 실행: ollama serve (보통 자동 실행)")
        sys.exit(1)
    
    file_path = sys.argv[1]
    model_name = sys.argv[2] if len(sys.argv) > 2 else "qwen3:30b-32k-0.0"
    
    if not os.path.exists(file_path):
        print(f"❌ 오류: 파일 '{file_path}'을 찾을 수 없습니다.")
        sys.exit(1)
    
    if not file_path.endswith('.md'):
        print(f"❌ 오류: 마크다운 파일(.md)만 처리할 수 있습니다.")
        sys.exit(1)
    
    # Ollama 연결 테스트
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [model['name'] for model in models]
            if model_name not in model_names:
                print(f"⚠️  모델 '{model_name}'이 설치되지 않았습니다.")
                print(f"   설치: ollama pull {model_name}")
                print(f"   사용 가능한 모델: {', '.join(model_names) if model_names else '없음'}")
                sys.exit(1)
            print(f"🦙 Ollama 연결 확인 완료 (모델: {model_name})")
        else:
            print("❌ Ollama 서버가 응답하지 않습니다.")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ Ollama 서버에 연결할 수 없습니다.")
        print("   Ollama가 실행 중인지 확인하세요: ollama serve")
        sys.exit(1)
    
    # 프로세서 초기화 및 파일 처리
    processor = MarkdownProcessor(model_name=model_name)
    success = processor.process_file(file_path)
    
    if success:
        print(f"\n🎉 처리 완료! 수정된 파일: {file_path}")
    else:
        print(f"\n❌ 파일 처리 중 오류가 발생했습니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()