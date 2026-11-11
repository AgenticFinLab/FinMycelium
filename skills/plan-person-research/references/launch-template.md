# Person research prompts and session settings

## Session settings

Use the following project baseline for person research:

| Setting          | Value                     |
| ---------------- | ------------------------- |
| Model            | GPT-6-Sol (`gpt-6-sol`) |
| Reasoning effort | High (`high`)           |
| Web search       | Live search enabled       |

Select the model and effort in the Codex window or at launch. Mentioning a model in the task prompt does not configure the session. These settings apply to the personal research agent; FinMycelium search and Builder models are configured in their own tasks. See the [official OpenAI model controls](https://learn.chatgpt.com/docs/models?surface=cli).

For a new task, send the initial prompt, then the revision prompt after delivery. Revision covers self-review, any needed corrections, ready directories, the progress CSV, and the README entry. It can proceed without feedback from another window. This completes the normal planning cycle; retain open questions for event-level work. Use the same revision prompt for later updates when needed.

## Initial research prompt

Replace the person and scope placeholders. The Skill defines directory creation and the shared `EPG-dataset/person-epg/` root, with a separate directory for each person. For full-life research, use `their full publicly documented life through the research date` as the research scope; use an explicit period or topic when requested.

```text
Follow skills/plan-person-research/SKILL.md and its template to conduct research on {{person_name}} covering {{research_scope}}. Complete the research and save the English research plan according to the skill, pending my confirmation.
```

Research methods, source requirements, and deliverable structure remain in [SKILL.md](../SKILL.md) and the [research plan template](../assets/research-plan-template.md). Keep the launch prompt limited to the case inputs.

## Revision prompt

Replace the plan path. The agent follows the current Skill to assess the plan and prepare its files and directories. A new session can use this prompt with access to the plan and the same settings.

```text
Re-read skills/plan-person-research/SKILL.md and its template, then review {{research_plan_path}} and revise where needed. After review, create the directories that are ready according to the skill and update the directory tree. Save the plan and summarize changes, created directories, and remaining questions.
```
