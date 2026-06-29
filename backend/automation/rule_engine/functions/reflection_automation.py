import os
from rule_engine.registry import register_function


@register_function(
    name="open_emulator",
    inputs=[
        {"name": "location", "type": "string"},
    ],
    outputs=[
        {"name": "success", "type": "boolean"},
        {"name": "launched", "type": "array"},
        {"name": "message", "type": "string"},
    ]
)
def open_emulator(location, context=None):
    if not os.path.isdir(location):
        return {
            "success": False,
            "launched": [],
            "message": f"Directory not found: {location}",
        }

    rd3x_files = [f for f in os.listdir(location) if f.endswith(".rd3x")]

    if not rd3x_files:
        return {
            "success": False,
            "launched": [],
            "message": f"No .rd3x files found in: {location}",
        }

    launched = []
    errors = []
    for filename in rd3x_files:
        filepath = os.path.join(location, filename)
        try:
            os.startfile(filepath)
            launched.append(filename)
        except Exception as e:
            errors.append(f"{filename}: {e}")

    return {
        "success": len(errors) == 0,
        "launched": launched,
        "message": f"Launched {len(launched)} file(s)." + (f" Errors: {'; '.join(errors)}" if errors else ""),
    }
