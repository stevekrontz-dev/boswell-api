#!/usr/bin/env python3
"""Add fingerprint dispatch to app.py"""

with open('app.py', 'r') as f:
    content = f.read()

old = '''    elif tool_name == "boswell_resume":
        return invoke_view(get_checkpoint, query_string={"task_id": args["task_id"]})

    else:
        return {"error": f"Unknown tool: {tool_name}"}, 400'''

new = '''    elif tool_name == "boswell_resume":
        return invoke_view(get_checkpoint, query_string={"task_id": args["task_id"]})

    elif tool_name == "boswell_validate_routing":
        json_data = {
            "content": args.get("content"),
            "branch": args.get("branch", "command-center")
        }
        return invoke_view(validate_commit_routing, method='POST', json_data=json_data)

    else:
        return {"error": f"Unknown tool: {tool_name}"}, 400'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Added boswell_validate_routing dispatch')
