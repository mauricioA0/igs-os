# 2-minute video — script and shot list

Recorded on the local stack (or the cloud URL once deployed) with the demo freshly reset
(`uv run python -m igs_common.seed --reset-demo`), worker running, models service up, and
`OPENAI_API_KEY` set so steps 3 and 4 answer live. Screen at 1440×900, browser zoom 100%,
light theme for ops, the coach pages force dark. Voiceover in English; on-screen UI is
Spanish for ops and English for the coach.

Fallbacks: if the model is slow, keep talking over the streamed tool steps; if it's down, use
`/ops?copilot=fake` for step 4 and say "scripted here, live in the repo".

| Time | Screen (tour step) | Action | Voiceover |
|---|---|---|---|
| 0:00–0:10 | Landing `/` | Cursor on **Start the 2-minute tour** | "This is IGS OS: an operating system for a sports tour operator. Agents and durable flows do the work; people stay in control." |
| 0:10–0:25 | 1 · `/ops` Today | Point at Lakeshore in the Atención queue | "Ops starts here: everything that needs a person, ranked. Lakeshore University is red: the team's enrollment fees — ninety-five dollars per traveler, per IGS's own terms — are overdue, and the hotel releases the March blocks on October 31st." |
| 0:25–0:45 | 2 · Account 360 | Hover a citation chip to show the preview | "Account 360. Why it's red, who decides — Robert Haines — and what was promised. Every line cites the email, call or chat it came from. Health comes from rules, not from the model." |
| 0:45–1:05 | 3 · Ask / copilot (⌘J) | Click the pre-loaded question, let tool steps stream | "Ask it anything about the client. The copilot uses the same tools as our MCP server, answers with sources, and says so when it doesn't know." |
| 1:05–1:25 | 4 · Approvals | Show recipient, message, price, fingerprint; press A once (armed), don't send | "The sales agent drafted the proposal from the coach's chat, but it can't send it. Ops sees exactly what will go out, bound to a hash — change one word and it needs approval again." |
| 1:25–1:40 | 5 · Flow execution | Toggle Canvas ↔ Pasos; point at the hatched wait | "This is the durable flow behind it, on Temporal. It has been waiting on that approval without holding a server, and it resumes the moment ops decides." |
| 1:40–1:52 | 6 · Proposal | Scroll hero → opponents → price → Reserve | "And this is what the coach receives: opponents matched to her team's level, one package price, and a way to reserve that becomes another approval for ops." |
| 1:52–2:00 | Terminal + repo | `claude mcp add …` line, then the README test table | "Same tools from Claude Code over MCP. Eight hundred and thirty-nine backend tests, evals and end-to-end accessibility checks in CI. The code is in the repo." |
