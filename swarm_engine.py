import os
import json
import re
from typing import List, Dict
from openai import OpenAI

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

print("[*] Initializing Apex Swarm OS™ (v22.0 - Token Economy)...")

# ==============================================================================
# 1. DYNAMIC AI BRAIN ROUTER (NVIDIA Qwen 3.5 Elite Stack)
# ==============================================================================
AGENT_MODELS = {
    "Master_Orchestrator": {
        "free": "groq/llama3-8b-8192", 
        "pro": "meta/llama-3.1-8b-instruct"
    },
    "Apex_Researcher": {
        "free": "groq/llama-3.3-70b-versatile", 
        "pro": "qwen/qwen3-next-80b-a3b-instruct"
    },
    "Apex_Strategist": {
        "free": "groq/llama-3.3-70b-versatile", 
        "pro": "meta/llama-3.1-70b-instruct"
    },
    "Apex_Coder": {
        "free": "groq/llama-3.3-70b-versatile", 
        "pro": "qwen/qwen3-next-80b-a3b-instruct"
    }
}

def get_client_for_model(tier: str, agent_name: str):
    model_name = AGENT_MODELS.get(agent_name, {}).get(tier, "groq/llama-3.3-70b-versatile")
    
    if "groq" in model_name:
        client = OpenAI(
            api_key=os.environ.get("GROQ_API_KEY"), 
            base_url="https://api.groq.com/openai/v1"
        )
        actual_model_name = model_name.replace("groq/", "")
        return client, actual_model_name
    else:
        client = OpenAI(
            api_key=os.environ.get("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1"
        )
        return client, model_name

# ==============================================================================
# 2. SHARED WORKSPACE & TOKEN TRACKING
# ==============================================================================
class SwarmState:
    def __init__(self, query: str):
        self.query = query
        self.plan = []
        self.artifacts = {}
        self.messages = []
        self.current_agent = None
        self.tokens_used = 0  # NEW: Track total tokens consumed

    def add_artifact(self, key: str, value: str): self.artifacts[key] = value
    def get_artifact(self, key: str) -> str: return self.artifacts.get(key, "No data available.")
    def to_dict(self): return {
        "plan": self.plan, 
        "final_answer": self.artifacts.get("final_answer", "Error: No final answer generated."), 
        "history": self.messages,
        "tokens_used": self.tokens_used  # Return tokens used to UI
    }

# ==============================================================================
# 3. AGENT DEFINITIONS
# ==============================================================================
AGENT_DEFS = {
    "Master_Orchestrator": {
        "system_prompt": (
            "You are the Master Orchestrator of the Apex Swarm OS. Analyze the user's request and route it instantly.\n"
            "ROUTING RULES:\n"
            "- If they want CODE, a WEB APP, a UI, or a DASHBOARD: Delegate to Apex_Coder.\n"
            "- If they want RESEARCH, WEB DATA, or MARKET ANALYSIS: Delegate to Apex_Researcher.\n"
            "- If they want WRITING, STRATEGY, or EMAILS: Delegate to Apex_Strategist.\n"
            "Be fast. Do not ask follow-up questions. Just route."
        ),
        "tools": ["delegate_to_agent"],
        "allowed_transitions": ["Apex_Coder", "Apex_Researcher", "Apex_Strategist"]
    },
    "Apex_Researcher": {
        "system_prompt": (
            "You are an Apex Researcher. Gather raw intelligence at lightning speed.\n"
            "WORKFLOW:\n"
            "1. Call `tool_web_search` if you need live data.\n"
            "2. Extract specific facts, numbers, and names. No fluff.\n"
            "3. Save findings using `save_artifact` with key 'research_data'.\n"
            "4. Delegate to Apex_Strategist to format the final answer.\n"
            "NEVER delegate to yourself."
        ),
        "tools": ["tool_web_search", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["Apex_Strategist"]
    },
    "Apex_Strategist": {
        "system_prompt": (
            "You are an Apex Strategist. You write high-value, formatted answers.\n"
            "WORKFLOW:\n"
            "1. Read 'research_data' using `read_artifact` if available.\n"
            "2. Write the final answer. Use Markdown for structure.\n"
            "3. Save as 'final_answer' using `save_artifact`.\n"
            "4. Call `finish_task`."
        ),
        "tools": ["read_artifact", "save_artifact", "finish_task"],
        "allowed_transitions": []
    },
    "Apex_Coder": {
        "system_prompt": (
            "You are an Apex Coder and Elite Debugger. You use deep reasoning to build flawless applications and fix complex bugs.\n"
            "WORKFLOW FOR BUILDING APPS:\n"
            "1. Think step-by-step about the architecture before writing code.\n"
            "2. Write a SINGLE FILE HTML app using Tailwind CSS (via CDN) and Vanilla JS.\n"
            "3. It must be fully self-contained and runnable in an iframe.\n"
            "4. Wrap the HTML code in ```html ... ``` markdown blocks.\n\n"
            "WORKFLOW FOR DEBUGGING:\n"
            "1. Analyze the provided code or error message carefully.\n"
            "2. Identify the root cause of the bug using step-by-step logic.\n"
            "3. Provide the fully corrected code, highlighting what was changed.\n"
            "4. Wrap corrected code in the appropriate markdown blocks (e.g., ```python, ```javascript).\n\n"
            "Save the output as 'final_answer' using `save_artifact`.\n"
            "Call `finish_task`."
        ),
        "tools": ["save_artifact", "finish_task"],
        "allowed_transitions": []
    }
}

# ==============================================================================
# 4. TOOL IMPLEMENTATIONS
# ==============================================================================
def tool_web_search(query: str) -> str:
    clean_query = query.replace("top 3", "").replace("latest", "").strip()
    if not clean_query: clean_query = "market analysis"
    print(f"    [TOOL_EXEC] Searching: {clean_query!r}")
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(clean_query, region="wt-wt", safesearch="off", max_results=5))
        if not results: return "LIVE SEARCH FAILED: No results found."
        return "\n".join(f"[{i+1}] {r.get('title', '')}: {r.get('body', '')}" for i, r in enumerate(results))
    except Exception as e:
        return f"LIVE SEARCH FAILED: Search engine error ({e})."

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "delegate_to_agent", "description": "Hand off the current task to another agent.", "parameters": {"type": "object", "properties": {"agent_name": {"type": "string", "enum": list(AGENT_DEFS.keys())}, "message": {"type": "string"}}, "required": ["agent_name", "message"]}}},
    {"type": "function", "function": {"name": "tool_web_search", "description": "Search the web for market data, competitor info, or news.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "save_artifact", "description": "Save work to the shared workspace.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["research_data", "final_answer"]}, "content": {"type": "string"}}, "required": ["key", "content"]}}},
    {"type": "function", "function": {"name": "read_artifact", "description": "Read an artifact from the workspace.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["research_data"]}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "finish_task", "description": "End the swarm process.", "parameters": {"type": "object", "properties": {}}}}
]

def get_tool_schemas_for_agent(agent_name: str) -> list:
    allowed = set(AGENT_DEFS[agent_name]["tools"])
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed]

def dispatch_tool_call(state: SwarmState, agent_name: str, agent_def: dict, func_name: str, func_args: dict):
    if func_name not in agent_def["tools"]:
        return f"ERROR: {agent_name} is not permitted to use '{func_name}'.", False

    if func_name == "delegate_to_agent":
        next_agent = func_args["agent_name"]
        if next_agent == agent_name: return f"CRITICAL ERROR: You cannot delegate to yourself! You are {agent_name}.", False
        if next_agent not in agent_def["allowed_transitions"]: return f"ERROR: You cannot delegate to {next_agent}.", False
        state.current_agent = next_agent
        handoff_note = func_args.get("message", "")
        return f"Control handed over to {next_agent}. Handoff note from {agent_name}: {handoff_note}", False

    elif func_name == "save_artifact":
        state.add_artifact(func_args["key"], func_args["content"])
        return f"Artifact '{func_args['key']}' saved successfully.", False

    elif func_name == "read_artifact":
        return state.get_artifact(func_args["key"]), False

    elif func_name == "tool_web_search":
        return tool_web_search(**func_args), False

    elif func_name == "finish_task":
        if "final_answer" not in state.artifacts: state.add_artifact("final_answer", "Task finished, but no final answer was saved.")
        return "Task finished.", True

    return f"Error: Tool {func_name} not found.", False

# ==============================================================================
# 5. THE AGENTIC EXECUTION LOOP
# ==============================================================================
def execute_agent_loop(state: SwarmState, tier: str = "free", max_output_tokens: int = 4096, max_steps: int = 15) -> dict:
    step = 0
    while step < max_steps:
        step += 1
        agent_name = state.current_agent
        agent_def = AGENT_DEFS[agent_name]
        
        client, model_name = get_client_for_model(tier, agent_name)
        print(f"\n[STEP {step}] Agent: {agent_name} | Model: {model_name} | Tier: {tier}")
        
        state.plan.append(agent_name)
        api_messages = [{"role": "system", "content": agent_def["system_prompt"]}] + state.messages
        agent_tools = get_tool_schemas_for_agent(agent_name)

        try:
            # Pass the user's manual max_output_tokens limit here
            response = client.chat.completions.create(
                model=model_name, 
                messages=api_messages, 
                tools=agent_tools, 
                tool_choice="auto", 
                max_tokens=max_output_tokens, 
                temperature=0.3
            )
            
            # NEW: Deduct the tokens used from the state wallet
            if hasattr(response, 'usage') and response.usage:
                state.tokens_used += response.usage.total_tokens
                
        except Exception as e:
            error_str = str(e)
            if "failed_generation" in error_str and "<function=" in error_str:
                print("    [SELF-HEAL] Caught malformed function call. Parsing manually...")
                match = re.search(r'<function=(\w+)>(\{.*?\})</function>', error_str)
                if match:
                    func_name, raw_args = match.group(1), match.group(2)
                    try: func_args = json.loads(raw_args)
                    except json.JSONDecodeError: state.add_artifact("final_answer", f"⚠️ Swarm API Error (unparseable self-heal args): {e}"); return state.to_dict()
                    print(f"    [SELF-HEAL] Manually executing: {func_name}({func_args})")
                    observation, finished = dispatch_tool_call(state, agent_name, agent_def, func_name, func_args)
                    healed_id = "healed_call_1"
                    state.messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": healed_id, "type": "function", "function": {"name": func_name, "arguments": json.dumps(func_args)}}]})
                    state.messages.append({"role": "tool", "name": func_name, "content": str(observation), "tool_call_id": healed_id})
                    if finished: return state.to_dict()
                    continue
            elif "429" in error_str or "rate_limit" in error_str.lower():
                state.add_artifact("final_answer", "⚠️ **Swarm is at Capacity:** High traffic. Please wait 60 seconds or upgrade to Pro for priority."); return state.to_dict()
            state.add_artifact("final_answer", f"⚠️ Swarm API Error: {e}"); return state.to_dict()

        choice = response.choices[0]
        if choice.finish_reason == "tool_calls":
            state.messages.append(choice.message)
            for tool_call in choice.message.tool_calls:
                try: func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    state.messages.append({"role": "tool", "name": tool_call.function.name, "content": f"ERROR: Could not parse arguments as JSON: {tool_call.function.arguments!r}", "tool_call_id": tool_call.id}); continue
                func_name = tool_call.function.name
                print(f"    [ACTION] {func_name}({func_args})")
                observation, finished = dispatch_tool_call(state, agent_name, agent_def, func_name, func_args)
                state.messages.append({"role": "tool", "name": func_name, "content": str(observation), "tool_call_id": tool_call.id})
                if finished: return state.to_dict()
        elif choice.finish_reason == "stop":
            state.messages.append({"role": "assistant", "content": choice.message.content})
            state.messages.append({"role": "user", "content": "You must use a tool to proceed. Delegate, save, or finish."})
        else: state.add_artifact("final_answer", f"⚠️ Swarm stopped unexpectedly (finish_reason='{choice.finish_reason}')."); break

    if "final_answer" not in state.artifacts: state.add_artifact("final_answer", "⚠️ Swarm exceeded maximum steps without finishing.")
    return state.to_dict()

# ==============================================================================
# 6. ENTRY POINT
# ==============================================================================
def run_swarm(user_prompt: str, tier: str = "free", max_output_tokens: int = 4096) -> dict:
    print(f"\n[SWARM v22.0] Query: {user_prompt[:60]}... (Tier: {tier} | Max Output: {max_output_tokens})")
    state = SwarmState(query=user_prompt)
    state.current_agent = "Master_Orchestrator"
    state.messages.append({"role": "user", "content": f"Client Request: {user_prompt}\n\nPlease delegate this to the appropriate specialist."})
    return execute_agent_loop(state, tier=tier, max_output_tokens=max_output_tokens)
