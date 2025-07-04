import asyncio
from anthropic import AsyncAnthropic
import os
from colors import Colors
from phase_manager import State, Phase, Context
from tree_printer import tree_section, tree_success, tree_error
from fileutils import LLMFileGenerator


LAYOUT_IMPLEMENTATION_SYSTEM_PROMPT = """
You are a Django developer tasked with implementing a layout template.
Your task is to implement a layout by creating HTML template file in the templates/layouts/ directory.
You must respect facts provided to you about the app.

## Guidelines

1. Create exactly one template file in the templates/layouts/ directory
2. Follow Django template best practices
3. Create responsive, modern layout
4. Use semantic HTML structure
"""

class LayoutImplementationAgent:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.anthropic_client = AsyncAnthropic()
        self.files_created = []
        self.generator = LLMFileGenerator(max_tokens=10000)

    async def implement_layout(self, layout: dict, facts: str, context: Context):
        """Implement a layout by creating template files"""
        layout_name = layout["name"]
        layout_description = layout["description"]
        layout_style = layout["style"]

        prompt = f"""<facts>{facts}</facts>
<layout_name>{layout_name}</layout_name>
<layout_description>{layout_description}</layout_description>
<layout_style>{layout_style}</layout_style>

Create a template file named templates/layouts/{layout_name}.html"""

        expected_file_path = f"templates/layouts/{layout_name}.html"
        output_file_path = os.path.join(self.project_path, expected_file_path)
        
        await self.generator.generate_and_write_async(
            context.anthropic_client,
            system=LAYOUT_IMPLEMENTATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            expected_file_path=expected_file_path,
            output_file_path=output_file_path
        )
        
        self.files_created.append(expected_file_path)
        tree_success(f"Created {expected_file_path}")

class ExecuteLayouts(Phase):
    def run(self, state: State, context: Context) -> dict:
        layouts = state["layouts"]
        facts = state["facts"]
        project_path = state["project_path"]

        tree_section("Generate layouts")

        agent = LayoutImplementationAgent(project_path)
        async def process_layouts_async():
            tasks = [
                agent.implement_layout(layout, facts, context)
                for layout in layouts
            ]

            await asyncio.gather(*tasks)

            tree_success(f"All {len(layouts)} layouts completed successfully")

        try:
            asyncio.run(process_layouts_async())
            tree_success(f"Process completed - Created {len(agent.files_created)} files")
        except Exception as e:
            tree_error(f"Process failed - {e}")
            raise

        return {}
