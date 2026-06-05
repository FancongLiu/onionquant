import pathlib
p = pathlib.Path('company/chairman_dashboard.html')
content = p.read_text('utf-8')

old1 = "  if (expandedDept) addMilestone("
old2 = "  addMilestone("

lines = content.split('\n')
new_lines = []
for line in lines:
    if "addMilestone" in line and ("展开部门架构" in line or "全部展开部门架构" in line or "全部折叠部门" in line):
        new_lines.append("  /* milestone only for significant actions */")
    else:
        new_lines.append(line)

content2 = '\n'.join(new_lines)
if content2 != content:
    p.write_text(content2, 'utf-8')
    print("Fixed milestone spam lines")
else:
    print("No matches found — checking chars")
    for i, line in enumerate(lines):
        if 'addMilestone' in line:
            print(f"  Line {i+1}: {repr(line[:100])}")
