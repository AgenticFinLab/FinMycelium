# Person research prompts and session settings

## Session settings

Use the following project baseline for person research:

| Setting          | Value                     |
| ---------------- | ------------------------- |
| Model            | GPT-6-Sol (`gpt-6-sol`) |
| Reasoning effort | High (`high`)           |
| Web search       | Live search enabled       |

Select the model and effort in the Codex window or at launch. Mentioning a model in the task prompt does not configure the session. These settings apply to the personal research agent; FinMycelium search and Builder models are configured in their own tasks. See the [official OpenAI model controls](https://learn.chatgpt.com/docs/models?surface=cli).

For a new research task, send the initial research prompt and, after delivery, the revision prompt in the same session. The second prompt requests one self-review and then directory preparation under the skill; feedback or screening from another window is not required. The agent creates the storyline/event directories that are ready without another confirmation step, updates the plan's directory tree, and reports changes, prepared directories, and remaining questions. The plan may need no content changes, while missing directories still need preparation. After these two prompts and directory preparation, close the default planning cycle and deliver the reviewed plan as the working version, with open questions recorded. Further review is not a default third step. Use the same revision prompt when later updates are warranted under the Skill.

## Initial research prompt

Replace the person and scope placeholders. The Skill defines directory creation and the shared `EPG-dataset/person-epg/` root, with a separate directory for each person. For full-life research, use `their full publicly documented life through the research date` as the research scope; use an explicit period or topic when requested.

```text
Follow skills/plan-person-research/SKILL.md and its template to conduct research on {{person_name}} covering {{research_scope}}. Complete the research and save the English research plan according to the skill, pending my confirmation.
```

Research methods, source requirements, and deliverable structure remain in [SKILL.md](../SKILL.md) and the [research plan template](../assets/research-plan-template.md). Keep the launch prompt limited to the case inputs.

## Revision prompt

Replace the plan path. The agent uses the current skill to assess the complete plan, perform any necessary follow-up research, and prepare directories under `EPG-dataset/person-epg/<person_directory>/`; no case-specific correction list is required. Unresolved entries may remain planned while ready directories are created. A new session may use this prompt with the same settings and access to the plan. Directory preparation does not start construction or change confirmation status.

```text
Re-read skills/plan-person-research/SKILL.md and its template, then review {{research_plan_path}} and revise where needed. After review, create the directories that are ready according to the skill and update the directory tree. Save the plan and summarize changes, created directories, and remaining questions.
```
