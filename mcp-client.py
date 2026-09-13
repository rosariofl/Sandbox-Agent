import asyncio, os, json, sys
from anthropic import Anthropic
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

mountain_tz = ZoneInfo("America/Denver")

load_dotenv()
anthropic = Anthropic()  # reads ANTHROPIC_API_KEY from env

server_params = StdioServerParameters(command="python", args=["mcp-server.py"])


def audit(action: str, args: dict, allowed: bool, reason: str = "", approved_by: dict = None ):
    audit_trail = {
        "timestamp": datetime.now(timezone.utc).astimezone(mountain_tz).isoformat(),
        "action": action,
        "args": args,
        "allowed": allowed,
        "reason": reason,
        "approved_by": approved_by
    }
    print(json.dumps(audit_trail), file=sys.stderr, flush=True)


def mcp_tools_to_anthropic(mcp_tool_list):
    # translate each MCP tool -> {"name", "description", "input_schema"}
    # the MCP tool objects have .name, .description, .inputSchema
    return [
        {
            "name": tool.name, 
            "description": tool.description, 
            "input_schema": {
                "type": "object",
                "properties": tool.inputSchema.get("properties", {}),
                "required": tool.inputSchema.get("required", [])
            }
        } 
        for tool in mcp_tool_list 
    ]

async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = mcp_tools_to_anthropic((await session.list_tools()).tools)

            print(f"Tools: {tools}\n", file=sys.stderr, flush=True)

            messages = [{"role": "user",
                         "content": "Look up the wells in NV and flag anything interesting for review."}]

            loop_counter = 0

            print("Starting agent loop\n", file=sys.stderr, flush=True)
            while True:
                if loop_counter >= 10:
                    audit("loop_cap_hit", args={"loop counter": loop_counter}, allowed=False, reason="agent exceeded iteration limit")
                    break

                response = anthropic.messages.create(
                    model="claude-sonnet-4-5",   # check current model name when you run
                    max_tokens=1024,
                    tools=tools,
                    messages=messages,
                )

                # Simulated response for demonstration purposes
                # response = Message(      
                #     id='msg_01XFDUDYJgAACzvnptvVoYEL', 
                #     type='message', 
                #     role='assistant', 
                #     model='claude-sonnet-4-5', 
                #     content=[
                #         TextBlock(
                #             type='text', 
                #             text="This is an example response from the model when getting a TextBlock"
                #         )
                #     ], 
                #     stop_reason='end_turn',  # Normal conversational completion
                #     stop_sequence=None, 
                #     usage=Usage(input_tokens=25, completion_tokens=25, output_tokens=30)
                # )

                # Simulated response for demonstration purposes
                # response = Message(      
                #     id='msg_01XFDUDYJgAACzvnptvVoYEL', 
                #     type='message', 
                #     role='assistant', 
                #     model='claude-sonnet-4-5', 
                #     content=[
                #         ToolUseBlock(
                #             id='tool_use_01XFDUDYJgAACzvnptvVoYEL',
                #             input={"region": "NV"},
                #             type='tool_use', 
                #             name='read_wells'  # Example tool name
                #         )
                #     ], 
                #     stop_reason='tool_use',  # Normal conversational completion
                #     stop_sequence=None, 
                #     usage=Usage(input_tokens=25, completion_tokens=25, output_tokens=30)
                # )

                # Simulated response for demonstration purposes
                # response = Message(      
                #     id='msg_01XFDUDYJgAACzvnptvVoYEL', 
                #     type='message', 
                #     role='assistant', 
                #     model='claude-sonnet-4-5', 
                #     content=[
                #         ToolUseBlock(
                #             id='tool_use_01XFDUDYJgAACzvnptvVoYEL',
                #             input={"site_id": "big-blind", "note": "Check for unusual temperature readings."},
                #             type='tool_use', 
                #             name='flag_site'  # Example tool name
                #         )
                #     ], 
                #     stop_reason='tool_use',  # Normal conversational completion
                #     stop_sequence=None, 
                #     usage=Usage(input_tokens=25, completion_tokens=25, output_tokens=30)
                # )

                # append the model's turn to history (it may contain tool_use blocks)
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason != "tool_use":
                    # model answered in text — print it and stop
                    for block in response.content:
                        if block.type == "text":
                            print(f"AGENT: {block.text}", file=sys.stderr, flush=True)
                    break

                # model wants tools. For EACH tool_use block:
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await session.call_tool(block.name, block.input)
                        print(f"Tool result: {result}", file=sys.stderr, flush=True)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result.content[0].text
                        })

                messages.append({"role": "user", "content": tool_results})

                loop_counter += 1

                print(f"Usage: {response.usage}\n", file=sys.stderr, flush=True)

            print("\nAgent loop finished\nPrinting messages...", file=sys.stderr, flush=True)
            for message in messages:
                print(f"Message: {message}\n", file=sys.stderr, flush=True)

asyncio.run(main())