from typing import cast
from pathlib import Path

import unreal

from AssetUtilities.menu_register import MenuEntry, menu_register


_here = Path(__file__).resolve()

unreal.log(f">>> Asset Utilities scripts initialized: <<<")

menu_register(
    "ContentBrowser.AssetContextMenu.Texture2D",
    cast(list[MenuEntry], [
        {
            "label": "Run Channel Packer",
            "target_module": "AssetUtilities.TextureUtilities.ChannelPacker.channel_packer",
            "tooltip": "Pack separate textures into single RGB/A texture",
            # "section_name": "ImportedAssetActions",
            "also_in_folders": True,
            "icon": "ClassIcon.Texture2D",
        },
        {
            "label": "Run Color Curve Generator",
            "target_module": "AssetUtilities.TextureUtilities.LinearColorCurveSampler.linear_color_curve_sampler",
            "tooltip": "Creates Linear Color Curves with colors sampled from selected textures.",
            # "section_name": "ImportedAssetActions",
            "also_in_folders": False,
            "icon": "ClassIcon.CurveBase",
        },
    ]),
    # main_menu="PythonTexture Tools"
)















#                                                === Menu Register ===

# Allows creating buttons and buttons in submenus in existing Unreal menus (top bar and context), e.g., ContentBrowser.AssetContextMenu.Texture2D, LevelEditor.MainMenu.Edit.
# Target module can be a path to module only: AssetUtilities.TextureUtilities.module/function_name and it will automatically assume that the function name is the same as the module.
# Or it can be specified: AssetUtilities.TextureUtilities.module.function
# Custom section_name and flag if the menus should also show up in a folder context menu are determined from the first entry only, for the whole section.
# Icons: Derived from the general icon name. Editor Style "set" by default. If the icon is from another style, it can be changed to App Style by typing: "AppStyle:Icon"
# Adding buttons to other parts of the Editor (like ToolBar) requires a different approach.




# "ContentBrowser.AssetContextMenu.Texture2D", - Main directory in the Editor where the buton will be registered.                                                     # mandatory
# {
#     "target_module":           - absolute path to a Python function, or just the module to run.                                                                     # mandatory
#     # "label": ...             - if unspecified derives button name from the function name.                                                                         # optional
#     # "tooltip": ...           - empty if unspecified.                                                                                                              # optional
#     # "section_name": ...      - 1st Entry Only: menu section name, e.g., GetAssetActions (TEXTURE ACTIONS), if empty defaults to AssetUtilities.                   # optional
#     # "also_in_folders": ...   - 1st Entry Only: if specified, then also registers menu entires in the context menu for folder assets.                              # optional
#     # "icon": ...              - takes either class icon like: ClassIcon.Texture2D as well as other type: Icons.Save.                                               # optional
#     # "inject_ctx": ...        - if external context factory module is specified, launches the main function with the factory as a context.                         # optional
# },
# debug=...,                     - shows debug messages in logs.                                                                                                      # optional
# main_menu=...                  - if specified groups all entries into a single parent "folder" entry in the menu.                                                   # optional









#                                           === Menu Register Examples===

# Minimal:

#        {
#        "target_module": "AssetUtilities.TextureUtilities.example_tool.example_tool
#        },



# Label + tooltip + icon + displayed in folders context menus:

#         {
#             "label": "Run Channel Packer",
#             "target_module": "AssetUtilities.TextureUtilities.channel_packer.channel_packer",
#             "tooltip": "Pack separate textures into single RGB/A texture",
#             "also_in_folders": True,
#             "icon": "ClassIcon.Texture2D",
#         },



# Label + tooltip + icon + registering under (optionally) an existing menu section and grouping the entry into a submenu:

# {
#     "label": "Utilities → Mip Fix",
#     "target_module": "AssetUtilities.TextureUtilities.mip_fix.mip_fix",
#     "tooltip": "Fixes mips on selected textures",
#     "section_name": "ImportedAssetActions",
#     "icon": "Icons.Edit",
# },
# ]),
# main_menu = "PythonTexture Tools",