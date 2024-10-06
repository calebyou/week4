import os
import re
import chainlit as cl
from agents.base_agent import Agent

class ImplementationAgent(Agent):
    """
    이 에이전트는 plan.md 파일의 각 마일스톤을 하나씩 구현하는 역할을 합니다.
    index.html과 styles.css 파일을 생성하거나 업데이트하고, plan.md에서 마일스톤을 완료로 표시합니다.
    """

    def __init__(self, name, client, prompt="", gen_kwargs=None):
        super().__init__(name, client, prompt, gen_kwargs)

    async def execute(self, message_history):
        """
        plan.md의 현재 마일스톤에 따라 구현을 실행합니다.
        """
        plan_md_path = os.path.join("artifacts", "plan.md")
        index_html_path = os.path.join("artifacts", "index.html")
        styles_css_path = os.path.join("artifacts", "styles.css")

        # plan.md 파일 로드
        if not os.path.exists(plan_md_path):
            return "오류: artifacts 폴더에 plan.md 파일이 없습니다."

        with open(plan_md_path, "r") as file:
            plan_content = file.read()

        all_milestones = []  # 완료한 마일스톤을 저장할 리스트

        while True:  # 모든 마일스톤이 완료될 때까지 반복
            # 다음 미완료 마일스톤 파싱
            milestone = self._get_next_milestone(plan_content)

            # 미완료 마일스톤이 없으면 종료
            if not milestone:
                break
            
            # 이미 완료된 마일스톤인지 확인
            if "- [x]" in milestone:
                await cl.Message(content=f"완료된 마일스톤을 건너뜁니다: {milestone.strip()}").send()
                continue  # 다음 마일스톤으로 넘어감

            await cl.Message(content=f"마일스톤 구현 중: {milestone.strip()}").send()

            # 마일스톤에 대한 HTML 및 CSS 코드 생성
            html_code, css_code = await self._generate_code_for_milestone(milestone, message_history)

            # index.html 업데이트
            updated_html = await self._update_html_content(index_html_path, html_code)

            # styles.css 업데이트
            updated_css = await self._update_css_content(styles_css_path, css_code)

            # plan.md에서 마일스톤을 완료로 표시
            updated_plan = self._mark_milestone_completed(plan_content, milestone)
            self._update_artifact(plan_md_path, updated_plan)

            all_milestones.append(milestone)  # 완료한 마일스톤 추가
            
            plan_content = updated_plan  # 다음 루프에서 변경 사항을 반영

            # 디버그: 생성된 HTML 코드 출력
            await cl.Message(content=f"생성된 HTML 코드:\n{html_code}").send()  
            
            # 디버그: 업데이트된 index.html 내용 출력
            await cl.Message(content=f"업데이트된 index.html 내용:\n{updated_html}").send()  

        if all_milestones:
            milestones_str = ', '.join([m.strip() for m in all_milestones])
            await cl.Message(content=f"완료된 마일스톤: {milestones_str}. 업데이트된 파일: index.html, styles.css.").send()
        else:
            await cl.Message(content="구현할 마일스톤이 없거나 모든 마일스톤이 이미 완료되었습니다.").send()

        # 모든 마일스톤이 완료되었는지 확인
        if all(milestone.startswith("- [x]") for milestone in plan_content.splitlines()):
            await cl.Message(content="모든 마일스톤이 완료되었습니다.").send()

    def _get_next_milestone(self, plan_content):
        """
        plan.md 내용에서 다음 미완료 마일스톤을 검색합니다.
        """
        lines = plan_content.split("\n")
        for line in lines:
            if line.strip().startswith("- [ ]"):  # 미완료 마일스톤
                return line.strip()
        return None

    async def _generate_code_for_milestone(self, milestone, message_history):
        """
        특정 마일스톤에 대한 HTML 및 CSS 코드를 LLM을 사용하여 생성합니다.
        """
        copied_message_history = message_history.copy()
        copied_message_history.append({"role": "user", "content": f"이 마일스톤을 구현하세요: {milestone}"})

        stream = await self.client.chat.completions.create(messages=copied_message_history, stream=True, **self.gen_kwargs)
        full_response = ""

        async for part in stream:
            if part.choices[0].delta.content:
                content = part.choices[0].delta.content
                full_response += content  # 모든 응답을 누적

        # HTML과 CSS 코드로 분리
        html_code = self._extract_code(full_response, "html")
        css_code = self._extract_code(full_response, "css")

        return html_code.strip(), css_code.strip()  # 각 코드의 앞뒤 공백 제거

    def _extract_code(self, response, code_type):
        """
        응답에서 HTML 또는 CSS 코드를 추출합니다.
        """
        pattern = r'```' + code_type + r'\n(.*?)```'
        match = re.search(pattern, response, re.DOTALL)
        return match.group(1) if match else ""  # 매칭된 코드 반환

    async def _update_html_content(self, file_path, new_content):
        """
        기존 HTML 파일의 내용을 OpenAI에 보내어 새로운 내용을 통합된 코드로 생성합니다.
        """
        existing_content = ""
        
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                existing_content = file.read()
        else:
            existing_content = """<!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <link rel="stylesheet" href="styles.css">
                    <title>Your Website</title>
                </head>
                <body>
                </body>
                </html>"""


        if existing_content:
            integrated_html = await self._integrate_new_html(existing_content, new_content)
        else:
            integrated_html = new_content
        
        # 파일에 업데이트된 HTML 내용을 저장
        with open(file_path, "w") as file:
            file.write(integrated_html)

        return integrated_html

    async def _integrate_new_html(self, existing_html, new_content):
        """
        기존 HTML과 새로운 내용을 통합하여 OpenAI에게 요청하고 응답을 반환합니다.
        """
        prompt = f"다음의 기존 HTML 코드를 유지하면서 새로운 내용을 추가해 주세요.\n\n기존 HTML:\n{existing_html}\n\n추가할 내용:\n{new_content}\n\n결과 HTML:"
        
        copied_message_history = [{"role": "user", "content": prompt}]
        stream = await self.client.chat.completions.create(messages=copied_message_history, stream=True, **self.gen_kwargs)
        full_response = ""

        async for part in stream:
            if part.choices[0].delta.content:
                content = part.choices[0].delta.content
                full_response += content  # 모든 응답을 누적

        # 응답에서 HTML 코드만 추출
        html_code = self._extract_code(full_response, "html")

        return html_code.strip()  # HTML 코드의 앞뒤 공백 제거 후 반환

    async def _update_css_content(self, file_path, new_content):
        """
        기존 내용을 유지하며 styles.css 파일에 새로운 내용을 업데이트합니다.
        """
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                existing_content = file.read()
        else:
            existing_content = ""  # 파일이 없으면 기존 내용은 없음

        updated_css_content = await self._integrate_new_css(existing_content, new_content)

        with open(file_path, "w") as file:
            file.write(updated_css_content)

        return updated_css_content

    async def _integrate_new_css(self, existing_css, new_content):
        """
        기존 CSS에 새로운 CSS 콘텐츠를 통합합니다. 중복을 피하고 올바르게 닫힌 코드를 생성합니다.
        """
        prompt = f"다음의 기존 CSS 코드를 유지하면서 새로운 CSS 코드를 통합해 주세요.\n\n기존 CSS:\n{existing_css}\n\n추가할 CSS:\n{new_content}\n\n결과 CSS:"
        
        copied_message_history = [{"role": "user", "content": prompt}]
        stream = await self.client.chat.completions.create(messages=copied_message_history, stream=True, **self.gen_kwargs)
        full_response = ""

        async for part in stream:
            if part.choices[0].delta.content:
                content = part.choices[0].delta.content
                full_response += content  # 모든 응답을 누적

        # 응답에서 CSS 코드만 추출
        css_code = self._extract_code(full_response, "css")

        return css_code.strip()  # CSS 코드의 앞뒤 공백 제거 후 반환

    def _update_artifact(self, file_path, updated_content):
        """
        파일의 내용을 업데이트합니다.
        """
        with open(file_path, "w") as file:
            file.write(updated_content)

    def _mark_milestone_completed(self, plan_content, milestone):
        """
        plan.md의 특정 마일스톤을 완료로 표시합니다.
        """
        return plan_content.replace(milestone, milestone.replace("- [ ]", "- [x]"))  # 상태 업데이트

