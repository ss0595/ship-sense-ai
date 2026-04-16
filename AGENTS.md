# Workspace Preferences

## elab
- When the user asks for coding help in this workspace, prefer concise C++ answers aimed at eLab-style portal checks unless the user says otherwise.
- Preserve exact mandatory substrings the portal expects.
- Optimize for low cyclomatic complexity, token count, and NLOC when those limits matter.
- Default to returning just the final code with minimal explanation.
- If a metric or mandatory check fails, revise the code to target that specific gate first.
