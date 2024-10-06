from dotenv import load_dotenv
import chainlit as cl
from agents.base_agent import Agent
from agents.implementation_agent import ImplementationAgent
import base64

load_dotenv()

# Note: If switching to LangSmith, uncomment the following, and replace @observe with @traceable
# from langsmith.wrappers import wrap_openai
# from langsmith import traceable
# client = wrap_openai(openai.AsyncClient())

from langfuse.decorators import observe
from langfuse.openai import AsyncOpenAI
 
client = AsyncOpenAI()

gen_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.2
}

SYSTEM_PROMPT = """\
You are a pirate.
"""

PLANNING_PROMPT = """\
You are a software architect, preparing to build the web page in the image that the user sends. 
Once they send an image, generate a plan, described below, in markdown format.

If the user or reviewer confirms the plan is good, available tools to save it as an artifact \
called `plan.md`. If the user has feedback on the plan, revise the plan, and save it using \
the tool again. A tool is available to update the artifact. Your role is only to plan the \
project. You will not implement the plan, and will not write any code.

If the plan has already been saved, no need to save it again unless there is feedback. Do not \
use the tool again if there are no changes.

For the contents of the markdown-formatted plan, create two sections, "Overview" and "Milestones".

In a section labeled "Overview", analyze the image, and describe the elements on the page, \
their positions, and the layout of the major sections.

Using vanilla HTML and CSS, discuss anything about the layout that might have different \
options for implementation. Review pros/cons, and recommend a course of action.

In a section labeled "Milestones", describe an ordered set of milestones for methodically \
building the web page, so that errors can be detected and corrected early. Pay close attention \
to the aligment of elements, and describe clear expectations in each milestone. Do not include \
testing milestones, just implementation.

Milestones should be formatted like this:

 - [ ] 1. This is the first milestone
 - [ ] 2. This is the second milestone
 - [ ] 3. This is the third milestone
"""

HTML_PROMPT = """\
You are an implementation agent tasked with completing a series of milestones defined in a markdown file named `plan.md`. Each milestone specifies a feature or task that requires the generation of HTML and CSS code.

Your responsibilities are as follows:

1. **Load the `plan.md` file**: This file contains a list of milestones. Each milestone is marked as incomplete with `- [ ]` and completed with `- [x]`.

2. **Iterate through milestones**: For each incomplete milestone:
   - Generate the necessary HTML and CSS code to implement the feature described in the milestone.
   - Update the `index.html` file with the generated HTML code.
   - Update the `styles.css` file with the generated CSS code.

3. **Mark milestones as completed**: After successfully implementing the HTML and CSS for a milestone, update the `plan.md` file to mark that milestone as completed (`- [x]`).

4. **Provide feedback**: During the implementation process, provide status updates for each milestone, indicating whether it is being implemented or skipped if it is already completed.

5. **Handle completion**: Once all milestones are completed, confirm that the web page has been successfully created, and indicate that no more milestones remain.

6. **make sure that the styles.css must be imported correctly via link tag in index.html. They are in the same folder.

Make sure to structure your code clearly and follow best practices for HTML and CSS to ensure the generated files are clean and well-organized. The end goal is to create a fully functional web page based on the milestones defined in `plan.md`.

"""


# Create instances of the agents
planning_agent = Agent(name="Planning Agent", client=client, prompt=PLANNING_PROMPT)
implementation_agent = ImplementationAgent(name="Implementation Agent", client=client, prompt=HTML_PROMPT)

@observe
@cl.on_chat_start
def on_chat_start():    
    message_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    cl.user_session.set("message_history", message_history)

@observe
async def generate_response(client, message_history, gen_kwargs):
    response_message = cl.Message(content="")
    await response_message.send()

    stream = await client.chat.completions.create(messages=message_history, stream=True, **gen_kwargs)
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await response_message.stream_token(token)
    
    await response_message.update()

    return response_message

@cl.on_message
@observe
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])

    # Processing images exclusively
    images = [file for file in message.elements if "image" in file.mime] if message.elements else []

    if images:
        # Read the first image and encode it to base64
        with open(images[0].path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
        message_history.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": message.content
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        })
    else:
        message_history.append({"role": "user", "content": message.content})

    # Planning agent generates the plan
    plan_response_message = await planning_agent.execute(message_history)
    message_history.append({"role": "assistant", "content": plan_response_message})

    # Check if the user confirms the plan (assumed via a follow-up message)
    if "confirm" in message.content.lower():
        # If confirmed, implementation agent generates HTML code
        html_response_message = await implementation_agent.execute(message_history)
        message_history.append({"role": "assistant", "content": html_response_message})

    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()
