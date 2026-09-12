# claude-skills

A collection of Claude Code skills I'm building.

## Structure

Each skill lives in its own directory under `skills/`, following the standard
Claude Code skill format (a `SKILL.md` with frontmatter, plus any supporting
files/scripts the skill needs).

```
skills/
  <skill-name>/
    SKILL.md
    ...
```

## Adding a new skill

1. Create `skills/<skill-name>/SKILL.md`
2. Add frontmatter with `name` and `description`
3. Write the instructions the skill should follow
