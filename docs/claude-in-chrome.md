# Claude in Chrome: fast and light

How to make Claude in Chrome finish work faster on a **4 GB PC**. This is the browser version of
[Tokensaver](TOKENSAVER.md): less waiting, fewer wasted steps, low memory use.

Claude itself runs in the cloud, so it doesn't use your PC's memory. What uses memory is Chrome and
the pages Claude opens. What makes it slow is how many steps Claude takes and how often it stops to
ask you. This guide cuts both.

---

## 1. One-time setup (5 minutes)

### Save the speed rules as a shortcut

In the Claude side panel, paste the block below, send it once, then save it as a shortcut named
`fast`. From then on, type `/fast` at the start of any task and write the task after it.

```text
Work fast and use as few steps as possible:
1. If you know the URL, go straight to it. Don't search for it.
2. Read the page text first. Take a screenshot only when the layout matters.
3. Plan once at the start, then do it. Don't re-check steps that already worked.
4. Fill in every field on a form, then submit once.
5. Use keyboard shortcuts and URL parameters when they are faster than clicking.
6. Use one tab. Close each tab as soon as you're done with it.
7. If something fails twice, stop and tell me what blocked you. Don't keep retrying.
8. When you finish, reply in 3 lines at most: what you did, the result, anything I need to do.
```

### Choose the settings that save the most time

| Setting | Choose | Why |
|---|---|---|
| Permission mode | **Follow Claude's plan** (or automatic approval) on sites you trust | In manual mode Claude stops before every click. This is the biggest slowdown. High-risk actions such as purchases or deletions still ask you |
| Model | A **fast, small model** for clicking and form filling. A larger one only for hard reasoning | Most browser steps are simple, and a smaller model answers each one faster |
| Site permissions | Allow only the sites you work on | Claude doesn't wander, and it's safer |

### Set Chrome up for 4 GB of RAM

1. **Memory Saver on:** Chrome Settings, then **Performance**, then **Memory Saver** set to *Maximum*.
   Unused tabs are unloaded automatically.
2. **Turn off other extensions** at `chrome://extensions`. Keep only Claude, plus a password manager
   if you use one.
3. **Keep 3 tabs or fewer** open while Claude works. Claude puts its tabs in its own tab group; close
   the others.
4. **Close other heavy apps** (video calls, IDEs, games) during long Claude tasks.
5. **Check memory use** with Chrome's task manager (**Shift+Esc**). Close the biggest tab if the
   total goes over ~2 GB.

---

## 2. Every task: write the prompt so Claude doesn't have to guess

Most slow runs happen because Claude spends steps working out something you already knew. Give it
this shape:

```text
/fast
Goal: <one sentence>
Start at: <exact URL>
Data: <the values to type, the names to look for>
Done when: <what the finished screen or result looks like>
Don't: <anything to leave alone>
```

Example:

```text
/fast
Goal: mark ticket 4821 as billing and reply with the refund template.
Start at: https://helpdesk.example.com/tickets/4821
Data: department = Billing, template = "Refund – double charge"
Done when: the ticket shows status "Pending customer" and the reply is sent.
Don't: change the ticket's priority.
```

---

## 3. Work you repeat: don't explain it twice

| Situation | Use |
|---|---|
| A prompt that worked well | **Save it as a shortcut** (`/` to reuse it) |
| The same clicks every time | **Record the workflow** once, and Claude repeats it (classic side panel) |
| Daily or weekly jobs | **Schedule the shortcut** (clock icon, top right of the panel) |

---

## 4. Habits

- **Start a new chat for each task.** A long conversation makes every step slower.
- **One task per prompt.** Split big jobs into shortcuts you run one after another.
- **Log in before you start.** Claude waiting on a login page wastes steps.
- **If a run was slow, look at where Claude hesitated.** Usually it was a missing URL or value, or
  an unclear "done when". Add that to the shortcut.

---

Sources: [Get started with Claude in Chrome](https://support.claude.com/en/articles/12012173-get-started-with-claude-in-chrome) ·
[Permissions guide](https://support.claude.com/en/articles/12902446-claude-in-chrome-permissions-guide).
Features were checked in September 2026, while the extension was still in beta. If a setting has
moved, look for it in the extension's settings page.
