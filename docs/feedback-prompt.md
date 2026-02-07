# Session-End Feedback Prompt

Run this prompt at the end of long working sessions to get honest process feedback.
Best used after 30+ minutes of work together, when there's enough context to draw from.

---

I want your honest, direct feedback on how I'm working with you and on this project.
Review our recent conversation history and the current state of the codebase, then
give me candid feedback on each of these areas:

## 1. Prompting effectiveness
- Am I giving you too much or too little context in my requests?
- Am I being specific enough about what I want, or am I leaving you to guess?
- Are there patterns in how I ask for things that lead to wasted rounds or
  misunderstandings?
- What's one concrete example of a prompt I gave recently that I could have
  written better, and show me the improved version?

## 2. Priority alignment
- Based on the priorities in CLAUDE.md and docs/PRD.md, am I working on what
  matters most, or am I getting pulled into tangents?
- Are there things I keep deferring that I should be tackling now?
- Am I spending time on polish/refinement when there are higher-leverage things
  to build?

## 3. Development process
- Am I breaking work into the right-sized chunks, or am I trying to do too much
  (or too little) per session?
- Am I testing and verifying changes adequately before moving on?
- Are there workflow patterns (branching, deployment, debugging) where I'm doing
  things inefficiently?
- Am I accumulating technical debt I should be aware of?

## 4. Architecture & planning blind spots
- What problems am I likely to hit in the next few weeks that I'm not planning for?
- Are there scaling, reliability, or maintenance concerns I should address before
  they become urgent?
- Is there anything in the current codebase structure that will make future
  priorities (from the PRD roadmap) harder than they need to be?

## 5. What you'd do differently
- If you were advising someone building this project, what would you tell them
  to change about their approach?
- What's the single highest-leverage thing I could do differently starting now?

Be blunt. I'd rather hear uncomfortable truths than polite reassurance. Use
specific examples from our recent work, not hypotheticals. If everything is
genuinely fine in some area, say so briefly and move on — don't pad the response.
