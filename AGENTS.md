# AGENTS.md: Server Framework Execution Rules

This repository is the server-side framework root for the multi-agent MLLM hallucination mitigation system.

Authoritative paths:

```text
SPEC_ROOT=/Users/zrblution/Documents/桌面文件夹/博士阶段/MLLM幻觉消除/work1_test4/find_idea_through_baseline/Multi-Agent Experimental System/multi_agent_mllm_system_specs
LOCAL_AGENT_SYSTEM_ROOT=/Users/zrblution/Documents/桌面文件夹/博士阶段/MLLM幻觉消除/work1_test4/find_idea_through_baseline/Multi-Agent Experimental System/multi_agent_mllm_system
SYSTEM_ROOT=/home/vepfs/data/work1/muti-agent-work_test4
SERVER_FRAMEWORK_ROOT=/home/vepfs/data/work1/muti-agent-work_test4
```

Rules:

- Never commit `.env`, real API keys, tokens, cookies, SSH private keys, model weights, datasets, large tensor artifacts, browser traces, or raw large logs.
- Configuration files may reference environment variable names only, for example `api_key_env: DEEPSEEK_API_KEY`.
- Real model and benchmark execution must use controlled runner actions. Do not let agents execute arbitrary shell commands.
- Large artifacts must be referenced by manifest files rather than committed directly.
- Each phase must run its declared tests, write a patch summary, and preserve failure diagnostics.
