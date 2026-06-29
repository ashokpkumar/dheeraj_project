import subprocess
from rule_engine.registry import register_function


@register_function(
    name="open_emulator",
    inputs=[
        {"name": "location", "type": "string"},
    ],
    outputs=[
        {"name": "success", "type": "boolean"},
        {"name": "message", "type": "string"},
    ]
)
def open_emulator(location, context=None):
    try:
        subprocess.Popen([location], shell=False)
        return {
            "success": True,
            "message": f"Launched executable: {location}",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": f"Executable not found: {location}",
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
        }
