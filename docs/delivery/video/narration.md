# Demo video — narration

Voiceover for `docs/delivery/video/igs-os-demo.mp4` (OpenAI TTS `gpt-4o-mini-tts`, voice `ash`).
Source of truth: `scripts/video/narration.json` (edit there; `scripts/video/make.sh` regenerates only changed lines).
Payment amounts are deliberately not narrated: terms are configuration (US$95 enrollment + US$500 installments, balance 110 days before departure).
The video says once, in the first scene, that every client is fictional; the title cards and the guide's POC banner say it on screen.

## 01-landing — IGS OS

This is IGS OS: an operating system for a sports tour operator. Agents and durable flows do the work, and people stay in control. Every client you'll see is fictional.

## 02-today — Today

Ops starts here, with everything that needs a person, ranked. Lakeshore University is red: enrollment fees are a week overdue, and the hotel releases its room blocks in nine days.

## 03-account — Account 360

Account 360 shows why it's red, who decides, and what was promised. Every line cites the email, call or chat it came from. Health comes from rules, not from the model.

## 04-copilot — Copilot

Ask the copilot about the client. It uses the same tools as our MCP server, answers with sources, and says so when it doesn't know.

## 05-approvals — Human approval

The sales agent drafted the proposal, but it can't send it. Ops sees exactly what will go out, bound to a fingerprint. Approve, and the flow continues.

## 06-editor — Flow editor

Flows are built on a canvas, the way Voiceflow does it: blocks of steps, a step library, and a test panel to try a flow before publishing it.

## 07-execution — Durable flow

This is the run behind Lakeshore's proposal, on Temporal. It waited for that approval without holding a server, and resumed the moment ops decided.

## 08-proposal — What the coach receives

This is what the coach receives: opponents matched to her team's level, one package price, and a way to reserve that becomes another approval for ops.

## 09-guide — Guide

Coaches start in a chat on the site. And on every screen, a guide bubble explains what you're looking at, in real time. It's a proof of concept, and it says so.

## 10-mcp — Built for agents

The same tools are open to Claude Code over MCP, with evals, end-to-end tests and accessibility checks in CI.

## 11-close — IGS OS · v0

IGS OS. Built with agents, for an operation run by people. Try it at igs-os dot vercel dot app.

## Teaser (30 s)

IGS OS runs a sports tour operation with agents and durable flows. Account 360 explains every client, with sources. Agents draft, people approve, and the flow resumes on its own. A guide explains every screen in real time. Built with agents, for an operation run by people.
