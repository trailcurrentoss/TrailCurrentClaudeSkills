# TrailCurrent Claude Skills

A growing library of [Claude skills](https://docs.claude.com/en/docs/claude-code/skills) that we use in TrailCurrent's R&D processes — from authoring embedded GUIs to running our hardware tooling.

We're publishing these as we extract them from our day-to-day work, so that other teams building hardware and embedded products can reuse the same workflows we rely on internally.

## What is a Claude skill?

A skill is a folder containing a `SKILL.md` file with YAML frontmatter (`name`, `description`) plus optional supporting scripts and references. When Claude Code encounters a task that matches a skill's description, it loads the skill and follows its instructions — encoding domain knowledge that would otherwise have to be re-derived every session.

See Anthropic's [skills documentation](https://docs.claude.com/en/docs/claude-code/skills) for the format spec.

## Skills in this repo

| Skill | What it does |
|---|---|
| [`eezstudio/`](eezstudio/SKILL.md) | Author and debug [EEZ Studio](https://www.envox.eu/studio/studio-introduction/) LVGL projects (`.eez-project` JSON files) programmatically. Covers measuring widget geometry against real TTF fonts, bisecting silently-failing project files, and the EEZ Studio → `idf.py build` handoff for ESP32 / LVGL firmware. |

More skills will be added as we extract them — pinout diagram generation, KiCad library tooling, FreeCAD automation, CAD-to-photo rendering, and others currently live in our internal toolbox.

## Using a skill

Copy the skill directory into your Claude Code skills location:

```bash
# User-scope (available in every project)
cp -r eezstudio ~/.claude/skills/

# Or project-scope (available only inside one project)
cp -r eezstudio /path/to/your/project/.claude/skills/
```

Claude Code picks the skill up automatically — it appears in the available-skills list at session start and is invoked when a task matches its description.

## Contributing

Issues and pull requests are welcome. If you add a skill, please:

1. Place it in its own top-level directory.
2. Include a `SKILL.md` with the required `name` and `description` frontmatter fields. The description should make clear *when* the skill should be invoked, not just what it does.
3. Add a row to the table above.

## License

[MIT](LICENSE) — use, modify, and redistribute freely.
