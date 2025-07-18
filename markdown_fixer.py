#!/usr/bin/env python3
"""
Markdown Fixer using OpenAI gpt-4o-mini to fix markdownlint-cli2 errors
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def run_markdownlint(file_path):
    """Run markdownlint-cli2 on a markdown file and return the output"""
    try:
        result = subprocess.run(
            ['markdownlint-cli2', file_path],
            capture_output=True,
            text=True
        )
        
        output = result.stdout + result.stderr
        
        # Filter out MD013 errors from the output
        filtered_lines = []
        md013_count = 0
        
        for line in output.split('\n'):
            if 'MD013/line-length' in line:
                md013_count += 1
                continue  # Skip MD013 lines
            filtered_lines.append(line)
        
        # Update the summary to reflect filtered count
        filtered_output = '\n'.join(filtered_lines)
        
        # Update error count in summary
        if 'Summary:' in filtered_output:
            import re
            summary_pattern = r'Summary: (\d+) error\(s\)'
            match = re.search(summary_pattern, filtered_output)
            if match:
                original_count = int(match.group(1))
                new_count = original_count - md013_count
                filtered_output = re.sub(
                    summary_pattern, 
                    f'Summary: {new_count} error(s)', 
                    filtered_output
                )
        
        # Remove file path from error lines to help GPT focus on line:column numbers
        import re
        # Replace "filepath:line:column" with just "line:column"
        filtered_output = re.sub(r'^[^:]+\.md:(\d+(?::\d+)?)', r'\1', filtered_output, flags=re.MULTILINE)
        
        return filtered_output
    except FileNotFoundError:
        return "Error: markdownlint-cli2 not found. Please install it with: npm install -g markdownlint-cli2"
    except Exception as e:
        return f"Error running markdownlint: {str(e)}"

def parse_markdown_with_frontmatter(content):
    """Parse markdown file to separate frontmatter and content"""
    # Check if file starts with frontmatter
    if content.startswith('---'):
        # Find the end of frontmatter
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter_raw = parts[1].strip()
            markdown_content = parts[2].lstrip('\n')
            return frontmatter_raw, markdown_content
    
    # No frontmatter found
    return None, content

def read_markdown_file(file_path):
    """Read markdown file content"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def fix_markdown_with_openai(markdown_content, markdownlint_output, client):
    """Use OpenAI gpt-4o-mini to fix markdown based on markdownlint output"""
    
    # Include the original content directly in the prompt
    prompt = f"""다음은 markdownlint-cli2의 출력과 원본 마크다운 파일 내용입니다.

markdownlint-cli2 출력:
```
{markdownlint_output}
```

원본 마크다운 파일 내용:
```markdown
{markdown_content}
```

markdownlint 출력에서 각 오류는 다음 형식으로 표시됩니다:
- 라인번호:컬럼번호 오류코드/오류명 설명 [상세정보] [컨텍스트: "해당 텍스트"]

예: `8 MD022/blanks-around-headings`는 8번째 줄에 제목 주변 공백 문제가 있음을 의미합니다.
`196:1 MD007/ul-indent`는 196번째 줄 1번째 컬럼에 리스트 들여쓰기 문제가 있음을 의미합니다.

위의 원본 파일 내용을 참조하여 다음 규칙을 따라 수정해주세요:

**매우 중요한 규칙:**
1. 모든 markdownlint 오류를 정확히 수정해야 합니다 (MD013 line-length 오류는 이미 제외되어 있음)
2. **원본 파일의 모든 내용을 반드시 포함해야 합니다** - 어떤 내용도 생략하거나 요약하지 마세요
3. **YAML 프론트메터를 원본과 정확히 동일하게 유지해주세요** (--- 으로 시작하고 끝나는 부분)
4. 한국어 텍스트와 의미를 절대 변경하지 마세요
5. 오직 마크다운 형식만 수정해주세요 (공백, 들여쓰기, 줄바꿈 등)
6. 라인 번호와 컬럼 번호를 정확히 참조하여 해당 위치의 문제만 수정해주세요
7. 모든 섹션, 모든 문단, 모든 리스트 항목, 모든 이미지, 모든 링크를 반드시 포함해야 합니다
8. 원본 파일의 길이와 동일하거나 더 긴 결과를 제공해야 합니다

**특정 오류 유형에 대한 수정 지침:**
- **MD036 (emphasis used instead of heading)**: 볼드체(**텍스트**)나 이탤릭체(*텍스트*)로 된 텍스트가 제목처럼 사용된 경우, 적절한 제목 레벨(#, ##, ### 등)로 변경하세요. 특히 다음 패턴들을 주의하세요:
  - "**◼︎ 텍스트**" 형태 → "### ◼︎ 텍스트" 또는 "#### ◼︎ 텍스트"로 변경
  - "**그림 설명: ...**" 형태 → "#### 그림 설명: ..."로 변경  
  - 섹션 구분자 역할을 하는 모든 볼드 텍스트를 적절한 헤딩 레벨로 변경
- **MD047 (single trailing newline)**: 파일이 반드시 하나의 빈 줄로 끝나야 합니다. 파일 끝에 정확히 하나의 개행 문자만 있도록 하세요
- **마크다운 강조 기호 띄어쓰기 규칙**: 마크다운 강조 기호(** 또는 *)의 앞뒤 띄어쓰기를 올바르게 수정하세요:
  - 잘못된 예: `밝혔습니다.**베트남은 완전 개방을 약속** 했습니다.`
  - 올바른 예: `밝혔습니다. **베트남은 완전 개방을 약속**했습니다.` 
  - 핵심 규칙: 
    * 강조 기호 시작(`**`) 앞에는 반드시 공백이나 구두점이 있어야 함
    * 강조 기호 끝(`**`) 뒤에는 공백 없이 바로 텍스트가 이어져야 함
    * `약속** 했습니다` → `약속**했습니다` (끝 마커 뒤 공백 제거)
- **금융 용어 및 약어 띄어쓰기 수정**: 잘 알려진 금융 용어나 약어에서 불필요한 띄어쓰기를 제거하세요:
  - `S &P 500` → `S&P 500`
  - `P &E 비율` → `P&E 비율` 
  - `M &A` → `M&A`
  - `R &D` → `R&D`
  - `AI &머신러닝` → `AI & 머신러닝` (한국어와 결합 시 &는 유지)
  - `GDP &경제성장` → `GDP & 경제성장`
  - 일반 규칙: 영문 약어에서 &(앰퍼샌드) 앞뒤의 불필요한 공백 제거

응답에는 **완전한 전체** 마크다운 파일 내용을 포함해주세요. 절대로 내용을 생략하거나 축약하지 마세요."""

    # save prompt to a file for debugging
    # with open('debug_prompt.txt', 'w', encoding='utf-8') as debug_file:
    #     debug_file.write(prompt)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {"role": "system", "content": "You are a helpful assistant that fixes markdown formatting issues based on markdownlint output. You MUST preserve ALL original content completely without any truncation or summarization. You MUST include the complete file content in your response, never shorten anything. You MUST preserve YAML frontmatter exactly as it appears in the original file. Your response should be as long as or longer than the original file. IMPORTANT: Also fix markdown emphasis spacing and financial term spacing - ensure space/punctuation before ** opening marker, NO space after ** closing marker when text follows, and fix financial terms like 'S &P 500' to 'S&P 500', 'M &A' to 'M&A', etc."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=16000,  # Use gpt-4o-mini which has better capacity
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error calling OpenAI API: {str(e)}"

def save_fixed_file(original_path, fixed_content):
    """Save the fixed markdown to a new file with _fix suffix"""
    original_file = Path(original_path)
    # fixed_file = original_file.parent / f"{original_file.stem}_fix{original_file.suffix}"
    fixed_file = original_file
    
    try:
        with open(fixed_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        return str(fixed_file)
    except Exception as e:
        return f"Error saving file: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='Fix markdown files using OpenAI gpt-4o-mini based on markdownlint-cli2 output')
    parser.add_argument('markdown_file', help='Path to the markdown file to fix')
    parser.add_argument('--api-key', help='OpenAI API key (or set OPENAI_API_KEY environment variable)')
    parser.add_argument('--model', default='gpt-4o-mini', help='OpenAI model to use (default: gpt-4o-mini)')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.markdown_file):
        print(f"Error: File {args.markdown_file} does not exist")
        sys.exit(1)
    
    # Set up OpenAI client
    api_key = args.api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OpenAI API key not provided. Use --api-key or set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    client = OpenAI(api_key=api_key)
    
    print(f"Processing: {args.markdown_file}")
    
    # Run markdownlint
    print("Running markdownlint-cli2...")
    markdownlint_output = run_markdownlint(args.markdown_file)
    
    if "Error:" in markdownlint_output:
        print(markdownlint_output)
        sys.exit(1)
    
    # Check if there are any errors to fix
    if "Summary: 0 error(s)" in markdownlint_output or ("error(s)" not in markdownlint_output and "Summary:" not in markdownlint_output):
        print("No markdownlint errors found. File is already properly formatted.")
        sys.exit(0)
    
    print(f"Found markdownlint errors. Output:\n{markdownlint_output}")
    
    # Read original file
    print("Reading original markdown file...")
    markdown_content = read_markdown_file(args.markdown_file)
    
    if markdown_content.startswith("Error:"):
        print(markdown_content)
        sys.exit(1)
    
    # Parse frontmatter
    frontmatter, _ = parse_markdown_with_frontmatter(markdown_content)
    if frontmatter:
        print("Detected YAML frontmatter - will be preserved during processing")
    
    # Fix markdown using OpenAI
    print("Fixing markdown with OpenAI...")
    fixed_content = fix_markdown_with_openai(markdown_content, markdownlint_output, client)
    
    if fixed_content.startswith("Error:"):
        print(fixed_content)
        sys.exit(1)
    
    # Remove potential code block markers from response
    if fixed_content.startswith("```markdown"):
        fixed_content = fixed_content[11:]
    if fixed_content.startswith("```"):
        fixed_content = fixed_content[3:]
    if fixed_content.endswith("```"):
        fixed_content = fixed_content[:-3]
    
    fixed_content = fixed_content.strip()
    
    # Fix MD047: Ensure file ends with exactly one newline
    fixed_content = fixed_content.rstrip() + '\n'
    
    # Save fixed file
    print("Saving fixed file...")
    fixed_file_path = save_fixed_file(args.markdown_file, fixed_content)
    
    if fixed_file_path.startswith("Error:"):
        print(fixed_file_path)
        sys.exit(1)
    
    print(f"Fixed file saved as: {fixed_file_path}")
    
    # Verify the fix by running markdownlint again
    print("Verifying fix...")
    verification_output = run_markdownlint(fixed_file_path)
    
    if "error(s)" in verification_output:
        print("Warning: Some errors may still remain:")
        print(verification_output)
    else:
        print("✅ All markdownlint errors have been fixed!")

if __name__ == "__main__":
    main()