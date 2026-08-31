---
name: wayfinder
description: Chart an effort too big for one session as a map of decision tickets under docs/plans/, then resolve one ticket per session until the way to the destination is clear.
disable-model-invocation: true
metadata:
  category: codebase-understanding
  origin: https://github.com/mattpocock/skills (MIT), skills/engineering/wayfinder — rewritten around a docs/plans ticket substrate; see CREDITS.md
---

# Wayfinder

An idea has arrived that is too big for one session and wrapped in fog: the way from here to the **destination** isn't visible yet.
Wayfinding finds that way — it does not charge at the destination.
This skill charts the way as a **map** under `docs/plans/`, then works its **decision tickets** — questions whose resolution is a decision, not slices of a build to execute — one per session until the route is clear.

## When to use

- A greenfield project or a large feature build where you can feel the shape of the work but cannot yet write it as a spec.
- More than one 100K-token session of thinking stands between here and a plan.

**Skip when** the effort fits one session — grill it and write the spec directly.
Skip when the plan already exists and only needs slicing; that is `plan-audit` territory, not wayfinding.
This is the heaviest planning flow here: reaching for it on a well-scoped feature costs several sessions and buys nothing.

## Plan, don't do

Every ticket resolves a decision, and the map is done when nothing is left to decide before someone goes and builds the thing.
The pull to just do the work is the signal you have reached the edge of the map — that is the moment to hand off to a spec, not to start implementing.
An effort can override this in the map's **Notes**; absent that, produce decisions, not deliverables.

## The map

The map is `docs/plans/<effort-slug>/map.md`, its tickets are `docs/plans/<effort-slug>/tickets/NN-<slug>.md`, numbered from `01`.
This matches the docs layout in `CLAUDE.md` — never `.scratch/`, never `docs/superpowers/**`.

The map is an **index**, not a store.
A decision lives in exactly one place — its ticket — so the map gists it and links, never restates it.
Load the map at low resolution each session and open individual tickets on demand.

Refer to every ticket by its **title** in anything the operator reads.
A wall of `01, 02, 03` is illegible; the number rides inside the name, it never stands in for it.

```markdown
# <effort name>

## Destination

<what reaching the end of this map looks like — the spec, decision, or change this effort is finding its way to. One or two lines; every session orients to it before choosing a ticket.>

## Notes

<domain; skills and rules every session should consult; standing preferences for this effort>

## Decisions so far

- <resolved ticket title> (`tickets/<NN>-<slug>.md`) — <one-line gist of the answer>

## Not yet specified

<in-scope fog you cannot ticket yet; graduates as the frontier advances>

## Out of scope

<work ruled beyond the destination; never graduates>
```

Open tickets are not listed on the map — they are found by scanning `tickets/`.

```markdown
# NN — <ticket title>

Type: grilling | research | prototype | task
Mode: HITL | AFK
Status: open | claimed | resolved
Blocked by: 02, 05

## Question

<the decision or investigation this ticket resolves, sized to one session>

## Answer

<recorded on resolution, with its evidence basis>
```

A ticket is **unblocked** when every ticket it lists is `resolved`.
The **frontier** is the open, unblocked, unclaimed tickets — the edge of the known.
A session **claims** a ticket by setting `Status: claimed` and saving that file before any work, so a parallel session skips it.

**On GitHub instead:** when the repo already runs its work on Issues, the map is one issue and the tickets are its sub-issues with native blocking links, which renders the frontier in GitHub's own UI.
Everything below is unchanged; only where the files live changes.
Use the local files by default — they work offline and commit alongside the code.

## Ticket types

Every ticket is **HITL** — worked with the operator, who speaks for themselves — or **AFK**, driven by the agent alone.
A HITL ticket resolves only through that live exchange.
An agent that asks its own question and then answers it has broken HITL and produced a fabricated decision.

- **grilling** (HITL) — conversation, one question at a time. The default. Look up _facts_ yourself; put every _decision_ to the operator and wait.
- **research** (AFK) — reading docs, third-party APIs, or the knowledge wiki to surface a fact a decision waits on. Resolved by a subagent.
- **prototype** (HITL) — a cheap, rough, concrete artifact to react to, when "how should it look" or "how should it behave" is the real question. Link the artifact; do not paste it in.
- **task** (either) — manual work that must happen before a decision can be made: provisioning access, moving data so its shape can be seen, signing up for a service so its API can be judged. The one type that _does_ rather than decides, and it earns that by unblocking a decision. Its answer records what was done plus any facts later tickets depend on.

## Fog of war

The map is deliberately incomplete.
Beyond the live tickets lies the **fog of war** — decisions you can tell are coming but cannot yet pin down.
Resolving a ticket clears the fog ahead of it, **graduating** whatever is now specifiable into fresh tickets.

The test is whether you can state the question precisely _now_ — not whether you can answer it.

- **Ticket** when the question is already sharp, even if it is blocked.
- **Not yet specified** when you cannot phrase it that sharply. Write it as loosely as the view allows, and do not pre-slice it: one patch may graduate into several tickets, or none.

## Out of scope

Fog gathers only _toward_ the destination, so work past the destination is not fog — it is out of scope, and it never graduates.
When an existing ticket turns out to sit past the destination, mark it `resolved` with a one-line answer saying it was ruled out, and record the gist plus the reason under **Out of scope**.
It stays out of **Decisions so far**, which records the route actually walked.

## Chart the map

1. **Pull precedent first.** If you keep a record of past decisions — a wiki, a memory directory, an agent that retrieves them — query it on 1–2 narrowly-named topics before naming anything. Finding nothing means you are setting new precedent, so say so on the map's Notes rather than silently inventing.
2. **Name the destination.** Grill it out one question at a time. The destination fixes the scope, so it settles before any ticket exists.
3. **Map the frontier** — grill again, breadth-first, fanning across the whole space rather than deep on one thread. **If this surfaces no fog**, the effort fits one session: stop, say so, and ask how the operator wants to proceed. Do not build a map nobody needs.
4. **Write the map and the tickets you can specify now**, then wire `Blocked by` in a second pass once every ticket has a number. Everything you cannot specify stays in **Not yet specified**.
5. **Fan out the AFK research tickets** as parallel subagents in a single message. Built-in `Explore` and `Plan` agents do not inherit `CLAUDE.md` or your rules files, so write every constraint they must respect into each prompt yourself.
6. **Commit the map** as a conventional commit, then stop. Charting resolves nothing by design, and it is not a finished task group — do not write the post-task audit marker.

## Work the map

1. **Re-read the map and the ticket files from disk in this turn.** You are never the only writer — a teammate, another session, or a merged branch can move the files under you — so state from earlier in the conversation is stale.
2. **Choose and claim.** Take the ticket the operator named, else the first frontier ticket by number. Set `Status: claimed` and save before any work.
3. **Resolve it**, zooming into related or resolved tickets on demand and invoking whatever the map's Notes name. HITL tickets resolve through the operator, not around them.
4. **Record the answer with its evidence basis.** Every fact in a resolution traces to a source, and a gap is marked as one rather than filled in. A resolution built on truncated or aborted command output is not a resolution: empty output can mean the command never ran.
5. **Update the map**: append one gist line plus link under **Decisions so far**, graduate the fog this answer sharpened into new tickets, and clear each graduated patch from **Not yet specified** so it lives in one place. If the answer invalidates other tickets, update or delete them.
6. **Commit, then stop.** One ticket per session — the exception is AFK research, which subagents burn down in parallel. Hand off (`handoff`) or `/clear` rather than taking a second ticket on a tired context.

## Closing the map

When no ticket remains, the way is clear and wayfinder is finished: it hands off, it does not build.
Collapse the map's linked decisions into a spec under `docs/specs/`, then slice and implement from there.
Looping the map straight into implementation throws away the linked detail the tickets hold.

Before closing, check the decisions for scope: one that holds beyond this effort belongs wherever your durable notes live, not buried in a plan file.
The oracle gave precedent; it cannot vouch for the new decisions — route anything hard to reverse through an independent adversarial check first.

## Concurrency and cost

Sessions run in parallel over the same files, so claim before working and re-read before writing.
Fan out only what is cheap: research subagents are fine, but a `task` ticket that runs a device build, an emulator, or a large SDK download runs alone, because stacking those is how a machine falls over mid-effort.
