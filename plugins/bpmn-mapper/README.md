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

## Publish it publicly (standalone GitHub repo)

The goal here is to host `bpmn-mapper` in your own public GitHub repo so users
install directly from your marketplace source.

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

### 3. Add your repo as a marketplace source

```
/plugin marketplace add <your-username>/bpmn-tools
/plugin install bpmn-mapper
```

Anyone with access to the public repo can install this plugin immediately; no
community review step is required for this distribution path.

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
4. Tag the same version in Git using a **plugin-scoped tag** so multiple
   plugins in one repo do not collide:
   ```bash
   # example when plugin.json version is 1.2.0
   git tag bpmn-mapper-v1.2.0
   git push origin bpmn-mapper-v1.2.0
   ```
   Keep the plugin portion and version aligned with
   `plugins/bpmn-mapper/.claude-plugin/plugin.json` (for example,
   `bpmn-mapper-v1.2.0` tag for `1.2.0` in JSON).
5. Users pull updates with `/plugin marketplace update`.

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

## Sync checklist (GitHub + plugin version)

When syncing changes to GitHub, keep these in lockstep:

1. Target plugin manifest version (for example,
   `plugins/bpmn-mapper/.claude-plugin/plugin.json`)
2. Plugin-scoped Git tag (`<plugin-id>-vX.Y.Z`)
3. Release notes/title (if you publish GitHub Releases)

If these drift, users may see unclear update history. A good quick check is:

```bash
jq -r '.version' plugins/bpmn-mapper/.claude-plugin/plugin.json
git tag --list 'bpmn-mapper-v*' --sort=-v:refname | head -n 5
```

## Release command sequence

Use this from the repo root to validate, compare against the latest published
plugin tag, and only proceed if `plugin.json` is a new version:

```bash
PLUGIN="bpmn-mapper"
MANIFEST="plugins/${PLUGIN}/.claude-plugin/plugin.json"

claude plugin validate "./plugins/${PLUGIN}"
VERSION=$(jq -r '.version' "${MANIFEST}")
TAG="${PLUGIN}-v${VERSION}"
LATEST_TAG=$(git tag --list "${PLUGIN}-v*" --sort=-v:refname | head -n 1)

echo "plugin: ${PLUGIN}"
echo "plugin.json version: ${VERSION}"
echo "latest plugin tag: ${LATEST_TAG:-<none>}"

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
   echo "ERROR: tag ${TAG} already exists. Bump plugin.json version first."
   exit 1
fi

if [ -n "${LATEST_TAG}" ]; then
   LATEST_VERSION=${LATEST_TAG#${PLUGIN}-v}
   if [ "$(printf '%s\n%s\n' "${LATEST_VERSION}" "${VERSION}" | sort -V | tail -n 1)" != "${VERSION}" ] || [ "${VERSION}" = "${LATEST_VERSION}" ]; then
      echo "ERROR: plugin.json version ${VERSION} is not newer than latest plugin tag ${LATEST_TAG}."
      exit 1
   fi
fi

git add .
git commit -m "bpmn-mapper v${VERSION}: <what changed>"
git tag "${TAG}"
git push origin main
git push origin "${TAG}"
```

Optional quick verify after pushing:

```bash
git tag --list "${PLUGIN}-v*" --sort=-v:refname | head -n 5
```

## Requirements

The renderer uses Python 3 with `cairosvg` for PNG export (`pip install cairosvg`).
SVG generation itself needs only the Python standard library.

## Usage

Once installed, just describe a process — "map our refund workflow", "turn this
SOP into a swimlane diagram", "model the approval flow" — and the skill runs the
intake and produces the diagram.
