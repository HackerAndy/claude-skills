# bpmn-tools marketplace — `bpmn-mapper` plugin

A Claude plugin that turns any described business process into a
standards-compliant **BPMN 2.0** diagram (SVG + PNG) — pools, swimlanes, typed
events, tasks, and gateways — with a **mentoring intake** that catches gaps,
parks off-target answers, digs into vague steps, and trims over-detail while
gathering the process.

## Repository layout

```
.
├── .claude-plugin/
│   └── marketplace.json          # catalog listing the plugin
├── plugins/
│   └── bpmn-mapper/
│       ├── .claude-plugin/
│       │   └── plugin.json        # plugin manifest
│       └── skills/
│           └── bpmn-mapper/
│               ├── SKILL.md
│               ├── references/
│               └── scripts/
└── README.md
```

## Publish it publicly (make it discoverable to any Claude user)

The goal here is to get `bpmn-mapper` into Anthropic's public **`claude-community`**
marketplace so anyone can find and install it. That takes four steps.

### 1. Push to a **public** git repo (GitHub or GitLab)

```bash
cd bpmn-mapper-plugin
git init && git add . && git commit -m "bpmn-mapper plugin v1.0.0"
git branch -M main
git remote add origin https://github.com/<your-username>/bpmn-tools.git
git push -u origin main
```

Make sure the repo's visibility is **Public**. Then update the two
`https://github.com/<your-username>/bpmn-tools` placeholders in
`plugins/bpmn-mapper/.claude-plugin/plugin.json` (`homepage`, `repository`) to
your real URL and commit again.

### 2. Validate locally (the review runs the same check)

```bash
claude plugin validate ./plugins/bpmn-mapper
```

Fix anything it flags before submitting.

### 3. Submit for community review

Use whichever form matches your account:

- **Console** (individual authors, no org required): https://platform.claude.com/plugins/submit
- **claude.ai** (Team/Enterprise orgs with directory access): https://claude.ai/admin-settings/directory/submissions/plugins/new

Submissions go through automated safety screening plus review. Approved plugins
are pinned to a specific commit SHA in the
[`anthropics/claude-plugins-community`](https://github.com/anthropics/claude-plugins-community)
catalog, and CI bumps the pin automatically as you push new commits. The public
catalog syncs nightly, so allow a delay between approval and the plugin
appearing.

### 4. Once approved, anyone installs it with

```
/plugin marketplace add anthropics/claude-plugins-community
/plugin install bpmn-mapper@claude-community
```

You can verify it's live by searching for `bpmn-mapper` in the
[community catalog](https://github.com/anthropics/claude-plugins-community/blob/main/.claude-plugin/marketplace.json).

> **Before approval / for early testers:** people can already install straight
> from your repo with `/plugin marketplace add <your-username>/bpmn-tools` then
> `/plugin install bpmn-mapper`. Good for sharing while the review is pending.

## Updating & releasing (the source of truth is this repo)

There are two copies of the skill: the one you may have installed personally in
Claude, and **this git repo**. Only the repo reaches your users. So make every
change here, in the repo, never in the personally-installed copy.

**Every time you change the skill:**

1. Edit files under `plugins/bpmn-mapper/skills/bpmn-mapper/`
   (`SKILL.md`, `references/`, `scripts/`).
2. **Bump `version`** in `plugins/bpmn-mapper/.claude-plugin/plugin.json`:
   - patch for fixes (`1.0.0` → `1.0.1`)
   - minor for new capabilities (`1.0.0` → `1.1.0`)
   - major for breaking changes (`1.0.0` → `2.0.0`)
   This is what tells installed clients an update exists — users only receive
   changes when this number goes up.
3. Validate and commit:
   ```bash
   claude plugin validate ./plugins/bpmn-mapper
   git add . && git commit -m "bpmn-mapper vX.Y.Z: <what changed>"
   git push
   ```
4. The `claude-community` catalog auto-bumps its pinned commit as you push and
   syncs nightly, so allow a short delay.
5. Users pull the update with `/plugin marketplace update` (then
   `/plugin install bpmn-mapper@claude-community` if not on auto-update).

**Keep your own machine on the repo version.** Install the plugin from your
marketplace and use that, rather than a separately-saved standalone copy, so
what you use and what you ship are always the same files. (See "Match GitHub
after saving a standalone copy" below if you already saved one.)

## Match GitHub after saving a standalone copy

If you already installed the skill personally (e.g. via **Save skill**), do this
once so the git repo becomes your single source of truth:

1. Push this repo to GitHub (steps above). It already matches your saved copy.
2. Remove the standalone copy so it can't drift: in Claude, open
   **Settings → Capabilities → Skills** and delete the personal `bpmn-mapper`
   (in Claude Code, `/plugin` manages installed plugins).
3. Add your marketplace and install the plugin version instead:
   ```
   /plugin marketplace add <your-username>/bpmn-tools
   /plugin install bpmn-mapper
   ```
   From now on your local copy updates via `/plugin marketplace update`, exactly
   like your users' copies — no more divergence.

## Requirements

The renderer uses Python 3 with `cairosvg` for PNG export (`pip install cairosvg`).
SVG generation itself needs only the Python standard library.

## Usage

Once installed, just describe a process — "map our refund workflow", "turn this
SOP into a swimlane diagram", "model the approval flow" — and the skill runs the
intake and produces the diagram.
