import os
import chainlit as cl
from agents.base_agent import Agent
from agents.implementation_agent import ImplementationAgent

class SupervisorAgent(Agent):
    """
    SupervisorAgent는 사용자와 상호작용하고 PlanningAgent 및 ImplementationAgent에 작업을 위임합니다.
    모든 마일스톤이 완료될 때까지 프로세스를 관리합니다.
    """

    def __init__(self, name, client, prompt="", gen_kwargs=None):
        super().__init__(name, client, prompt, gen_kwargs)

    async def execute(self, message_history):
        """
        사용자의 요청을 처리하고, 마일스톤을 관리합니다.
        """
        # 계획서 파일 로드
        plan_md_path = os.path.join("artifacts", "plan.md")
        
        if not os.path.exists(plan_md_path):
            return "오류: artifacts 폴더에 plan.md 파일이 없습니다."

        with open(plan_md_path, "r") as file:
            plan_content = file.read()

        # Planning Agent에게 요청
        planning_agent = Agent("Planning Agent", self.client)
        await cl.Message(content="계획 작성을 시작합니다...").send()
        
        plan_response = await planning_agent.execute(message_history)
        await cl.Message(content=f"계획 작성 완료: {plan_response}").send()

        while True:
            # 미완료 마일스톤 검색
            milestone = self._get_next_milestone(plan_content)

            if not milestone:
                await cl.Message(content="모든 마일스톤이 완료되었습니다.").send()
                break
            
            await cl.Message(content=f"마일스톤을 시작합니다: {milestone.strip()}").send()

            # ImplementationAgent에 작업 위임
            implementation_agent = ImplementationAgent("Implementation Agent", self.client)
            implementation_response = await implementation_agent.execute(message_history)

            # 다음 마일스톤을 업데이트
            updated_plan_content = self._mark_milestone_completed(plan_content, milestone)
            plan_content = updated_plan_content  # 다음 루프에서 변경 사항을 반영

            # 디버그: 완료된 마일스톤 출력
            await cl.Message(content=f"완료된 마일스톤: {milestone.strip()}").send()
            await cl.Message(content=f"구현 결과: {implementation_response}").send()

    def _get_next_milestone(self, plan_content):
        """
        plan.md 내용에서 다음 미완료 마일스톤을 검색합니다.
        """
        lines = plan_content.split("\n")
        for line in lines:
            if line.strip().startswith("- [ ]"):  # 미완료 마일스톤
                return line.strip()
        return None

    def _mark_milestone_completed(self, plan_content, milestone):
        """
        plan.md 내용에서 주어진 마일스톤을 완료로 표시합니다.
        """
        return plan_content.replace(milestone, milestone.replace("- [ ]", "- [x]"))  # 완료로 표시
