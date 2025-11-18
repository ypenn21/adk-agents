
import os
from toolbox_core import ToolboxSyncClient

TOOLBOX_URL = "https://toolbox-ttjkms4frq-uc.a.run.app"

def main():
    print(f"Connecting to toolbox at {TOOLBOX_URL}...")
    client = ToolboxSyncClient(TOOLBOX_URL)
    try:
        # Try to load the toolset
        tools = client.load_toolset("tickets_toolset")
        print(f"Successfully loaded toolset 'tickets_toolset'. Found {len(tools)} tools.")
        for tool in tools:
            print(f" - {tool.__name__}")
    except Exception as e:
        print(f"Error loading toolset: {e}")

if __name__ == "__main__":
    main()
